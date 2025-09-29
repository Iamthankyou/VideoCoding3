
# win_quickfire_runner.py
# Fire off EncoderApp jobs immediately; compute later.
# Usage examples:
#   pip install pyyaml numpy
#   python win_quickfire_runner.py --yaml experiment_ablation.yaml --workers 24 --coarse ^
#       --inherit PERFADD=Baseline_Min --skip-baselines Baseline_Min --timeout-sec 1200
#
# Notes:
#   - --coarse sets qps=27,32,37 and frames=16, and --nobitstream
#   - --inherit PERFADD=Baseline_Min  --> perf_add experiments will append Baseline_Min args automatically
#   - --skip-baselines Baseline_Min   --> do not launch Baseline_Min anchors now (they're slow); analyze later

import argparse, os, sys, shlex, subprocess, json, csv, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from vtm_logparser_win import parse_log_for_metrics

CREATE_BELOW_NORMAL = 0x00004000
CREATE_NEW_PROCESS_GROUP = 0x00000200

def quote_win(p: str) -> str:
    if p is None: return ""
    p = str(p)
    if any(ch in p for ch in [' ', '(', ')']):
        return f'"{p}"'
    return p

def build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, args_list, out_dir, frames_override=None, nobitstream=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    bitstream = out_dir / f"{seq['name']}_QP{qp}.vvc"
    log_path  = out_dir / f"{seq['name']}_QP{qp}.log"
    frames = frames_override if frames_override is not None else seq.get('frames', 64)
    b_arg = "NUL" if nobitstream else str(bitstream)

    base = [
        quote_win(vtm_bin), "-c", quote_win(base_cfg),
        "-i", quote_win(seq['yuv']), "-wdt", str(seq['width']), "-hgt", str(seq['height']),
        "-fr", str(seq['fps']), "-f", str(frames), "-q", str(qp),
        "-b", quote_win(b_arg),
    ]
    full = base + fixed_args + (args_list or [])
    cmd = " ".join(full)
    return cmd, str(log_path)

def run_one(cmd, log_path, timeout_sec=None):
    # shell=True for CLI flags; BELOW_NORMAL priority to stay responsive
    with open(log_path, "w", encoding="utf-8", errors="ignore") as logf:
        try:
            p = subprocess.Popen(cmd + f" 2>&1", shell=True, stdout=logf,
                                 creationflags=CREATE_BELOW_NORMAL|CREATE_NEW_PROCESS_GROUP)
            rc = p.wait(timeout=timeout_sec) if timeout_sec and timeout_sec>0 else p.wait()
            status = "DONE" if rc == 0 else f"RC={rc}"
        except subprocess.TimeoutExpired:
            try:
                p.terminate()
            except Exception:
                pass
            status = "TIMEOUT"
        except Exception as e:
            status = f"ERR:{e.__class__.__name__}"
    return status

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--coarse", action="store_true", help="Use qps=27,32,37; frames=16; --nobitstream")
    ap.add_argument("--qps", default="", help="Override QPs, e.g., 27,32,37")
    ap.add_argument("--frames", type=int, default=0, help="Override frames per run")
    ap.add_argument("--nobitstream", action="store_true")
    ap.add_argument("--timeout-sec", type=int, default=0, help="Kill a job if it exceeds this many seconds")
    ap.add_argument("--skip-baselines", default="", help="Comma-separated baseline names to skip launching now")
    ap.add_argument("--inherit", action="append", default=[],
                    help="Format GROUP=BASELINE_NAME (e.g., PERFADD=Baseline_Min) to inherit BASELINE args for all items in GROUP.")
    ap.add_argument("--groups", default="perf_ablate,perf_add", help="Which groups to run: comma-separated from {perf_ablate,perf_add,speed_ablate,speed_add}")
    ap.add_argument("--manifest", default="manifest_quickfire.json")
    ap.add_argument("--csv", default="quickfire_runs.csv")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))

    vtm_bin   = cfg["vtm_bin"]
    base_cfg  = cfg["base_cfg"]
    out_root  = Path(cfg.get("output_dir","./runs_out_ablation"))
    sequences = cfg["sequences"]
    fixed_args = cfg.get("fixed_args", [])
    yaml_qps   = cfg.get("qps", [37,32,27,22])  # full set by default

    # Coarse options
    if args.coarse:
        qps = [27,32,37]
        frames_override = 16
        nobit = True
    else:
        qps = [int(x) for x in args.qps.split(",")] if args.qps.strip() else yaml_qps
        frames_override = args.frames if args.frames>0 else None
        nobit = args.nobitstream

    # Parse group selections
    wanted_groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    group_keys = [g for g in ["perf_ablate","perf_add","speed_ablate","speed_add"] if g in cfg and g in wanted_groups]

    # Baselines
    baselines = cfg.get("baselines", [])
    baseline_map = {b["name"]: b.get("args",[]) for b in baselines}
    skip_baselines = {x.strip() for x in args.skip_baselines.split(",") if x.strip()}

    # Inheritance map for groups
    inherit_map = {}
    for it in args.inherit:
        if "=" in it:
            k,v = it.split("=",1)
            inherit_map[k.strip().lower()] = v.strip()

    # Build job list
    jobs = []
    # Baselines first (unless skipped)
    for b in baselines:
        if b["name"] in skip_baselines:
            continue
        for seq in sequences:
            for qp in qps:
                out_dir = out_root / "baselines" / b["name"] / seq["name"] / f"QP{qp}"
                cmd, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, b.get("args",[]),
                                      out_dir, frames_override=frames_override, nobitstream=nobit)
                jobs.append({"group":"baseline","exp":b["name"],"seq":seq["name"],"qp":qp,"cmd":cmd,"log":logp})

    # Experiments by group
    for gk in group_keys:
        items = cfg[gk]
        inherit_from = inherit_map.get(gk.lower())
        base_args_for_group = baseline_map.get(inherit_from, []) if inherit_from else []

        for it in items:
            exp_name = it["name"]
            exp_args = base_args_for_group + it.get("args",[])
            for seq in sequences:
                for qp in qps:
                    out_dir = out_root / gk / exp_name / seq["name"] / f"QP{qp}"
                    cmd, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, exp_args,
                                          out_dir, frames_override=frames_override, nobitstream=nobit)
                    jobs.append({"group":gk,"exp":exp_name,"seq":seq["name"],"qp":qp,"cmd":cmd,"log":logp})

    # Shuffle to fill cores evenly
    import random; random.shuffle(jobs)

    # Run
    print(f"[INFO] Quickfire: {len(jobs)} runs, qps={qps}, frames={frames_override or 'YAML'}, nobitstream={nobit}, timeout={args.timeout_sec}s")
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut2job = {ex.submit(run_one, j["cmd"], j["log"], args.timeout_sec): j for j in jobs}
        for fut in as_completed(fut2job):
            j = fut2job[fut]
            status = fut.result()
            br, py = (None, None)
            try:
                if Path(j["log"]).exists():
                    br, py = parse_log_for_metrics(j["log"])
            except Exception:
                pass
            row = {"group":j["group"], "experiment":j["exp"], "sequence":j["seq"], "qp":j["qp"],
                   "bitrate_kbps": br, "psnrY_dB": py, "status": status, "log": j["log"]}
            rows.append(row)
            # Progressive print
            print(f"[{status:8s}] {j['group']} | {j['exp']} | {j['seq']} | QP{j['qp']}")

    # Write outputs
    csv_path = Path(args.csv)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB","status","log"])
        w.writeheader()
        for r in rows: w.writerow(r)

    manifest = {"yaml": args.yaml, "qps": qps, "frames": frames_override, "nobitstream": nobit,
                "jobs": jobs, "skip_baselines": list(skip_baselines), "inherit": inherit_map}
    Path(args.manifest).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[OK] Wrote:", csv_path)
    print("[OK] Manifest:", args.manifest)

if __name__ == "__main__":
    main()

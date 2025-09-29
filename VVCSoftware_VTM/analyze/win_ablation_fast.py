
# win_ablation_fast.py
# Usage:
#   pip install pyyaml numpy
#   python win_ablation_fast.py --yaml your_experiment_ablation.yaml --workers 24 --topk 5
import argparse, os, sys, shlex, subprocess, json, math, statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml

from vtm_logparser_win import parse_log_for_metrics
from bdrate_win import bd_rate

CREATE_BELOW_NORMAL = 0x00004000

def quote_win(p: str) -> str:
    if p is None: return ""
    p = str(p)
    if " " in p or "(" in p or ")" in p:
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
    full = base + fixed_args + args_list
    cmd = " ".join(full) + f" > {quote_win(str(log_path))} 2>&1"
    return cmd, bitstream, log_path

def run_cmd(cmd):
    try:
        rc = subprocess.call(cmd, shell=True, creationflags=CREATE_BELOW_NORMAL)
        return rc
    except Exception:
        return -1

def average(lst):
    lst2=[x for x in lst if x is not None]
    return sum(lst2)/len(lst2) if lst2 else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--qps", default="27,32,37", help="Coarse QPs, CSV (3 points recommended)")
    ap.add_argument("--frames", type=int, default=16, help="Frames per run in coarse stage")
    ap.add_argument("--nobitstream", action="store_true", help="Send bitstreams to NUL")
    ap.add_argument("--phase", choices=["perf_add","perf_ablate","speed_add","speed_ablate","all"], default="all")
    ap.add_argument("--topk", type=int, default=5, help="Top-K experiments per group to keep")
    ap.add_argument("--out_yaml", default="experiment_shortlist.yaml")
    ap.add_argument("--summary", default="ablation_summary_coarse.csv")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))
    vtm_bin = cfg["vtm_bin"]; base_cfg = cfg["base_cfg"]
    out_root = Path(cfg.get("output_dir","./runs_out_ablation"))
    fixed_args = cfg.get("fixed_args", [])
    sequences = cfg["sequences"]
    coarse_qps = [int(x) for x in args.qps.split(",")]

    # Build experiment groups per phase
    wanted_keys = ["baselines","perf_add","perf_ablate","speed_add","speed_ablate"]
    groups = []
    for k in wanted_keys:
        if k in cfg:
            if args.phase != "all" and k != "baselines" and k != args.phase:
                continue
            groups.append((k, cfg[k]))

    # Baseline(s)
    baseline_defs = cfg.get("baselines", [])
    if not baseline_defs:
        print("No baselines defined.")
        sys.exit(2)
    # Choose anchor
    anchor_name = None
    for b in baseline_defs:
        if "Ref" in b["name"]:
            anchor_name = b["name"]; break
    if anchor_name is None:
        anchor_name = baseline_defs[0]["name"]

    # Prepare jobs: run baselines and chosen groups with coarse settings
    jobs = []
    for seq in sequences:
        for b in baseline_defs:
            for qp in coarse_qps:
                out_dir = out_root / "COARSE" / "baselines" / b["name"] / seq["name"] / f"QP{qp}"
                cmd, bs, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, b.get("args",[]),
                                          out_dir, frames_override=args.frames, nobitstream=args.nobitstream)
                jobs.append(("baseline", b["name"], seq["name"], qp, cmd, str(logp)))

    for (group_name, items) in groups:
        if group_name == "baselines": continue
        for seq in sequences:
            for it in items:
                for qp in coarse_qps:
                    out_dir = out_root / "COARSE" / group_name / it["name"] / seq["name"] / f"QP{qp}"
                    cmd, bs, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, it.get("args",[]),
                                              out_dir, frames_override=args.frames, nobitstream=args.nobitstream)
                    jobs.append((group_name, it["name"], seq["name"], qp, cmd, str(logp)))

    # Randomize job order to better fill cores
    import random
    random.shuffle(jobs)

    # Run in parallel
    print(f"[INFO] Coarse stage: {len(jobs)} runs, qps={coarse_qps}, frames={args.frames}, nobitstream={args.nobitstream}")
    rows_detail = []
    from collections import defaultdict
    rd_anchor = defaultdict(lambda: {"bitrate":{}, "psnr":{}})
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut2job = {ex.submit(run_cmd, j[4]): j for j in jobs}
        for fut in as_completed(fut2job):
            group_name, exp_name, seq_name, qp, cmd, logp = fut2job[fut]
            rc = fut.result()
            if rc != 0:
                print(f"[WARN] rc={rc} for {group_name}:{exp_name} {seq_name} QP{qp}")
            br, py = (None, None)
            if Path(logp).exists():
                br, py = parse_log_for_metrics(logp)
            rows_detail.append({"group": group_name, "experiment": exp_name, "sequence": seq_name, "qp": qp, "bitrate_kbps": br, "psnrY_dB": py})
            if group_name == "baseline" and exp_name == anchor_name and br is not None and py is not None:
                rd_anchor[seq_name]["bitrate"][qp] = br
                rd_anchor[seq_name]["psnr"][qp] = py

    # Compute BD-Rate vs anchor for each experiment/sequence
    rows_summary = []
    exp_scores = {}  # exp -> list of bd across sequences (signed)
    from collections import defaultdict
    exp_scores = defaultdict(list)

    # Collect per experiment RD data
    exp_rd = defaultdict(lambda: defaultdict(lambda: {"bitrate":{}, "psnr":{}}))
    for r in rows_detail:
        if r["group"] == "baseline": continue
        exp = r["experiment"]; seq = r["sequence"]; qp=r["qp"]
        if r["bitrate_kbps"] is not None and r["psnrY_dB"] is not None:
            exp_rd[exp][seq]["bitrate"][qp] = r["bitrate_kbps"]
            exp_rd[exp][seq]["psnr"][qp]    = r["psnrY_dB"]

    for exp, per_seq in exp_rd.items():
        for seq, rd in per_seq.items():
            ref = rd_anchor.get(seq)
            if not ref: continue
            # Find common QPs
            qps_ref = sorted(ref["bitrate"].keys())
            qps_tst = sorted(rd["bitrate"].keys())
            use_qps = [q for q in [min(qps_ref), statistics.median(qps_ref), max(qps_ref)] if q in qps_ref and q in qps_tst]
            if len(use_qps) < 3:
                bd = None
            else:
                R1 = [ref["bitrate"][q] for q in use_qps]
                P1 = [ref["psnr"][q] for q in use_qps]
                R2 = [rd["bitrate"][q] for q in use_qps]
                P2 = [rd["psnr"][q] for q in use_qps]
                try:
                    bd = bd_rate(R1,P1,R2,P2)
                except Exception as e:
                    bd = None
            rows_summary.append({"experiment": exp, "sequence": seq, "bd_rate_psnrY_percent": bd, "qps_used": ",".join(map(str,use_qps)) if len(use_qps)>=1 else ""})
            if bd is not None: exp_scores[exp].append(bd)

    # Rank experiments by average BD-Rate across sequences (lower is better for "perf_add"; higher penalty for "perf_ablate")
    # We need to know which group each experiment belonged to:
    exp2group={}
    for (group_name, items) in groups:
        if group_name=="baselines": continue
        for it in items:
            exp2group[it["name"]] = group_name

    # aggregate per group
    from collections import defaultdict
    group_rank = defaultdict(list)
    for exp, arr in exp_scores.items():
        avg = sum(arr)/len(arr) if arr else None
        grp = exp2group.get(exp,"unknown")
        group_rank[grp].append((exp, avg, len(arr)))

    shortlist = {}
    for grp, lst in group_rank.items():
        # remove None
        lst2 = [(e,avg,n) for (e,avg,n) in lst if avg is not None and n>=1]
        if grp in ["perf_add", "speed_add"]:
            # more negative is better (savings vs Baseline_Min typically)
            lst2.sort(key=lambda x: x[1])  # ascending
        else:
            # ablate groups: more positive means big penalty -> important tool to keep
            lst2.sort(key=lambda x: -x[1]) # descending
        keep = [e for (e,avg,n) in lst2[:args.topk]]
        shortlist[grp] = keep

    # Write coarse CSVs
    det_csv = Path("ablation_detailed_coarse.csv")
    with det_csv.open("w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB"])
        w.writeheader()
        for r in rows_detail: w.writerow(r)

    sum_csv = Path(args.summary)
    with sum_csv.open("w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=["experiment","sequence","bd_rate_psnrY_percent","qps_used"])
        w.writeheader()
        for r in rows_summary: w.writerow(r)

    # Build shortlist YAML
    src = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))
    out = {
        "vtm_bin": src["vtm_bin"],
        "base_cfg": src["base_cfg"],
        "output_dir": src.get("output_dir","./runs_out_ablation"),
        "qps": src.get("qps",[37,32,27,22]),   # full set for confirm stage
        "fixed_args": src.get("fixed_args",[]),
        "sequences": src["sequences"],
        "baselines": src.get("baselines",[])
    }
    for grp in ["perf_add","perf_ablate","speed_add","speed_ablate"]:
        if grp in src and grp in shortlist and shortlist[grp]:
            src_items = {it["name"]: it for it in src[grp]}
            out[grp] = [src_items[name] for name in shortlist[grp] if name in src_items]

    with Path(args.out_yaml).open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False)

    # Write a JSON report
    report = {
        "anchor": anchor_name,
        "qps_coarse": coarse_qps,
        "frames_coarse": args.frames,
        "nobitstream": args.nobitstream,
        "topk": args.topk,
        "shortlist": shortlist,
        "detail_csv": str(det_csv),
        "summary_csv": str(sum_csv),
        "out_yaml": args.out_yaml
    }
    Path("coarse_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] Coarse summary:", sum_csv)
    print("[OK] Shortlist YAML:", args.out_yaml)
    print("[OK] Report JSON:", "coarse_report.json")

if __name__ == "__main__":
    main()

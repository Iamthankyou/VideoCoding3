
# win_ablation_runner.py
# Usage:
#   pip install pyyaml numpy
#   python win_ablation_runner.py --yaml your_experiment_ablation.yaml --workers 28
import argparse, os, sys, shlex, subprocess, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from vtm_logparser_win import parse_log_for_metrics
from bdrate_win import bd_rate

CREATE_BELOW_NORMAL = 0x00004000  # Windows process priority hint

def quote_win(p: str) -> str:
    # Properly quote Windows paths with spaces/backslashes for cmd.exe
    if not p:
        return p
    p = str(p)
    if " " in p or "(" in p or ")" in p:
        return f'"{p}"'
    return p

def build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, args_list, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    bitstream = out_dir / f"{seq['name']}_QP{qp}.vvc"
    log_path  = out_dir / f"{seq['name']}_QP{qp}.log"

    # Compose full command for EncoderApp
    base = [
        quote_win(vtm_bin), "-c", quote_win(base_cfg),
        "-i", quote_win(seq['yuv']), "-wdt", str(seq['width']), "-hgt", str(seq['height']),
        "-fr", str(seq['fps']), "-f", str(seq['frames']), "-q", str(qp),
        "-b", quote_win(str(bitstream)),
    ]
    # fixed args come first, then experiment args
    full = base + fixed_args + args_list
    cmd = " ".join(full) + f" > {quote_win(str(log_path))} 2>&1"
    return cmd, bitstream, log_path

def run_cmd(cmd):
    try:
        rc = subprocess.call(cmd, shell=True, creationflags=CREATE_BELOW_NORMAL)
        return rc
    except Exception as e:
        return -1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True)
    ap.add_argument("--workers", type=int, default=28, help="Max parallel processes (leave headroom on 32T CPU)")
    ap.add_argument("--summary", default="ablation_summary_win.csv")
    ap.add_argument("--phase", choices=["perf_add","perf_ablate","speed_add","speed_ablate","all"], default="all")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))

    vtm_bin = cfg["vtm_bin"]
    base_cfg = cfg["base_cfg"]
    out_root = Path(cfg.get("output_dir","./runs_out_ablation"))
    qps = cfg.get("qps", [37,32,27,22])
    fixed_args = cfg.get("fixed_args", [])
    sequences = cfg["sequences"]

    # Build experiment groups
    groups = []
    order = ["baselines","perf_add","perf_ablate","speed_add","speed_ablate"]
    for k in order:
        if k in cfg:
            if k in ["perf_add","perf_ablate","speed_add","speed_ablate"] and args.phase != "all" and args.phase != k:
                continue
            groups.append((k, cfg[k]))

    # Run baseline(s) first (used as anchors)
    baseline_defs = cfg.get("baselines", [])
    if not baseline_defs:
        print("No 'baselines' defined; please add at least one anchor (Baseline_Ref).")
        sys.exit(2)

    # Prepare a mapping to collect RD points by (anchor_name, seq_name)
    rd_anchor = {}  # (anchor, seq_name) -> {"bitrate": {qp:val}, "psnr": {qp:val}}
    results_rows = []

    # Build job list
    jobs = []
    for seq in sequences:
        for b in baseline_defs:
            for qp in qps:
                out_dir = out_root / "baselines" / b["name"] / seq["name"] / f"QP{qp}"
                cmd, bs, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, b.get("args",[]), out_dir)
                jobs.append(("baseline", b["name"], seq["name"], qp, cmd, str(logp)))

    # Add other groups
    for (group_name, items) in groups:
        if group_name == "baselines":
            continue
        for seq in sequences:
            for it in items:
                for qp in qps:
                    out_dir = out_root / group_name / it["name"] / seq["name"] / f"QP{qp}"
                    cmd, bs, logp = build_cmd(vtm_bin, base_cfg, seq, qp, fixed_args, it.get("args",[]), out_dir)
                    jobs.append((group_name, it["name"], seq["name"], qp, cmd, str(logp)))

    # Run in parallel
    print(f"[INFO] Launching {len(jobs)} encodes with up to {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut2job = {ex.submit(run_cmd, j[4]): j for j in jobs}
        for fut in as_completed(fut2job):
            group_name, exp_name, seq_name, qp, cmd, logp = fut2job[fut]
            rc = fut.result()
            if rc != 0:
                print(f"[WARN] Non-zero exit for {group_name}:{exp_name} {seq_name} QP{qp} (rc={rc})")
            # Parse metrics if log exists
            br, py = (None, None)
            if Path(logp).exists():
                br, py = parse_log_for_metrics(logp)

            # Store baseline metrics
            if group_name == "baseline":
                key = (exp_name, seq_name)
                rd = rd_anchor.setdefault(key, {"bitrate": {}, "psnr": {}})
                if br is not None and py is not None:
                    rd["bitrate"][qp] = br; rd["psnr"][qp] = py

            # Write immediate row for tracking (actual BD-Rate computed later)
            results_rows.append({
                "group": group_name, "experiment": exp_name, "sequence": seq_name, "qp": qp,
                "bitrate_kbps": br, "psnrY_dB": py, "log": logp
            })

    # Compute BD-Rate for each experiment vs Baseline_Ref (if present)
    anchor_name = None
    for b in baseline_defs:
        if "Ref" in b["name"]:
            anchor_name = b["name"]; break
    if anchor_name is None:
        anchor_name = baseline_defs[0]["name"]
        print(f"[INFO] Using first baseline as anchor: {anchor_name}")

    # Aggregate per experiment and sequence
    rows_summary = []
    # Collect experiment -> seq -> list of points
    from collections import defaultdict
    exp_collect = defaultdict(lambda: defaultdict(lambda: {"bitrate": {}, "psnr": {}}))
    for r in results_rows:
        if r["group"] == "baseline":
            continue
        exp = r["experiment"]; seq = r["sequence"]; qp = r["qp"]
        if r["bitrate_kbps"] is not None and r["psnrY_dB"] is not None:
            exp_collect[exp][seq]["bitrate"][qp] = r["bitrate_kbps"]
            exp_collect[exp][seq]["psnr"][qp] = r["psnrY_dB"]

    for exp, per_seq in exp_collect.items():
        for seq, rd in per_seq.items():
            key_anchor = (anchor_name, seq)
            if key_anchor not in rd_anchor:
                continue
            ref = rd_anchor[key_anchor]
            # Sort QPs in ascending order for consistent mapping
            qps_sorted = sorted(set(list(ref["bitrate"].keys()) + list(rd["bitrate"].keys())))
            # Use only QPs available in both
            qps_use = [q for q in qps_sorted if q in ref["bitrate"] and q in rd["bitrate"]]
            if len(qps_use) < 3:
                bd = None
            else:
                refR = [ref["bitrate"][q] for q in qps_use]
                refP = [ref["psnr"][q]    for q in qps_use]
                tstR = [rd["bitrate"][q]  for q in qps_use]
                tstP = [rd["psnr"][q]     for q in qps_use]
                try:
                    bd = bd_rate(refR, refP, tstR, tstP)
                except Exception as e:
                    bd = None
            rows_summary.append({
                "anchor": anchor_name, "experiment": exp, "sequence": seq,
                "bd_rate_psnrY_percent": bd,
                "qps_used": ",".join(map(str, qps_use))
            })

    # Write detailed rows and summary
    det_csv = Path("ablation_detailed_win.csv")
    with det_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB","log"])
        w.writeheader()
        for r in results_rows: w.writerow(r)

    sum_csv = Path(args.summary)
    with sum_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["anchor","experiment","sequence","bd_rate_psnrY_percent","qps_used"])
        w.writeheader()
        for r in rows_summary: w.writerow(r)

    print("[OK] Detailed:", det_csv)
    print("[OK] Summary :", sum_csv)

if __name__ == "__main__":
    main()

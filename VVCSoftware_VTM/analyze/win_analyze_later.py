
# win_analyze_later.py
# Compute BD-Rate per experiment when logs are available.
# You can run it multiple times; missing anchors/experiments are marked PENDING.
#
# Examples:
#   pip install pyyaml numpy
#   python win_analyze_later.py --yaml experiment_ablation.yaml --csv quickfire_runs.csv ^
#       --out quickfire_summary.csv --anchor-ref-name Baseline_Ref --anchor-min-name Baseline_Min
#   # Optional watch mode (refresh every 60s):
#   python win_analyze_later.py --yaml experiment_ablation.yaml --csv quickfire_runs.csv --watch 60
import argparse, time, csv, json
from pathlib import Path
from collections import defaultdict, OrderedDict

import yaml
from bdrate_win import bd_rate

def load_runs(csv_path):
    rows = []
    if not Path(csv_path).exists(): return rows
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # cast
            for k in ["qp","bitrate_kbps","psnrY_dB"]:
                if k in row and row[k] not in ("",None):
                    try:
                        row[k] = float(row[k]) if k!="qp" else int(row[k])
                    except Exception:
                        row[k] = None
            rows.append(row)
    return rows

def pick_anchor_name(baselines, prefer_contains):
    # find the baseline whose name contains prefer_contains (case-insensitive)
    for b in baselines:
        if prefer_contains.lower() in b["name"].lower():
            return b["name"]
    # fallback to first baseline
    return baselines[0]["name"] if baselines else None

def summarize(yaml_path, csv_path, out_path, anchor_ref_name=None, anchor_min_name=None):
    cfg = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    baselines = cfg.get("baselines", [])
    # anchors
    if anchor_ref_name is None:
        anchor_ref_name = pick_anchor_name(baselines, "Ref") or (baselines[0]["name"] if baselines else None)
    if anchor_min_name is None:
        anchor_min_name = pick_anchor_name(baselines, "Min") or (baselines[0]["name"] if baselines else None)

    rows = load_runs(csv_path)
    # Collect RD points by (anchor_name, sequence)
    anchor_rd = defaultdict(lambda: {"R":{}, "P":{}})
    for r in rows:
        if r["group"] != "baseline": continue
        aname = r["experiment"]
        if aname not in (anchor_ref_name, anchor_min_name): continue
        if r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        anchor_rd[(aname, r["sequence"])]["R"][r["qp"]] = r["bitrate_kbps"]
        anchor_rd[(aname, r["sequence"])]["P"][r["qp"]] = r["psnrY_dB"]

    # Collect experiment RD points
    exp_rd = defaultdict(lambda: defaultdict(lambda: {"R":{}, "P":{}, "group":""}))
    for r in rows:
        if r["group"] == "baseline": continue
        key = (r["experiment"], r["sequence"])
        if r["bitrate_kbps"] is not None and r["psnrY_dB"] is not None:
            exp_rd[key]["R"][r["qp"]] = r["bitrate_kbps"]
            exp_rd[key]["P"][r["qp"]] = r["psnrY_dB"]
            exp_rd[key]["group"] = r["group"]

    # Decide anchor per group
    group2anchor = {
        "perf_ablate": anchor_ref_name,
        "perf_add":    anchor_min_name,
        "speed_ablate":anchor_ref_name,
        "speed_add":   anchor_min_name,
    }

    out_rows = []
    for (exp, seq), rd in exp_rd.items():
        grp = rd["group"]
        anchor_name = group2anchor.get(grp, anchor_ref_name)
        ref = anchor_rd.get((anchor_name, seq))
        status = "PENDING"
        bd = None; qps_used = ""
        if ref:
            # Use intersection of available QPs
            common = sorted(set(ref["R"].keys()) & set(rd["R"].keys()))
            if len(common) >= 3:
                R1 = [ref["R"][q] for q in common]
                P1 = [ref["P"][q] for q in common]
                R2 = [rd["R"][q] for q in common]
                P2 = [rd["P"][q] for q in common]
                try:
                    bd = bd_rate(R1,P1,R2,P2)
                    status = "OK"
                    qps_used = ",".join(map(str, common))
                except Exception as e:
                    status = f"BDERR:{e.__class__.__name__}"
            else:
                status = f"NEED_{3-len(common)}_QP"
        out_rows.append({
            "group": grp, "experiment": exp, "sequence": seq,
            "anchor": anchor_name, "bd_rate_psnrY_percent": bd,
            "qps_used": qps_used, "status": status
        })

    # Write
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","anchor","bd_rate_psnrY_percent","qps_used","status"])
        w.writeheader()
        for r in out_rows: w.writerow(r)
    return out_rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True)
    ap.add_argument("--csv", default="quickfire_runs.csv")
    ap.add_argument("--out", default="quickfire_summary.csv")
    ap.add_argument("--anchor-ref-name", default=None, help="Override anchor baseline name for perf_ablate/speed_ablate")
    ap.add_argument("--anchor-min-name", default=None, help="Override anchor baseline name for perf_add/speed_add")
    ap.add_argument("--watch", type=int, default=0, help="If >0, rerun summary every N seconds")
    args = ap.parse_args()

    if args.watch > 0:
        print(f"[INFO] Watching every {args.watch}s. Press Ctrl+C to stop.")
        try:
            while True:
                out_rows = summarize(args.yaml, args.csv, args.out, args.anchor_ref_name, args.anchor_min_name)
                ok = sum(1 for r in out_rows if r["status"]=="OK")
                pend = sum(1 for r in out_rows if r["status"]!="OK")
                print(f"[{time.strftime('%H:%M:%S')}] OK={ok}, PENDING={pend}. Wrote {args.out}")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            pass
    else:
        out_rows = summarize(args.yaml, args.csv, args.out, args.anchor_ref_name, args.anchor_min_name)
        ok = sum(1 for r in out_rows if r["status"]=="OK")
        pend = sum(1 for r in out_rows if r["status"]!="OK")
        print(f"[OK] Summary written: {args.out} (OK={ok}, PENDING={pend})")

if __name__ == "__main__":
    main()

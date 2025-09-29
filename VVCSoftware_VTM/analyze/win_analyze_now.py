
# win_analyze_now.py
# Usage:
#   pip install pyyaml numpy
#   python win_analyze_now.py --yaml experiment_ablation.yaml --csv quickfire_runs.csv \
#     --out quickfire_summary_now.csv --overview quickfire_overview_now.csv \
#     --anchor-ref-name Baseline_Ref --anchor-min-name Baseline_Min \
#     --allow-2qp-estimate --fallback-perf-add-to-ref
import argparse, csv, json, statistics
from pathlib import Path
from collections import defaultdict

import yaml
from bdrate_win import bd_rate

def load_runs(csv_path):
    rows = []
    if not Path(csv_path).exists(): return rows
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # cast
            try: row["qp"] = int(row["qp"])
            except: row["qp"] = None
            for k in ["bitrate_kbps","psnrY_dB"]:
                try: row[k] = float(row[k]) if row[k] not in ("",None) else None
                except: row[k] = None
            rows.append(row)
    return rows

def pick_anchor_name(baselines, prefer_contains):
    for b in baselines:
        if prefer_contains.lower() in b["name"].lower():
            return b["name"]
    return baselines[0]["name"] if baselines else None

def bd_rate_2qp_linear(refR, refP, tstR, tstP):
    """
    2-QP fallback estimate:
    - Fit line in log-rate domain: logR = a*PSNR + b using 2 points
    - Integrate difference across the overlapping PSNR range (just the segment)
    - Return % as in BD-Rate
    """
    import numpy as np
    rR = np.array(refR); pR = np.array(refP)
    rT = np.array(tstR); pT = np.array(tstP)
    lR = np.log(rR); lT = np.log(rT)
    # line coefficients for ref and test
    def line(x1,y1,x2,y2):
        a = (y2 - y1) / (x2 - x1)
        b = y1 - a*x1
        return a,b
    aR,bR = line(pR[0], lR[0], pR[1], lR[1])
    aT,bT = line(pT[0], lT[0], pT[1], lT[1])
    pmin = max(min(pR), min(pT)); pmax = min(max(pR), max(pT))
    if pmax <= pmin: raise ValueError("PSNR range disjoint")
    # integrate exp(line) over [pmin,pmax]: ∫ exp(a x + b) dx = (1/a) exp(b) (exp(a x)) ...
    import math
    def I(a,b,x): return (math.exp(b)/a) * math.exp(a*x) if abs(a) > 1e-12 else math.exp(b)*x
    intR = I(aR,bR,pmax) - I(aR,bR,pmin)
    intT = I(aT,bT,pmax) - I(aT,bT,pmin)
    avgR = intR / (pmax - pmin); avgT = intT / (pmax - pmin)
    return float((avgT/avgR - 1.0)*100.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True)
    ap.add_argument("--csv", default="quickfire_runs.csv")
    ap.add_argument("--out", default="quickfire_summary_now.csv")
    ap.add_argument("--overview", default="quickfire_overview_now.csv")
    ap.add_argument("--anchor-ref-name", default=None)
    ap.add_argument("--anchor-min-name", default=None)
    ap.add_argument("--allow-2qp-estimate", action="store_true")
    ap.add_argument("--fallback-perf-add-to-ref", action="store_true",
                    help="If Baseline_Min anchor missing for a sequence, temporarily use Baseline_Ref for perf_add on that sequence")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text(encoding="utf-8"))
    baselines = cfg.get("baselines", [])
    # anchors
    anchor_ref = args.anchor_ref_name or pick_anchor_name(baselines, "Ref")
    anchor_min = args.anchor_min_name or pick_anchor_name(baselines, "Min") or anchor_ref

    rows = load_runs(args.csv)

    # Collect anchors
    anchor_rd = defaultdict(lambda: {"R":{}, "P":{}})
    for r in rows:
        if r["group"] != "baseline": continue
        aname = r["experiment"]
        if aname not in (anchor_ref, anchor_min): continue
        if r["qp"] is None or r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        anchor_rd[(aname, r["sequence"])]["R"][r["qp"]] = r["bitrate_kbps"]
        anchor_rd[(aname, r["sequence"])]["P"][r["qp"]] = r["psnrY_dB"]

    # Collect experiment RD points
    exp_rd = defaultdict(lambda: defaultdict(lambda: {"R":{}, "P":{}, "group":""}))
    for r in rows:
        if r["group"] == "baseline": continue
        key = (r["experiment"], r["sequence"])
        if r["qp"] is None or r["bitrate_kbps"] is None or r["psnrY_dB"] is None: 
            continue
        exp_rd[key]["R"][r["qp"]] = r["bitrate_kbps"]
        exp_rd[key]["P"][r["qp"]] = r["psnrY_dB"]
        exp_rd[key]["group"] = r["group"]

    # Decide default anchor per group
    group2anchor = {"perf_ablate": anchor_ref, "speed_ablate": anchor_ref,
                    "perf_add": anchor_min, "speed_add": anchor_min}

    # Per-sequence summary rows
    out_rows = []
    # Aggregation
    agg = defaultdict(list)

    for (exp, seq), rd in exp_rd.items():
        grp = rd["group"]
        anchor_name = group2anchor.get(grp, anchor_ref)
        # find anchor for this sequence
        ref = anchor_rd.get((anchor_name, seq))
        anchor_used = anchor_name
        anchor_fallback = False
        if ref is None and grp == "perf_add" and args.fallback-perf-add-to-ref:
            # fallback to Ref if Min missing
            ref = anchor_rd.get((anchor_ref, seq))
            anchor_used = anchor_ref
            anchor_fallback = True

        status = "PENDING"; bd = None; qps_used = ""; approx = ""
        if ref:
            common = sorted(set(ref["R"].keys()) & set(rd["R"].keys()))
            if len(common) >= 3:
                R1 = [ref["R"][q] for q in common]
                P1 = [ref["P"][q] for q in common]
                R2 = [rd ["R"][q] for q in common]
                P2 = [rd ["P"][q] for q in common]
                try:
                    bd = bd_rate(R1,P1,R2,P2)
                    status = "OK"
                    qps_used = ",".join(map(str, common))
                except Exception as e:
                    status = f"BDERR:{e.__class__.__name__}"
            elif len(common) == 2 and args.allow_2qp_estimate:
                Q = common
                R1 = [ref["R"][q] for q in Q]
                P1 = [ref["P"][q] for q in Q]
                R2 = [rd ["R"][q] for q in Q]
                P2 = [rd ["P"][q] for q in Q]
                try:
                    bd = bd_rate_2qp_linear(R1,P1,R2,P2)
                    status = "OK_EST2QP"
                    qps_used = ",".join(map(str, Q))
                    approx = "2QP"
                except Exception as e:
                    status = f"BDERR2:{e.__class__.__name__}"
            else:
                need = max(0, 3 - len(common))
                status = f"NEED_{need}_QP"
        else:
            status = "NO_ANCHOR"

        out_rows.append({
            "group": grp, "experiment": exp, "sequence": seq,
            "anchor": anchor_used, "fallback_anchor": "Y" if anchor_fallback else "",
            "bd_rate_psnrY_percent": bd, "qps_used": qps_used,
            "approx": approx, "status": status
        })
        if bd is not None and status in ("OK","OK_EST2QP"):
            agg[(grp,exp)].append(bd)

    # Write per-sequence summary
    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","anchor","fallback_anchor","bd_rate_psnrY_percent","qps_used","approx","status"])
        w.writeheader()
        for r in out_rows: w.writerow(r)

    # Overview per experiment
    over_path = Path(args.overview)
    with over_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","mean_bd_rate","n_sequences_used"])
        w.writeheader()
        for (grp,exp), arr in agg.items():
            mean = sum(arr)/len(arr) if arr else None
            w.writerow({"group":grp, "experiment":exp, "mean_bd_rate": mean, "n_sequences_used": len(arr)})

    print(f"[OK] Wrote {out_path} and {over_path}")

if __name__ == "__main__":
    main()

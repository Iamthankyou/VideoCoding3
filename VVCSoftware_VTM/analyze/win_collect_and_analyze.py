
# win_collect_and_analyze.py
# Crawl an output root (e.g., runs_out_ablation\COARSE), parse *.log files,
# reconstruct runs, then compute BD-Rate per experiment.
#
# Usage (Windows PowerShell/CMD):
#   pip install numpy pyyaml
#   python win_collect_and_analyze.py --root "C:\path\to\runs_out_ablation\COARSE" ^
#     --out quickfire_summary_from_logs.csv --overview quickfire_overview_from_logs.csv ^
#     --anchor-ref-name Baseline_Ref --anchor-min-name Baseline_Min ^
#     --allow-2qp-estimate --fallback-perf-add-to-ref

import argparse, re, csv
from pathlib import Path
from collections import defaultdict

def parse_log_for_metrics(log_path: str):
    try:
        t = Path(log_path).read_text(errors="ignore")
    except Exception:
        return None, None
    import re
    br = None; py = None
    for pat in [r'Bitrate\s*\(kbps\)\s*[:=]\s*([0-9.]+)', r'Bitrate\s*[:=]\s*([0-9.]+)\s*kbps']:
        m = re.search(pat, t, flags=re.I)
        if m: br = float(m.group(1)); break
    for pat in [r'Y-?PSNR\s*\(dB\)\s*[:=]\s*([0-9.]+)', r'PSNR[-\s]*Y\s*[:=]\s*([0-9.]+)']:
        m = re.search(pat, t, flags=re.I)
        if m: py = float(m.group(1)); break
    return br, py

def bd_rate(ref_bitrate, ref_psnr, test_bitrate, test_psnr):
    import numpy as np
    lR1 = np.log(np.array(ref_bitrate)); lR2 = np.log(np.array(test_bitrate))
    P1  = np.array(ref_psnr);            P2  = np.array(test_psnr)
    c1 = np.polyfit(P1, lR1, 3);         c2 = np.polyfit(P2, lR2, 3)
    pmin = max(min(P1), min(P2)); pmax = min(max(P1), max(P2))
    if pmax <= pmin: raise ValueError("PSNR ranges do not overlap.")
    I1 = np.polyint(c1); I2 = np.polyint(c2)
    int1 = np.polyval(I1, pmax) - np.polyval(I1, pmin)
    int2 = np.polyval(I2, pmax) - np.polyval(I2, pmin)
    avg1 = int1 / (pmax - pmin); avg2 = int2 / (pmax - pmin)
    return float((np.exp(avg2)/np.exp(avg1) - 1.0) * 100.0)

def bd_rate_2qp_linear(refR, refP, tstR, tstP):
    import numpy as np, math
    rR = np.array(refR); pR = np.array(refP)
    rT = np.array(tstR); pT = np.array(tstP)
    lR = np.log(rR); lT = np.log(rT)
    def line(x1,y1,x2,y2):
        a = (y2 - y1) / (x2 - x1)
        b = y1 - a*x1
        return a,b
    aR,bR = line(pR[0], lR[0], pR[1], lR[1])
    aT,bT = line(pT[0], lT[0], pT[1], lT[1])
    pmin = max(min(pR), min(pT)); pmax = min(max(pR), max(pT))
    if pmax <= pmin: raise ValueError("PSNR range disjoint")
    def I(a,b,x): return (math.exp(b)/a) * math.exp(a*x) if abs(a) > 1e-12 else math.exp(b)*x
    intR = I(aR,bR,pmax) - I(aR,bR,pmin)
    intT = I(aT,bT,pmax) - I(aT,bT,pmin)
    avgR = intR / (pmax - pmin); avgT = intT / (pmax - pmin)
    return float((avgT/avgR - 1.0)*100.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Folder that contains logs (e.g. ...\\runs_out_ablation\\COARSE)")
    ap.add_argument("--out", default="quickfire_summary_from_logs.csv")
    ap.add_argument("--overview", default="quickfire_overview_from_logs.csv")
    ap.add_argument("--anchor-ref-name", default="Baseline_Ref")
    ap.add_argument("--anchor-min-name", default="Baseline_Min")
    ap.add_argument("--allow-2qp-estimate", action="store_true")
    ap.add_argument("--fallback-perf-add-to-ref", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"ROOT not found: {root}")

    rows = []
    qp_re = re.compile(r"^QP(\d+)$", re.I)

    for p in root.rglob("*.log"):
        try:
            qp_dir = p.parent.name
            m = qp_re.match(qp_dir)
            if not m:
                continue
            qp = int(m.group(1))
            seq = p.parent.parent.name
            parent2 = p.parent.parent.parent.name
            parent3 = p.parent.parent.parent.parent.name

            if parent3.lower() == "baselines":
                group = "baseline"
                exp   = parent2
            else:
                group = parent3
                exp   = parent2

            br,py = parse_log_for_metrics(str(p))
            rows.append({"group":group, "experiment":exp, "sequence":seq, "qp":qp,
                         "bitrate_kbps": br, "psnrY_dB": py, "log": str(p)})
        except Exception:
            pass

    # Snapshot for debugging
    with open("collected_runs_snapshot.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB","log"])
        w.writeheader()
        for r in rows: w.writerow(r)

    # Build anchors
    anchor_ref = args.anchor_ref_name
    anchor_min = args.anchor_min_name
    from collections import defaultdict
    anchor_rd = defaultdict(lambda: {"R":{}, "P":{}})
    for r in rows:
        if r["group"] != "baseline": continue
        if r["experiment"] not in (anchor_ref, anchor_min): continue
        if r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        anchor_rd[(r["experiment"], r["sequence"])]["R"][r["qp"]] = r["bitrate_kbps"]
        anchor_rd[(r["experiment"], r["sequence"])]["P"][r["qp"]] = r["psnrY_dB"]

    # Collect experiments
    exp_rd = defaultdict(lambda: defaultdict(lambda: {"R":{}, "P":{}, "group":""}))
    for r in rows:
        if r["group"] == "baseline": continue
        key = (r["experiment"], r["sequence"])
        if r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        exp_rd[key]["R"][r["qp"]] = r["bitrate_kbps"]
        exp_rd[key]["P"][r["qp"]] = r["psnrY_dB"]
        exp_rd[key]["group"] = r["group"]

    group2anchor = {"perf_ablate": anchor_ref, "speed_ablate": anchor_ref,
                    "perf_add": anchor_min, "speed_add": anchor_min}

    # Compute BD-Rate
    out_rows = []
    agg = defaultdict(list)
    for (exp, seq), rd in exp_rd.items():
        grp = rd["group"]
        anchor_name = group2anchor.get(grp, anchor_ref)
        ref = anchor_rd.get((anchor_name, seq))
        anchor_used = anchor_name
        anchor_fallback = False
        if ref is None and grp == "perf_add" and args.fallback_perf_add_to_ref:
            ref = anchor_rd.get((anchor_ref, seq))
            anchor_used = anchor_ref
            anchor_fallback = True

        status = "PENDING"; bd = None; qps_used = ""; approx=""
        if ref:
            common = sorted(set(ref["R"].keys()) & set(rd["R"].keys()))
            if len(common) >= 3:
                R1 = [ref["R"][q] for q in common]; P1 = [ref["P"][q] for q in common]
                R2 = [rd ["R"][q] for q in common]; P2 = [rd ["P"][q] for q in common]
                try:
                    bd = bd_rate(R1,P1,R2,P2)
                    status = "OK"; qps_used = ",".join(map(str,common))
                except Exception as e:
                    status = f"BDERR:{e.__class__.__name__}"
            elif len(common) == 2 and args.allow_2qp_estimate:
                Q = common
                R1 = [ref["R"][q] for q in Q]; P1 = [ref["P"][q] for q in Q]
                R2 = [rd ["R"][q] for q in Q]; P2 = [rd ["P"][q] for q in Q]
                try:
                    bd = bd_rate_2qp_linear(R1,P1,R2,P2)
                    status = "OK_EST2QP"; qps_used = ",".join(map(str,Q)); approx="2QP"
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

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","anchor","fallback_anchor","bd_rate_psnrY_percent","qps_used","approx","status"])
        w.writeheader()
        for r in out_rows: w.writerow(r)

    with open(args.overview, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","mean_bd_rate","n_sequences_used"])
        w.writeheader()
        for (grp,exp), arr in agg.items():
            mean = sum(arr)/len(arr) if arr else None
            w.writerow({"group":grp, "experiment":exp, "mean_bd_rate": mean, "n_sequences_used": len(arr)})

    print(f"[OK] Summaries written: {args.out} and {args.overview}\nAlso wrote collected_runs_snapshot.csv for debugging.")

if __name__ == "__main__":
    main()

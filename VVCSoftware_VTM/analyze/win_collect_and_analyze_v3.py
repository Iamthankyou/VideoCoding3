
# win_collect_and_analyze_v3.py
# Crawl an output root (e.g., runs_out_ablation\COARSE), parse *.log files (VTM 23.11-friendly),
# reconstruct runs, then compute BD-Rate per experiment (with 2QP fallback & anchor fallback).
#
# Usage (Windows PowerShell/CMD):
#   pip install numpy pyyaml
#   python win_collect_and_analyze_v3.py --root "C:\path\to\runs_out_ablation\COARSE" ^
#     --out quickfire_summary_from_logs.csv --overview quickfire_overview_from_logs.csv ^
#     --anchor-ref-name Baseline_Ref --anchor-min-name Baseline_Min ^
#     --allow-2qp-estimate --fallback-perf-add-to-ref
import argparse, re, csv
from pathlib import Path
from collections import defaultdict

# ---- Parsers ---------------------------------------------------------
POC_Y_BRACKETS  = re.compile(r'\bPOC\b.*?\[.*?Y\s*([0-9]+(?:\.[0-9]+)?)\s*dB', re.I)
POC_Y_PSNR      = re.compile(r'\bPOC\b.*?(?:PSNR|PSNRY)\s*Y[:\s]*([0-9]+(?:\.[0-9]+)?)', re.I)

ANY_BITRATE1    = re.compile(r'Bitrate\s*[:=]\s*([0-9.]+)\s*kbps', re.I)
ANY_BITRATE2    = re.compile(r'Avg\.?\s*bitrate\s*[:=]\s*([0-9.]+)\s*kbps', re.I)

LAYER_HDR = re.compile(r'Total\s+Frames\s*\|\s*Bitrate\s*Y-PSNR', re.I)

def read_text_auto(log_path):
    p = Path(log_path)
    for enc in ("utf-8", "utf-16-le", None):
        try:
            return p.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""

def parse_layer_summary(text):
    m = LAYER_HDR.search(text)
    if not m:
        return None, None
    # take the next non-empty line after header
    idx = m.end()
    tail = text[idx:].splitlines()
    row = None
    for ln in tail:
        s = ln.strip()
        if not s:
            continue
        row = s
        break
    if not row:
        return None, None
    # collapse multiple spaces/tabs into single space
    cols = re.split(r'\s+', row)
    # Find first pair of consecutive floats -> bitrate, Y-PSNR
    flt_idx = None
    for i in range(1, len(cols)-1):
        if re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', cols[i]) and re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', cols[i+1]):
            flt_idx = i
            break
    if flt_idx is None:
        return None, None
    try:
        bitrate = float(cols[flt_idx])
        ypsnr   = float(cols[flt_idx+1])
        return bitrate, ypsnr
    except Exception:
        return None, None

def parse_log_for_metrics(log_path: str):
    text = read_text_auto(log_path)

    # 1) Try Layer summary block first (VTM 23.11)
    br, py = parse_layer_summary(text)

    # 2) If Y not found, compute from POC lines
    if py is None:
        ys = [float(x) for x in POC_Y_BRACKETS.findall(text)]
        if not ys:
            ys = [float(x) for x in POC_Y_PSNR.findall(text)]
        if ys:
            py = sum(ys)/len(ys)

    # 3) If bitrate still None, try generic "bitrate ... kbps" anywhere
    if br is None:
        m = ANY_BITRATE1.search(text) or ANY_BITRATE2.search(text)
        if m:
            br = float(m.group(1))

    return br, py

# ---- BD-Rate helpers --------------------------------------------------------
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
    def I(a,b,x): 
        return (math.exp(b)/a) * math.exp(a*x) if abs(a) > 1e-12 else math.exp(b)*x
    intR = I(aR,bR,pmax) - I(aR,bR,pmin)
    intT = I(aT,bT,pmax) - I(aT,bT,pmin)
    avgR = intR / (pmax - pmin); avgT = intT / (pmax - pmin)
    return float((avgT/avgR - 1.0)*100.0)

# ---- Collector + Analyzer ---------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
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
            exp_or_seq_parent = p.parent.parent.parent
            group_parent = exp_or_seq_parent.parent

            if group_parent.name.lower() == "baselines":
                group = "baseline"
                exp   = exp_or_seq_parent.name
            else:
                group = group_parent.name
                exp   = exp_or_seq_parent.name

            br, py = parse_log_for_metrics(str(p))
            rows.append({"group":group, "experiment":exp, "sequence":seq, "qp":qp,
                         "bitrate_kbps": br, "psnrY_dB": py, "log": str(p)})
        except Exception:
            pass

    # snapshot
    with open("collected_runs_snapshot.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB","log"])
        w.writeheader()
        for r in rows: w.writerow(r)

    # anchors
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

    # experiments
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

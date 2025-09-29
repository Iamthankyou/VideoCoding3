# === win_collect_and_analyze_v4.py (all-in-one) ===
# Crawl root -> parse VTM 23.11 logs -> compute bitrate/PSNR-Y -> BD-Rate -> CSV.
import argparse, re, csv, math
from pathlib import Path
from collections import defaultdict

# -------- Regex / Helpers --------
POC_BITS_LINE   = re.compile(r'\bPOC\b.*?\b([0-9]+)\s+bits\b', re.I)
POC_Y_BRACKETS  = re.compile(r'\bPOC\b.*?\[.*?Y\s*([0-9]+(?:\.[0-9]+)?)\s*dB', re.I)
POC_Y_PSNR      = re.compile(r'\bPOC\b.*?(?:PSNR|PSNRY)\s*Y[:\s]*([0-9]+(?:\.[0-9]+)?)', re.I)
LAYER_HDR       = re.compile(r'Total\s+Frames\s*\|\s*Bitrate\s*Y-PSNR', re.I)
QP_DIR_RE       = re.compile(r'^QP(\d+)$', re.I)

def read_text(p: Path) -> str:
    for enc in ("utf-8", "utf-16-le", None):
        try:
            return p.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return ""

def parse_layer_summary(text: str):
    m = LAYER_HDR.search(text)
    if not m: return None, None
    # hàng ngay sau header, bỏ dòng rỗng
    for ln in text[m.end():].splitlines():
        s = ln.strip()
        if not s: continue
        cols = re.split(r'\s+', s)
        # tìm 2 số float liên tiếp -> bitrate, Y-PSNR (vượt qua token 'a' nếu có)
        for i in range(1, len(cols)-1):
            if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', cols[i]) and re.fullmatch(r'[+-]?\d+(?:\.\d+)?', cols[i+1]):
                try:
                    return float(cols[i]), float(cols[i+1])
                except Exception:
                    pass
        break
    return None, None

def infer_fps_from_seqname(seq: str, fps_default: int):
    # lấy đuôi _50 / _60 / _30 ...
    m = re.search(r'_([0-9]{2,3})$', seq)
    if m: 
        try: return int(m.group(1))
        except: pass
    return fps_default

def parse_log_metrics(log_path: str, seqname: str, fps_default: int):
    text = read_text(Path(log_path))
    br, py = parse_layer_summary(text)

    if py is None:  # fallback: trung bình PSNR-Y theo POC
        ys = [float(x) for x in POC_Y_BRACKETS.findall(text)]
        if not ys:
            ys = [float(x) for x in POC_Y_PSNR.findall(text)]
        if ys:
            py = sum(ys)/len(ys)

    if br is None:  # fallback: tự tính bitrate từ tổng bits theo POC
        bits = [int(x) for x in POC_BITS_LINE.findall(text)]
        if bits:
            fps = infer_fps_from_seqname(seqname, fps_default)
            br = (sum(bits)/max(1,len(bits))) * fps / 1000.0  # kbps
    return br, py

# -------- BD-Rate --------
def bd_rate(refR, refP, tstR, tstP):
    import numpy as np
    lR1, lR2 = np.log(refR), np.log(tstR)
    c1, c2 = np.polyfit(refP, lR1, 3), np.polyfit(tstP, lR2, 3)
    pmin, pmax = max(min(refP), min(tstP)), min(max(refP), max(tstP))
    if pmax <= pmin: 
        raise ValueError("PSNR ranges do not overlap.")
    I1, I2 = np.polyint(c1), np.polyint(c2)
    int1 = np.polyval(I1,pmax) - np.polyval(I1,pmin)
    int2 = np.polyval(I2,pmax) - np.polyval(I2,pmin)
    avg1, avg2 = int1/(pmax-pmin), int2/(pmax-pmin)
    return float((math.exp(avg2)/math.exp(avg1) - 1.0) * 100.0)

def bd_rate_2qp_linear(refR, refP, tstR, tstP):
    import numpy as np
    rR, pR = np.array(refR), np.array(refP)
    rT, pT = np.array(tstR), np.array(tstP)
    lR, lT = np.log(rR), np.log(rT)
    def line(x1,y1,x2,y2):
        a = (y2-y1)/(x2-x1); b = y1 - a*x1; return a,b
    aR,bR = line(pR[0],lR[0],pR[1],lR[1]); aT,bT = line(pT[0],lT[0],pT[1],lT[1])
    pmin, pmax = max(min(pR),min(pT)), min(max(pR),max(pT))
    if pmax <= pmin: 
        raise ValueError("PSNR ranges disjoint")
    import math
    def I(a,b,x): 
        return (math.exp(b)/a)*math.exp(a*x) if abs(a)>1e-12 else math.exp(b)*x
    intR = I(aR,bR,pmax)-I(aR,bR,pmin); intT = I(aT,bT,pmax)-I(aT,bT,pmin)
    avgR = intR/(pmax-pmin);          avgT = intT/(pmax-pmin)
    return float((avgT/avgR - 1.0) * 100.0)

# -------- Main --------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Folder chứa *.log (ví dụ ...\\runs_out_ablation\\COARSE)")
    ap.add_argument("--out", default="quickfire_summary_from_logs.csv")
    ap.add_argument("--overview", default="quickfire_overview_from_logs.csv")
    ap.add_argument("--anchor-ref-name", default="Baseline_Ref")
    ap.add_argument("--anchor-min-name", default="Baseline_Min")
    ap.add_argument("--allow-2qp-estimate", action="store_true", default=True)   # bật mặc định
    ap.add_argument("--no-2qp-estimate", action="store_false", dest="allow_2qp_estimate")
    ap.add_argument("--fallback-perf-add-to-ref", action="store_true", default=True)  # bật mặc định
    ap.add_argument("--no-fallback-perf-add", action="store_false", dest="fallback_perf_add_to_ref")
    ap.add_argument("--fps-default", type=int, default=30, help="fps mặc định nếu tên sequence không có _fps")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"ROOT not found: {root}")

    rows = []
    for p in root.rglob("*.log"):
        qpdir = p.parent.name
        m = QP_DIR_RE.match(qpdir)
        if not m: 
            continue
        qp = int(m.group(1))
        seq = p.parent.parent.name
        exp_or_seq_parent = p.parent.parent.parent
        group_parent      = exp_or_seq_parent.parent

        if group_parent.name.lower() == "baselines":
            group = "baseline"; exp = exp_or_seq_parent.name
        else:
            group = group_parent.name; exp = exp_or_seq_parent.name

        br, py = parse_log_metrics(str(p), seq, args.fps_default)
        rows.append({"group":group,"experiment":exp,"sequence":seq,"qp":qp,
                     "bitrate_kbps":br,"psnrY_dB":py,"log":str(p)})

    # Ảnh chụp đã thu thập
    with open("collected_runs_snapshot.csv","w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","qp","bitrate_kbps","psnrY_dB","log"])
        w.writeheader(); [w.writerow(r) for r in rows]

    # Build RD points cho anchor
    anchor_ref = args.anchor_ref_name
    anchor_min = args.anchor_min_name
    anchor_rd = defaultdict(lambda: {"R":{}, "P":{}})
    for r in rows:
        if r["group"]!="baseline": continue
        if r["experiment"] not in (anchor_ref, anchor_min): continue
        if r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        anchor_rd[(r["experiment"], r["sequence"])]["R"][r["qp"]] = r["bitrate_kbps"]
        anchor_rd[(r["experiment"], r["sequence"])]["P"][r["qp"]] = r["psnrY_dB"]

    # Build RD points cho experiments
    exp_rd = defaultdict(lambda: defaultdict(lambda: {"R":{}, "P":{}, "group":""}))
    for r in rows:
        if r["group"]=="baseline": continue
        key = (r["experiment"], r["sequence"])
        if r["bitrate_kbps"] is None or r["psnrY_dB"] is None: continue
        exp_rd[key]["R"][r["qp"]] = r["bitrate_kbps"]
        exp_rd[key]["P"][r["qp"]] = r["psnrY_dB"]
        exp_rd[key]["group"]      = r["group"]

    group2anchor = {"perf_ablate": anchor_ref, "speed_ablate": anchor_ref,
                    "perf_add": anchor_min, "speed_add": anchor_min}

    out_rows = []
    agg = defaultdict(list)

    for (exp, seq), rd in exp_rd.items():
        grp = rd["group"]
        anchor_name = group2anchor.get(grp, anchor_ref)
        ref = anchor_rd.get((anchor_name, seq))
        anchor_used = anchor_name; anchor_fallback = False
        if ref is None and grp=="perf_add" and args.fallback_perf_add_to_ref:
            ref = anchor_rd.get((anchor_ref, seq))
            if ref:
                anchor_used = anchor_ref; anchor_fallback = True

        status="PENDING"; bd=None; qps_used=""; approx=""
        if ref:
            common = sorted(set(ref["R"].keys()) & set(rd["R"].keys()))
            if len(common) >= 3:
                R1=[ref["R"][q] for q in common]; P1=[ref["P"][q] for q in common]
                R2=[rd ["R"][q] for q in common]; P2=[rd ["P"][q] for q in common]
                try:
                    bd = bd_rate(R1,P1,R2,P2); status="OK"; qps_used=",".join(map(str,common))
                except Exception as e:
                    status=f"BDERR:{type(e).__name__}"
            elif len(common)==2 and args.allow_2qp_estimate:
                Q = common
                R1=[ref["R"][q] for q in Q]; P1=[ref["P"][q] for q in Q]
                R2=[rd ["R"][q] for q in Q]; P2=[rd ["P"][q] for q in Q]
                try:
                    bd = bd_rate_2qp_linear(R1,P1,R2,P2); status="OK_EST2QP"; qps_used=",".join(map(str,Q)); approx="2QP"
                except Exception as e:
                    status=f"BDERR2:{type(e).__name__}"
            else:
                need=max(0,3-len(common)); status=f"NEED_{need}_QP"
        else:
            status="NO_ANCHOR"

        out_rows.append({
            "group": grp, "experiment": exp, "sequence": seq,
            "anchor": anchor_used, "fallback_anchor": "Y" if anchor_fallback else "",
            "bd_rate_psnrY_percent": bd, "qps_used": qps_used, "approx": approx, "status": status
        })
        if bd is not None and status in ("OK","OK_EST2QP"):
            agg[(grp,exp)].append(bd)

    # Ghi per-seq summary
    with open(args.out,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","sequence","anchor","fallback_anchor","bd_rate_psnrY_percent","qps_used","approx","status"])
        w.writeheader(); [w.writerow(r) for r in out_rows]

    # Ghi overview per experiment
    with open(args.overview,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group","experiment","mean_bd_rate","n_sequences_used"])
        w.writeheader()
        for (grp,exp), arr in agg.items():
            mean = sum(arr)/len(arr) if arr else None
            w.writerow({"group":grp,"experiment":exp,"mean_bd_rate":mean,"n_sequences_used":len(arr)})

    print(f"[OK] Wrote {args.out} and {args.overview}. Also wrote collected_runs_snapshot.csv")

if __name__ == "__main__":
    main()

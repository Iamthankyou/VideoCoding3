# efficiency_report_v1.py
# Read quickfire_* CSV -> compute "benefit when ON" per tool -> rank -> suggest two combos -> export flags & YAML skeleton.
import csv, argparse, re, statistics
from collections import defaultdict, OrderedDict
from pathlib import Path   # <== thêm dòng này


# ---- map experiment name -> CLI flags (sửa theo tên của bạn nếu khác) ----
FLAG_MAP = {
  # perf_add (enable from Baseline_Min)
  "ADD_SAO": ["--SAO=1"],
  "ADD_Deblock": ["--DeblockingFilterDisable=0"],
  "ADD_ALF": ["--ALF=1","--CCALF=1"],
  "ADD_RDOQ": ["--DepQuant=1","--RDOQ=1","--RDOQTS=1"],
  "ADD_LMCS": ["--LMCSEnable=1"],
  "ADD_LFNST": ["--LFNST=1"],
  "ADD_MTS": ["--MTS=1"],
  "ADD_ISP": ["--ISP=1"],
  "ADD_MIP": ["--MIP=1"],
  "ADD_BDOF": ["--Bdof=1"],
  "ADD_DMVR": ["--Dmvr=1"],
  "ADD_BCW": ["--Bcw=1"],
  "ADD_CIIP": ["--CIIP=1"],
  "ADD_GEO": ["--Geo=1"],
  "ADD_Affine_AMVR": ["--Affine=1","--AffineAmvr=1"],

  # perf_ablate (off vs Baseline_Ref) -> must-keep => ON
  "ABLATE_SAO": ["--SAO=1"],
  "ABLATE_Deblock": ["--DeblockingFilterDisable=0"],
  "ABLATE_ALF": ["--ALF=1","--CCALF=1"],
  "ABLATE_RDOQ": ["--DepQuant=1","--RDOQ=1","--RDOQTS=1"],
  "ABLATE_LMCS": ["--LMCSEnable=1"],
  "ABLATE_LFNST": ["--LFNST=1"],
  "ABLATE_MTS": ["--MTS=1"],
  "ABLATE_ISP": ["--ISP=1"],
  "ABLATE_MIP": ["--MIP=1"],
  "ABLATE_BDOF": ["--Bdof=1"],
  "ABLATE_DMVR": ["--Dmvr=1"],
  "ABLATE_BCW": ["--Bcw=1"],
  "ABLATE_CIIP": ["--CIIP=1"],
  "ABLATE_GEO": ["--Geo=1"],
  "ABLATE_Affine_AMVR": ["--Affine=1","--AffineAmvr=1"],
}

# parse resolution from sequence name "..._1920x1080_60"
def parse_res(seq):
    m = re.search(r'_(\d+)x(\d+)_', seq)
    if not m: return None, None, None
    w, h = int(m.group(1)), int(m.group(2))
    cls = "B" if w>=1920 else ("C" if w>=832 else ("D" if w>=416 else "U"))
    return w, h, cls

def read_summary(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                bd = float(r["bd_rate_psnrY_percent"]) if r["bd_rate_psnrY_percent"] else None
            except: bd = None
            rows.append({
              "group": r["group"],
              "experiment": r["experiment"],
              "sequence": r["sequence"],
              "bd": bd,
              "status": r.get("status",""),
            })
    return rows

def per_sequence_benefit(rows):
    # Convert BD-rate to "benefit when ON"
    benefits = []  # dicts: group,experiment,sequence,benefit
    for r in rows:
        if r["bd"] is None: continue
        if r["group"] == "perf_ablate":
            ben = + r["bd"]  # ablate makes BD-rate worse; ON gives +benefit
        elif r["group"] == "perf_add":
            ben = - r["bd"]  # add makes BD-rate more negative; ON benefit = -BD
        else:
            continue  # ignore speed groups here
        benefits.append({"group":r["group"],"experiment":r["experiment"],"sequence":r["sequence"],"benefit":ben})
    return benefits

def aggregate_tool(benefits):
    tool2seq = defaultdict(dict)
    for b in benefits:
        tool2seq[(b["group"], b["experiment"])][b["sequence"]] = b["benefit"]

    agg = []
    for (grp,exp), m in tool2seq.items():
        vals = [v for v in m.values() if v is not None]
        if not vals: continue
        mean = sum(vals)/len(vals)
        med  = statistics.median(vals)
        pos  = sum(1 for v in vals if v>0)/len(vals)
        std  = statistics.pstdev(vals) if len(vals)>1 else 0.0
        agg.append({
            "group": grp, "experiment": exp,
            "mean_benefit": mean, "median_benefit": med, "std": std,
            "stability_ratio": pos, "n_sequences": len(vals)
        })
    return sorted(agg, key=lambda r: (-r["mean_benefit"], -r["stability_ratio"], -r["median_benefit"]))

def per_class_breakdown(benefits):
    # returns {(group,exp,cls): [benefits...]}
    d = defaultdict(list)
    for b in benefits:
        _,_,cls = parse_res(b["sequence"])
        cls = cls or "U"
        d[(b["group"], b["experiment"], cls)].append(b["benefit"])
    rows=[]
    for (g,e,c), arr in d.items():
        rows.append({"group":g,"experiment":e,"class":c,
                     "mean": sum(arr)/len(arr), "n": len(arr)})
    return rows

def corr_pairs(benefits):
    # pairwise corr across sequences between tools (same group or across groups)
    # build sequence-aligned vectors
    tool2seq = defaultdict(dict)
    for b in benefits:
        tool2seq[(b["group"], b["experiment"])][b["sequence"]] = b["benefit"]

    tools = list(tool2seq.keys())
    out=[]
    import math
    def pearson(x,y):
        n=len(x); sx=sum(x); sy=sum(y); sxx=sum(v*v for v in x); syy=sum(v*v for v in y); sxy=sum(a*b for a,b in zip(x,y))
        num = n*sxy - sx*sy
        den = math.sqrt(max(1e-12,(n*sxx-sx*sx)*(n*syy-sy*sy)))
        return num/den if den>0 else 0.0

    for i in range(len(tools)):
        for j in range(i+1,len(tools)):
            t1, t2 = tools[i], tools[j]
            s1, s2 = tool2seq[t1], tool2seq[t2]
            common = sorted(set(s1.keys()) & set(s2.keys()))
            if len(common) < 3: continue
            x = [s1[s] for s in common]
            y = [s2[s] for s in common]
            out.append({"toolA_group":t1[0],"toolA":t1[1],"toolB_group":t2[0],"toolB":t2[1],
                        "n_seq":len(common),"corr": pearson(x,y)})
    return sorted(out, key=lambda r: -abs(r["corr"]))

def classify_and_suggest(agg, corr_rows, thr_high=0.7, thr_med=0.4, stable_high=0.8, stable_med=0.6):
    # classify
    high=[]; med=[]; low=[]
    for r in agg:
        if (r["mean_benefit"]>=thr_high and r["stability_ratio"]>=stable_high):
            high.append(r)
        elif (r["mean_benefit"]>=thr_med and r["stability_ratio"]>=stable_med):
            med.append(r)
        else:
            low.append(r)
    # build two combos
    conservative = high[:]  # High only
    aggressive   = high + med  # High + Medium

    # prune highly overlapping (|corr|>0.85) in aggressive
    # choose the one with higher mean_benefit
    key2mean = {(r["group"], r["experiment"]): r["mean_benefit"] for r in aggressive}
    pruned = set()
    for c in corr_rows:
        if abs(c["corr"]) < 0.85: continue
        a=(c["toolA_group"], c["toolA"]); b=(c["toolB_group"], c["toolB"])
        if a in key2mean and b in key2mean:
            if key2mean[a] >= key2mean[b]:
                pruned.add(b)
            else:
                pruned.add(a)
    aggressive = [r for r in aggressive if (r["group"],r["experiment"]) not in pruned]

    return high, med, low, conservative, aggressive

def flags_from_combo(combo):
    flags=set()
    for r in combo:
        flags.update(FLAG_MAP.get(r["experiment"], []))
    return sorted(flags)

def write_csv(path, rows, header=None):
    if not rows: 
        open(path,"w",encoding="utf-8").write("")
        return
    if header is None: header = list(rows[0].keys())
    with open(path,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header); w.writeheader(); [w.writerow(r) for r in rows]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default="quickfire_summary_from_logs.csv")
    ap.add_argument("--overview", default="quickfire_overview_from_logs.csv")
    ap.add_argument("--out_dir", default="eff_report")
    ap.add_argument("--thr_high", type=float, default=0.7)
    ap.add_argument("--thr_med", type=float, default=0.4)
    ap.add_argument("--stable_high", type=float, default=0.8)
    ap.add_argument("--stable_med", type=float, default=0.6)
    args = ap.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    rows = read_summary(args.summary)
    ben  = per_sequence_benefit(rows)
    agg  = aggregate_tool(ben)
    cls  = per_class_breakdown(ben)
    cor  = corr_pairs(ben)

    write_csv(f"{args.out_dir}/tool_effects.csv", agg,
        header=["group","experiment","mean_benefit","median_benefit","std","stability_ratio","n_sequences"])
    write_csv(f"{args.out_dir}/per_class_breakdown.csv", cls,
        header=["group","experiment","class","mean","n"])
    write_csv(f"{args.out_dir}/pair_correlation.csv", cor,
        header=["toolA_group","toolA","toolB_group","toolB","n_seq","corr"])

    high, med, low, conservative, aggressive = classify_and_suggest(
        agg, cor, args.thr_high, args.thr_med, args.stable_high, args.stable_med)

    # Export flag lists
    cons_flags = flags_from_combo(conservative)
    aggr_flags = flags_from_combo(aggressive)
    with open(f"{args.out_dir}/eff_best_args_conservative.txt","w",encoding="utf-8") as f:
        for fl in cons_flags: f.write(fl+"\n")
    with open(f"{args.out_dir}/eff_best_args_aggressive.txt","w",encoding="utf-8") as f:
        for fl in aggr_flags: f.write(fl+"\n")

    # Quick README for report
    with open(f"{args.out_dir}/README_report.md","w",encoding="utf-8") as f:
        f.write("# Efficiency Report (auto)\n\n")
        f.write("## Ranking (tool_effects.csv)\n")
        f.write("- mean_benefit = lợi ích khi bật tool (%% BD-Rate); stability_ratio = %% sequence cải thiện\n")
        f.write("## Per-class breakdown (per_class_breakdown.csv)\n")
        f.write("## Pairwise correlation (pair_correlation.csv) — cảnh báo trùng lặp nếu |corr|>0.85\n")
        f.write("## Suggested presets\n")
        f.write("- Conservative flags: eff_best_args_conservative.txt\n")
        f.write("- Aggressive flags:   eff_best_args_aggressive.txt\n")

    print("[OK] Wrote:", args.out_dir)

if __name__ == "__main__":
    main()

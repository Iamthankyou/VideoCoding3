#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
excel_vtm_report.py
- Đọc results.csv (các cột: group, tool, seq, qp, bitrate_kbps, psnr_y/psnr_yuv, enc_time_s, …)
- Chuẩn hoá dữ liệu, nhận diện Baseline: group=="Baseline" & tool trống/NaN
- Tính BD-Rate (chuẩn poly bậc 3, fallback bậc 1 nếu chỉ có 2 điểm)
- Xuất Excel gồm:
  Raw, BD-Rate, BD_Missing, TimeTable, SpeedupTable, Time_vs_QP_All (column),
  và mỗi SEQ_* có: RD curve (log-scale), Time line, Time column.
Yêu cầu: pip install pandas numpy xlsxwriter
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# -------- BD-Rate helpers --------
def _polyfit_lograte_vs_psnr(rate, psnr):
    m = (~np.isnan(rate)) & (~np.isnan(psnr)) & (rate > 0)
    x = psnr[m].astype(float).values
    y = np.log(rate[m].astype(float).values)
    if len(x) >= 3:      # chuẩn (khuyến nghị)
        return np.polyfit(x, y, 3)
    elif len(x) == 2:    # fallback 2 điểm (log-linear)
        return np.polyfit(x, y, 1)
    else:
        return None

def _bdrate_pair(baseline_df, test_df, metric_col="psnr_yuv", rate_col="bitrate_kbps"):
    # sort theo qp cho chắc
    baseline_df = baseline_df.sort_values("qp")
    test_df     = test_df.sort_values("qp")
    pb = _polyfit_lograte_vs_psnr(baseline_df[rate_col], baseline_df[metric_col])
    pt = _polyfit_lograte_vs_psnr(test_df[rate_col],      test_df[metric_col])
    if pb is None or pt is None:
        return np.nan, "not_enough_points"

    yb = baseline_df[metric_col].values
    yt = test_df[metric_col].values
    y_min = max(np.min(yb), np.min(yt))
    y_max = min(np.max(yb), np.max(yt))
    if not (y_max > y_min):
        return np.nan, "no_overlap"

    fb = np.poly1d(pb); ft = np.poly1d(pt)
    Ib = np.polyint(fb); It = np.polyint(ft)
    avg_b = (Ib(y_max) - Ib(y_min)) / (y_max - y_min)
    avg_t = (It(y_max) - It(y_min)) / (y_max - y_min)
    return (np.exp(avg_t - avg_b) - 1.0) * 100.0, ""

def _fit_curve(df, metric_col, n=30):
    """Trả về (psnr_grid, rate_fit) theo nội suy đa thức; None nếu dữ liệu thiếu."""
    p = _polyfit_lograte_vs_psnr(df["bitrate_kbps"], df[metric_col])
    if p is None:
        return None, None
    y = df[metric_col].values
    y_grid = np.linspace(np.min(y), np.max(y), n)
    rate_fit = np.exp(np.poly1d(p)(y_grid))
    return y_grid, rate_fit

# -------- Load & normalize --------
def load_clean(csv_path):
    df = pd.read_csv(csv_path)

    # Chuẩn hoá text
    for c in ["group","tool","seq"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # Baseline: group=="Baseline" & tool rỗng/None/NaN
    if "tool" in df.columns:
        df["tool"] = df["tool"].replace({"None":"", "none":""})
        df.loc[df["tool"]=="", "tool"] = np.nan

    # Lọc job lỗi nếu có retcode
    if "retcode" in df.columns:
        df = df[df["retcode"] == 0].copy()

    # Numeric
    for c in ["bitrate_kbps","psnr_y","psnr_u","psnr_v","psnr_yuv","enc_time_s","qp"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Cần bitrate
    df = df.dropna(subset=["bitrate_kbps"]).copy()

    # QP về int
    if "qp" in df.columns:
        df["qp"] = df["qp"].astype(float).round().astype(int)

    # Nhãn tool_full cho pivot/tổng hợp
    df["tool_full"] = np.where(
        (df["group"]=="Baseline") & (df["tool"].isna()),
        "Baseline",
        df["group"] + "-" + df["tool"].fillna("")
    )
    return df

# -------- Excel writer --------
def build_excel(csv_path, out_path, metric="psnr_yuv"):
    from xlsxwriter import Workbook

    df = load_clean(csv_path)
    if df.empty:
        raise SystemExit("CSV rỗng hoặc không hợp lệ.")

    wb = Workbook(str(out_path), {'nan_inf_to_errors': True})

    def safe(v):
        # đổi NaN/inf → None để Excel không lỗi
        try:
            import math
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
        except Exception:
            pass
        return v

    # RAW
    ws_raw = wb.add_worksheet("Raw")
    for j, col in enumerate(df.columns): ws_raw.write(0, j, col)
    for i, row in enumerate(df.itertuples(index=False), start=1):
        ws_raw.write_row(i, 0, [safe(v) for v in row])

    # BD-Rate & BD_Missing
    ws_bdr = wb.add_worksheet("BD-Rate")
    ws_bdr.write_row(0, 0, ["seq","group","tool","BD-Rate_%"])
    bdr_rows, miss_rows = [], []

    for seq, gseq in df.groupby("seq"):
        base = gseq[(gseq["group"]=="Baseline") & (gseq["tool"].isna())].sort_values("qp")
        if base.empty:
            miss_rows.append([seq, "(all tools)", "no_baseline", None, None, None, None])
            continue
        for (group, tool), gtool in gseq.groupby(["group","tool"]):
            if group=="Baseline" and pd.isna(tool):
                continue
            gtool = gtool.sort_values("qp")
            val, reason = _bdrate_pair(
                base[["qp","bitrate_kbps",metric]].dropna(),
                gtool[["qp","bitrate_kbps",metric]].dropna(),
                metric_col=metric
            )
            if np.isnan(val):
                bmin = base[metric].min() if metric in base.columns else np.nan
                bmax = base[metric].max() if metric in base.columns else np.nan
                tmin = gtool[metric].min() if metric in gtool.columns else np.nan
                tmax = gtool[metric].max() if metric in gtool.columns else np.nan
                miss_rows.append([seq, f"{group}-{'' if pd.isna(tool) else tool}", reason, bmin, bmax, tmin, tmax])
            bdr_rows.append([seq, group, ("" if pd.isna(tool) else tool), val])

    for i, row in enumerate(bdr_rows, start=1):
        ws_bdr.write_row(i, 0, [safe(v) for v in row])

    if miss_rows:
        ws_miss = wb.add_worksheet("BD_Missing")
        ws_miss.write_row(0,0,["seq","tool","reason","base_min","base_max","tool_min","tool_max"])
        for i, row in enumerate(miss_rows, start=1):
            ws_miss.write_row(i, 0, [safe(v) for v in row])

    # TimeTable
    ws_time = wb.add_worksheet("TimeTable")
    pivot = df.pivot_table(index=["seq","qp"], columns="tool_full",
                           values="enc_time_s", aggfunc="mean").sort_index()
    ws_time.write_row(0,0,["seq","qp"] + list(pivot.columns))
    for i,(idx, vals) in enumerate(pivot.iterrows(), start=1):
        ws_time.write_row(i, 0, [idx[0], int(idx[1])] + [safe(vals[c]) for c in pivot.columns])

    # SpeedupTable
    ws_sp = wb.add_worksheet("SpeedupTable")
    sp_rows = []
    for seq, gseq in df.groupby("seq"):
        base = gseq[(gseq["group"]=="Baseline") & (gseq["tool"].isna())][["qp","enc_time_s"]].rename(columns={"enc_time_s":"base_time"})
        if base.empty:
            continue
        for (group, tool), g in gseq.groupby(["group","tool"]):
            if group=="Baseline" and pd.isna(tool):
                continue
            m = pd.merge(g[["qp","enc_time_s"]], base, on="qp", how="inner")
            if not m.empty:
                m["seq"]=seq; m["tool_full"]=f"{group}-{'' if pd.isna(tool) else tool}"
                m["speedup"]=m["base_time"]/m["enc_time_s"]
                sp_rows.append(m[["seq","qp","tool_full","speedup"]])
    if sp_rows:
        sp_df = pd.concat(sp_rows, ignore_index=True)
        piv = sp_df.pivot_table(index=["seq","qp"], columns="tool_full",
                                values="speedup", aggfunc="mean").sort_index()
        ws_sp.write_row(0,0,["seq","qp"] + list(piv.columns))
        for i,(idx, vals) in enumerate(piv.iterrows(), start=1):
            ws_sp.write_row(i, 0, [idx[0], int(idx[1])] + [safe(vals[c]) for c in piv.columns])

    # Time_vs_QP_All (column chart)
    ws_all = wb.add_worksheet("Time_vs_QP_All")
    avg = df.groupby(["tool_full","qp"], as_index=False)["enc_time_s"].mean().sort_values(["tool_full","qp"])
    ws_all.write_row(0,0,["tool_full","qp","enc_time_s"])
    for i,row in enumerate(avg.itertuples(index=False), start=1):
        ws_all.write_row(i, 0, [safe(v) for v in row])

    ch = wb.add_chart({"type":"column"})
    ch.set_title({"name":"Average Encoding Time vs QP (All sequences)"})
    ch.set_x_axis({"name":"QP"})
    ch.set_y_axis({"name":"Encode time (s)"})
    ch.set_legend({"position":"bottom"})
    for tool, g in avg.groupby("tool_full"):
        first = g.index.min()+1
        last  = g.index.max()+1
        ch.add_series({
            "name": tool,
            "categories": ["Time_vs_QP_All", first, 1, last, 1],  # qp col
            "values":     ["Time_vs_QP_All", first, 2, last, 2],  # time col
        })
    ws_all.insert_chart(1, 4, ch)

    # Per-sequence sheets
    for seq, gseq in df.groupby("seq"):
        sheet = f"SEQ_{str(seq)[:25]}"
        ws = wb.add_worksheet(sheet)
        sub = gseq[["group","tool","qp","bitrate_kbps",metric if metric in gseq.columns else "psnr_y","enc_time_s"]]\
              .sort_values(["group","tool","bitrate_kbps","qp"]).reset_index(drop=True)
        ws.write_row(0,0,["group","tool","qp","bitrate_kbps",metric,"enc_time_s"])
        for i,row in enumerate(sub.itertuples(index=False), start=1):
            ws.write_row(i, 0, [safe(v) for v in row])

        # RD curve (line, log-scale X)
        rd = wb.add_chart({"type":"line"})
        rd.set_title({"name": f"RD Curve — {seq} ({metric})"})
        rd.set_x_axis({"name":"Bitrate (kbps)", "log_base":10})
        rd.set_y_axis({"name": f"{metric.upper()} (dB)"})
        rd.set_legend({"position":"bottom"})
        sc = 0
        for (group, tool), g in sub.groupby(["group","tool"]):
            if g.iloc[:,4].isna().all():  # metric col
                continue
            first, last = g.index.min()+1, g.index.max()+1
            rd.add_series({
                "name": f"{group}-{'' if pd.isna(tool) else tool}" if not (group=="Baseline" and pd.isna(tool)) else "Baseline",
                "categories": [sheet, first, 3, last, 3],  # bitrate
                "values":     [sheet, first, 4, last, 4],  # metric
                "marker": {"type":"circle","size":6},
                "line": {"width":1.25},
            }); sc += 1
        if sc:
            ws.insert_chart(1, 7, rd)

        # Time vs QP (line)
        tl = wb.add_chart({"type":"line"})
        tl.set_title({"name": f"Encoding Time — {seq}"})
        tl.set_x_axis({"name":"QP"}); tl.set_y_axis({"name":"Encode time (s)"})
        tl.set_legend({"position":"bottom"})
        sc = 0
        for (group, tool), g in sub.groupby(["group","tool"]):
            if g["enc_time_s"].isna().all():
                continue
            first, last = g.index.min()+1, g.index.max()+1
            tl.add_series({
                "name": f"{group}-{'' if pd.isna(tool) else tool}" if not (group=="Baseline" and pd.isna(tool)) else "Baseline",
                "categories": [sheet, first, 2, last, 2],  # qp
                "values":     [sheet, first, 5, last, 5],  # time
                "marker": {"type":"square","size":6},
                "line": {"width":1.25},
            }); sc += 1
        if sc:
            ws.insert_chart(21, 7, tl)

        # Time vs QP (clustered column)
        tc = wb.add_chart({"type":"column"})
        tc.set_title({"name": f"Encoding Time (Column) — {seq}"})
        tc.set_x_axis({"name":"QP"}); tc.set_y_axis({"name":"Encode time (s)"})
        tc.set_legend({"position":"bottom"})
        sc = 0
        for (group, tool), g in sub.groupby(["group","tool"]):
            if g["enc_time_s"].isna().all():
                continue
            first, last = g.index.min()+1, g.index.max()+1
            tc.add_series({
                "name": f"{group}-{'' if pd.isna(tool) else tool}" if not (group=="Baseline" and pd.isna(tool)) else "Baseline",
                "categories": [sheet, first, 2, last, 2],  # qp
                "values":     [sheet, first, 5, last, 5],  # time
            }); sc += 1
        if sc:
            ws.insert_chart(41, 7, tc)

    wb.close()
    return out_path

# -------- main --------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng:")
        print("  python excel_vtm_report.py <path/to/results.csv> [metric] [output.xlsx]")
        print("  metric: psnr_y (mặc định) | psnr_yuv | psnr_u | psnr_v")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    metric   = sys.argv[2] if len(sys.argv) >= 3 else "psnr_yuv"
    out      = Path(sys.argv[3]) if len(sys.argv) >= 4 else (csv_path.parent / "vtm_report.xlsx")

    print("Đang tạo Excel report…")
    p = build_excel(str(csv_path), str(out), metric=metric)
    print(f"Xong: {p}")

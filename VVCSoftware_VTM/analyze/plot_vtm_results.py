#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, os
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def load_and_clean(csv_path: str):
    df = pd.read_csv(csv_path)
    # chỉ giữ job thành công
    if "retcode" in df.columns:
        df = df[df["retcode"] == 0].copy()
    # ép kiểu số
    for c in ["bitrate_kbps","psnr_y","psnr_u","psnr_v","psnr_yuv","enc_time_s","qp"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # bỏ hàng thiếu bitrate/psnr
    df = df.dropna(subset=["bitrate_kbps"]).copy()
    return df

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def plot_rd_curves(df: pd.DataFrame, outdir: Path, metric: str):
    # vẽ RD cho từng sequence: bitrate vs PSNR metric
    for seq, gseq in df.groupby("seq"):
        plt.figure()
        # sắp theo group để legend dễ đọc
        for (group, tool), gtool in gseq.groupby(["group","tool"]):
            g = gtool.sort_values("bitrate_kbps")
            y = g[metric] if metric in g.columns else g["psnr_y"]
            if y.isna().all():
                continue
            label = f"{group}-{tool}" if tool != "None" else "Baseline"
            plt.plot(g["bitrate_kbps"], y, marker="o", label=label)
        plt.xlabel("Bitrate (kbps)")
        plt.ylabel(metric.upper() if metric.startswith("psnr") else "PSNR-Y (dB)")
        plt.title(f"RD Curve — {seq}")
        plt.grid(True, which="both", linewidth=0.5, linestyle="--")
        plt.legend(loc="best", fontsize=8)
        plt.tight_layout()
        ensure_dir(outdir)
        plt.savefig(outdir / f"RD_{seq}.png", dpi=160)
        plt.close()

def plot_time_vs_qp(df: pd.DataFrame, outdir: Path):
    # vẽ độ phức tạp (thời gian) theo QP cho từng sequence
    for seq, gseq in df.groupby("seq"):
        plt.figure()
        for (group, tool), gtool in gseq.groupby(["group","tool"]):
            g = gtool.sort_values("qp")
            if "enc_time_s" not in g.columns or g["enc_time_s"].isna().all():
                continue
            label = f"{group}-{tool}" if tool != "None" else "Baseline"
            plt.plot(g["qp"], g["enc_time_s"], marker="s", label=label)
        plt.xlabel("QP")
        plt.ylabel("Encode time (s)")
        plt.title(f"Encoding Complexity — {seq}")
        plt.grid(True, linestyle="--", linewidth=0.5)
        plt.legend(loc="best", fontsize=8)
        plt.tight_layout()
        ensure_dir(outdir)
        plt.savefig(outdir / f"TIME_{seq}.png", dpi=160)
        plt.close()

# --- BD-Rate (Bjøntegaard Delta Rate) so với baseline ---
def _polyfit_bitrate_psnr(bitrate, psnr):
    # dùng log(rate) như chuẩn BD-Rate
    # lọc dữ liệu hợp lệ
    m = (~np.isnan(bitrate)) & (~np.isnan(psnr)) & (bitrate > 0)
    x = np.log(bitrate[m].values)
    y = psnr[m].values
    if len(x) < 3:
        return None  # không đủ điểm
    return np.polyfit(y, x, 3)  # x = f(y)

def _bdrate_single(baseline_df, test_df, metric_col):
    # lấy khoảng giao nhau của PSNR
    yb = baseline_df[metric_col].values
    yt = test_df[metric_col].values
    rb = baseline_df["bitrate_kbps"].values
    rt = test_df["bitrate_kbps"].values
    pb = _polyfit_bitrate_psnr(rb, yb)
    pt = _polyfit_bitrate_psnr(rt, yt)
    if pb is None or pt is None:
        return np.nan
    y_min = max(min(yb), min(yt))
    y_max = min(max(yb), max(yt))
    if y_max <= y_min:
        return np.nan
    # tích phân log-rate theo PSNR
    p_b = np.poly1d(pb)
    p_t = np.poly1d(pt)
    int_b = np.polyint(p_b)
    int_t = np.polyint(p_t)
    avg_b = (int_b(y_max) - int_b(y_min)) / (y_max - y_min)
    avg_t = (int_t(y_max) - int_t(y_min)) / (y_max - y_min)
    # chuyển về tỉ lệ %
    return (np.exp(avg_t - avg_b) - 1.0) * 100.0

def compute_bdrate(df: pd.DataFrame, metric: str):
    rows = []
    for seq, gseq in df.groupby("seq"):
        # baseline
        base = gseq[(gseq["group"]=="Baseline") & (gseq["tool"]=="None")]
        if base.empty:
            continue
        for (group, tool), gtool in gseq.groupby(["group","tool"]):
            if group=="Baseline" and tool=="None":
                continue
            val = _bdrate_single(base.sort_values("qp"), gtool.sort_values("qp"), metric)
            rows.append([seq, group, tool, val])
    if not rows:
        return pd.DataFrame(columns=["seq","group","tool","BD-Rate_%"])
    out = pd.DataFrame(rows, columns=["seq","group","tool","BD-Rate_%"])
    return out.sort_values(["seq","group","tool"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Đường dẫn results.csv")
    ap.add_argument("--outdir", default=None, help="Thư mục lưu ảnh (mặc định cùng thư mục CSV, /plots)")
    ap.add_argument("--metric", default="psnr_y", choices=["psnr_y","psnr_yuv","psnr_u","psnr_v"],
                    help="PSNR dùng cho RD & BD-Rate")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    outdir = Path(args.outdir) if args.outdir else csv_path.parent / "plots"
    ensure_dir(outdir)

    df = load_and_clean(str(csv_path))
    if df.empty:
        print("Không có dữ liệu hợp lệ trong CSV (retcode!=0 hoặc thiếu bitrate/psnr).")
        return

    print("Vẽ RD curves...")
    plot_rd_curves(df, outdir, args.metric)

    print("Vẽ thời gian mã hoá (complexity)...")
    plot_time_vs_qp(df, outdir)

    print("Tính BD-Rate so với Baseline...")
    bdr = compute_bdrate(df, args.metric)
    bdr_file = outdir / "bdrate_summary.csv"
    bdr.to_csv(bdr_file, index=False)
    print(f"Đã lưu {bdr_file}")

    print(f"Xong. Ảnh lưu trong: {outdir}")

if __name__ == "__main__":
    main()

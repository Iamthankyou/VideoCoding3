#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, asyncio, csv, os, re, sys, time, yaml, hashlib, itertools
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ------------------------- parsing VTM log -------------------------

PSNR_SUMMARY_RE = re.compile(
    r"Total Frames\s*\|\s*Bitrate\s+Y-PSNR\s+U-PSNR\s+V-PSNR\s+YUV-PSNR\s*"
    r"\n\s*(\d+)\s+\S\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
    re.MULTILINE
)
TOTAL_TIME_RE = re.compile(r"Total Time:\s+([\d.]+)\s+sec\.\s+\[user\]\s+([\d.]+)\s+sec\.\s+\[elapsed\]", re.MULTILINE)

def parse_vtm_log(log_text: str) -> Tuple[float, float, float, float, float, float]:
    import math
    br = py = pu = pv = pyuv = tenc = float('nan')

    m = PSNR_SUMMARY_RE.search(log_text)
    if m:
        br     = float(m.group(2))
        py     = float(m.group(3))
        pu     = float(m.group(4))
        pv     = float(m.group(5))
        pyuv   = float(m.group(6))

    mt = TOTAL_TIME_RE.search(log_text)
    if mt:
        tenc  = float(mt.group(2))

    return br, py, pu, pv, pyuv, tenc

# ------------------------- job building helpers -------------------------

def normalize_args(args: List[str]) -> List[str]:
    out = []
    for a in args or []:
        if a is None: continue
        s = str(a).strip()
        if s:
            out.append(s)
    return out

def apply_dependencies(args: list[str]) -> list[str]:
    a = " ".join(args) + " "
    need_dq0 = ("--RDOQ=0" in a) or ("--RDOQTS=0" in a)
    need_dq1 = ("--RDOQ=1" in a) or ("--RDOQTS=1" in a)

    args = [x for x in args if not x.startswith("--DepQuant=")]
    if need_dq0 and not need_dq1:
        args.append("--DepQuant=0")
    elif need_dq1 and not need_dq0:
        args.append("--DepQuant=1")
    return args

def merge_args(base: List[str], extra: List[str]) -> List[str]:
    return apply_dependencies(normalize_args(list(base) + list(extra)))

# ------------------------- YAML schema -------------------------

def load_experiment(yaml_path: Path) -> Dict:
    with open(yaml_path, "r", encoding="utf-8") as f:
        exp = yaml.safe_load(f)
    exp.setdefault("fixed_args", [])
    exp.setdefault("sequences", [])
    exp.setdefault("qps", [37,32,27,22])
    for key in ["baselines", "perf_add", "perf_ablate", "speed_add", "speed_ablate"]:
        exp.setdefault(key, [])
    return exp

# ------------------------- command building -------------------------

def build_cmd(exp, seq, qp, job_args, out_dir, tag, no_recon):
    vtm_bin = str(exp["vtm_bin"])
    base_cfg = str(exp["base_cfg"])
    name = seq["name"]

    job_dir = out_dir / f"{tag}_{name}_QP{qp}"
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_dir / "enc.log"

    cmd = [vtm_bin, "-c", base_cfg, f"--QP={qp}"]

    seq_cfg = seq.get("seq_cfg", "")
    if seq_cfg:
        cmd += ["-c", str(seq_cfg)]
    else:
        if "yuv" in seq and str(seq["yuv"]).lower().endswith(".yuv"):
            cmd += [
                f'--InputFile={seq["yuv"]}',
                f'--SourceWidth={seq["width"]}',
                f'--SourceHeight={seq["height"]}',
                f'--FrameRate={seq["fps"]}',
                f'--FramesToBeEncoded={seq["frames"]}',
            ]

    if not no_recon:
        rec_path = job_dir / f"{tag}_{name}_QP{qp}.yuv"
        cmd += [f"--ReconFile={rec_path}"]

    cmd += exp.get("fixed_args", [])
    cmd += job_args
    return cmd, log_path

# ------------------------- job plan -------------------------

def jobs_from_yaml(exp: Dict, out_dir: Path, no_recon: bool) -> List[Dict]:
    jobs = []
    base_ref = next((b for b in exp["baselines"] if b["name"] == "Baseline_Ref"), None)
    base_min = next((b for b in exp["baselines"] if b["name"] == "Baseline_Min"), None)

    def plan_group(group_name: str, base_name: str, base_args: List[str], items: List[Dict]):
        for seq in exp["sequences"]:
            for qp in exp["qps"]:
                args_base = apply_dependencies(normalize_args(base_args))
                jobs.append({
                    "group": "Baseline",
                    "tool": base_name,
                    "seq": seq["name"],
                    "qp": qp,
                    "cmd_spec": (seq, qp, args_base, out_dir, base_name, no_recon)
                })
                for it in items:
                    tool_name = it["name"]
                    merged = merge_args(args_base, it.get("args", []))
                    tag2 = f"{group_name}_{tool_name}"
                    jobs.append({
                        "group": group_name,
                        "tool": tool_name,
                        "seq": seq["name"],
                        "qp": qp,
                        "cmd_spec": (seq, qp, merged, out_dir, tag2, no_recon)
                    })

    if base_ref:
        plan_group("Perf_Ablate",  "Baseline_Ref", base_ref.get("args", []), exp["perf_ablate"])
        plan_group("Speed_Ablate", "Baseline_Ref", base_ref.get("args", []), exp["speed_ablate"])

    if base_min:
        plan_group("Perf_Add",  "Baseline_Min", base_min.get("args", []), exp["perf_add"])
        plan_group("Speed_Add", "Baseline_Min", base_min.get("args", []), exp["speed_add"])

    return jobs

# ------------------------- runner -------------------------

async def run_one(job: Dict, writer, lock, args):
    seq, qp, job_args, out_dir, tag, no_recon = job["cmd_spec"]
    cmd, log_path = build_cmd(args.exp, seq, qp, job_args, out_dir, tag, no_recon)

    t0 = time.time()
    env = os.environ.copy()
    if args.enc_threads:
        env["OMP_NUM_THREADS"] = str(args.enc_threads)

    if args.verbose:
        print("[run]", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env
    )

    buff = []
    with open(log_path, "wb") as f:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            f.write(line)
            if args.verbose:
                try:
                    sys.stdout.buffer.write(line)
                except Exception:
                    pass
            buff.append(line)

    ret = await proc.wait()
    t1 = time.time()

    log_text = b"".join(buff).decode("utf-8", errors="ignore")
    br, py, pu, pv, pyuv, tenc = parse_vtm_log(log_text)

    if (tenc != tenc) or (tenc is None):
        tenc = t1 - t0

    row = [
        job["group"], job["tool"], job["seq"], qp,
        br, py, pu, pv, pyuv, tenc, ret
    ]
    async with lock:
        writer.writerow(row)

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True, help="YAML experiment file")
    ap.add_argument("--max-parallel", type=int, default=None)
    ap.add_argument("--enc-threads", type=int, default=None)
    ap.add_argument("--no-recon", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--progress-interval", type=int, default=10)
    args = ap.parse_args()

    exp = load_experiment(Path(args.exp))
    args.exp = exp

    out_dir = Path(exp["output_dir"]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"

    cpu_count = os.cpu_count() or 8
    max_parallel = args.max_parallel or max(1, min(cpu_count, 16))
    if args.verbose:
        print(f"[plan] cores={cpu_count}, enc_threads={args.enc_threads}, max_parallel={max_parallel}")

    jobs = jobs_from_yaml(exp, out_dir, args.no_recon)
    if args.verbose:
        print(f"[plan] jobs={len(jobs)}")

    sem = asyncio.Semaphore(max_parallel)
    fcsv = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(fcsv)
    writer.writerow(["group","tool","seq","qp","bitrate_kbps","psnr_y","psnr_u","psnr_v","psnr_yuv","enc_time_s","retcode"])
    lock = asyncio.Lock()

    async def gated(job):
        async with sem:
            await run_one(job, writer, lock, args)

    def scan_progress():
        created = 0
        finished = 0
        for p in out_dir.rglob("enc.log"):
            created += 1
            try:
                with open(p, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    n = f.tell()
                    f.seek(max(0, n - 65536), os.SEEK_SET)
                    tail = f.read().decode("utf-8", errors="ignore")
                    if "Total Time:" in tail:
                        finished += 1
            except Exception:
                pass
        return created, finished

    async def progress():
        total = len(jobs)
        while True:
            await asyncio.sleep(args.progress_interval)
            created, finished = scan_progress()
            print(f"[progress] {created}/{total} logs, finished={finished}, csv={csv_path}")
            if finished >= total:
                break

    prog_task = asyncio.create_task(progress())
    try:
        await asyncio.gather(*(gated(j) for j in jobs))
    finally:
        prog_task.cancel()
        try:
            await prog_task
        except asyncio.CancelledError:
            pass
        fcsv.close()
        print("[done] CSV:", csv_path)

if __name__ == "__main__":
    asyncio.run(main())

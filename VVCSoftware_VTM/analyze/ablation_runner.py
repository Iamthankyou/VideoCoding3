
# ablation_runner.py
# Run VTM ablations defined in a YAML file and compute BD-Rate vs. baseline.
import argparse, os, subprocess, shlex, json
from pathlib import Path

try:
    import yaml
except Exception as e:
    raise SystemExit("PyYAML is required. Please install with: pip install pyyaml") from e

from vtm_logparser import parse_log_for_metrics
from bdrate import bd_rate

def build_cmd(vtm_bin, cfg, seq, qp, overrides, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    bitstream = out_dir / f"{seq['name']}_QP{qp}.vvc"
    log_path  = out_dir / f"{seq['name']}_QP{qp}.log"

    # Build override string: --Key=Value pairs
    # Keys are case-sensitive; they must match VTM cfg names
    ov_flags = " ".join([f"--{k}={v}" for k,v in overrides.items()]) if overrides else ""

    cmd = (
        f"{vtm_bin} -c {shlex.quote(cfg)} "
        f"-i {shlex.quote(seq['path'])} -wdt {seq['w']} -hgt {seq['h']} "
        f"-fr {seq.get('fr', 60)} -f {seq.get('frames', 64)} -q {qp} "
        f"-b {shlex.quote(str(bitstream))} {ov_flags} "
        f"> {shlex.quote(str(log_path))} 2>&1"
    )
    return cmd, bitstream, log_path

def run(cmd):
    print("[RUN]", cmd)
    return subprocess.call(cmd, shell=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", required=True, help="Path to experiment_ablation.yaml")
    ap.add_argument("--dry", action="store_true", help="Print commands only")
    ap.add_argument("--profile", choices=["RA","AI","LDB","ALL"], default="ALL")
    ap.add_argument("--summary", default="ablation_summary.csv")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text())

    vtm_bin = cfg["globals"]["vtm_bin"]
    out_root = Path(cfg["globals"].get("out_dir","./out_ablation"))
    qps = cfg["globals"].get("qps", [22,27,32,37])

    profiles = cfg["globals"]["profiles"]
    if args.profile != "ALL":
        profiles = [p for p in profiles if p["name"] == args.profile]

    sequences = cfg["sequences"]
    experiments = cfg["experiments"]

    results = []  # rows for CSV

    for prof in profiles:
        prof_name = prof["name"]
        cfg_file  = prof["cfg"]

        for seq in sequences:
            # Run baseline first
            base_exp = next((e for e in experiments if e["name"] == "baseline"), None)
            if not base_exp:
                raise SystemExit("experiments must include a 'baseline' entry")

            # Map from QP to (bitrate, psnrY)
            base_rd = {"bitrate": [], "psnr": []}
            exp_rd_sets = {}  # exp_name -> {"bitrate": [], "psnr": []}

            # Run all experiments including baseline
            for exp in experiments:
                exp_name = exp["name"]
                overrides = exp.get("override",{}) or {}

                for qp in qps:
                    out_dir = out_root / prof_name / seq["name"] / exp_name / f"QP{qp}"
                    cmd, bitstream, log_path = build_cmd(vtm_bin, cfg_file, seq, qp, overrides, out_dir)
                    if not args.dry:
                        rc = run(cmd)
                        if rc != 0:
                            print(f"[WARN] Encoder returned {rc} for {exp_name} QP{qp} {seq['name']} {prof_name}")
                    # Parse log
                    if log_path.exists():
                        br, py = parse_log_for_metrics(str(log_path))
                    else:
                        br, py = None, None

                    if exp_name == "baseline":
                        base_rd["bitrate"].append(br)
                        base_rd["psnr"].append(py)
                    else:
                        exp_rd_sets.setdefault(exp_name, {"bitrate": [], "psnr": []})
                        exp_rd_sets[exp_name]["bitrate"].append(br)
                        exp_rd_sets[exp_name]["psnr"].append(py)

            # Compute BD-Rate vs baseline for each experiment
            for exp_name, rd in exp_rd_sets.items():
                try:
                    bd = bd_rate(base_rd["bitrate"], base_rd["psnr"], rd["bitrate"], rd["psnr"])
                except Exception as e:
                    bd = None
                    print(f"[ERR] BD-Rate failed for {exp_name} on {seq['name']} {prof_name}: {e}")

                row = {
                    "profile": prof_name,
                    "sequence": seq["name"],
                    "experiment": exp_name,
                    "bd_rate_psnrY_percent": bd,
                    "anchor": "baseline",
                    "qps": ",".join(map(str, qps)),
                }
                results.append(row)

    # Write CSV summary
    import csv
    csv_path = Path(args.summary)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["profile","sequence","experiment","bd_rate_psnrY_percent","anchor","qps"])
        w.writeheader()
        for r in results:
            w.writerow(r)

    print(f"[OK] Summary written:", csv_path)

if __name__ == "__main__":
    main()

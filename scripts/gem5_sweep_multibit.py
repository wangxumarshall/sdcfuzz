#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_multibit.py — 多 bit 翻转注入, 对比单 bit 的 diverge 率

项2: gem5-fi 当前 max-faults=1 (单 bit)。多 bit 翻转更接近真实 SDC (多位同时翻转),
预期 diverge 率更高。本脚本跑 N 次注入, max-faults 可配, 对比单 bit。

用法 (在 0101): python3 gem5_sweep_multibit.py <num_runs> <max_faults> [--seed S]
"""
import argparse, os, random, shutil, subprocess, sys, re
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
WORKLOAD = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload")
GOLDEN_NUMCYCLES = 63788
ROI_LO = int(GOLDEN_NUMCYCLES * 0.20)
ROI_HI = int(GOLDEN_NUMCYCLES * 0.80)
GOLDEN_STDOUT = "SUM=1176263118239748788 CRC=5b8846f3"

def run_one(i, first_clock, max_faults, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5, "-r", "-e", "--silent-redirect", "-d", outdir, SCRIPT,
           "--binary", WORKLOAD, "--mode", "inject",
           "--first-clock", str(first_clock),
           "--max-faults", str(max_faults), "--probability", "1.0"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
    except subprocess.TimeoutExpired:
        return {"gem5rc": -1, "workload": "", "fault": "timeout"}
    simout = ""
    p = os.path.join(outdir, "simout.txt")
    if os.path.exists(p):
        with open(p, errors='replace') as f: simout = f.read()
    wl = ""
    for line in simout.splitlines():
        if "SUM=" in line: wl = line.strip(); break
    faults = ""
    fp = os.path.join(outdir, "fault_injections.log")
    if os.path.exists(fp):
        with open(fp, errors='replace') as f: faults = f.read().strip()
    nfi = len(faults.splitlines()) if faults else 0
    return {"gem5rc": proc.returncode, "workload": wl, "nfi": nfi, "fault": faults}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("num_runs", type=int)
    ap.add_argument("max_faults", type=int, help="1=单bit对照, 2/3/4=多bit")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    runs_dir = os.path.expanduser(f"~/gem5-fi/smoke_test/sdc_multi_{args.max_faults}bit_runs")
    if os.path.exists(runs_dir): shutil.rmtree(runs_dir)
    os.makedirs(runs_dir, exist_ok=True)
    print(f"多 bit 注入: max-faults={args.max_faults}, {args.num_runs} runs, ROI=[{ROI_LO},{ROI_HI}]")
    print(f"{'#':>3} {'fc':>7} {'gem5rc':>6} {'nFi':>4} {'class':>10}  workload")
    clean = exit_d = masked = noout = 0
    for i in range(args.num_runs):
        fc = rng.randint(ROI_LO, ROI_HI)
        outdir = os.path.join(runs_dir, f"run_{i:03d}")
        r = run_one(i, fc, args.max_faults, outdir)
        wl = r["workload"]
        if not wl:
            cls = "nooutput"; noout += 1
        elif wl == GOLDEN_STDOUT:
            cls = "masked"; masked += 1
        elif "Exiting" in wl:
            cls = "exit_div"; exit_d += 1
        else:
            cls = "DIVERGE"; clean += 1
        if cls in ("DIVERGE", "exit_div"):
            print(f"{i:>3} {fc:>7} {r['gem5rc']:>6} {r.get('nfi',0):>4} {cls:>10}  {wl[:60]}")
    total = clean + exit_d + masked + noout
    print(f"\n=== max-faults={args.max_faults}: {total} runs, 干净diverge={clean} ({100*clean/total:.1f}%), "
          f"退出diverge={exit_d}, masked={masked} ===")

if __name__ == "__main__":
    main()

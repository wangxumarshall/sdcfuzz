#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_ab_random.py — B组(随机操作数)工作负载的gem5-fi注入sweep

A/B实验对照: A组=operand-dict定向(sdc_probe_workload), B组=随机操作数(sdc_probe_workload_random)。
本脚本对B组跑N次单bit翻转注入, ROI与A组相同区间比例[20%,80%]numCycles,
统计diverge率, 与A组(417次18 diverge 4.3%)对比。

用法 (在0101): python3 gem5_sweep_ab_random.py <num_runs> [--seed S]
"""
import argparse, os, random, shutil, subprocess, re
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
WORKLOAD = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_random")
# B组 golden (baseline): SUM=10721424292087689827 CRC=6728fc4a, numCycles=71215
GOLDEN_NUMCYCLES = 71215
ROI_LO = int(GOLDEN_NUMCYCLES * 0.20)   # 14243
ROI_HI = int(GOLDEN_NUMCYCLES * 0.80)   # 56972
GOLDEN_STDOUT = "SUM=10721424292087689827 CRC=6728fc4a"

def run_one(i, first_clock, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5, "-r", "-e", "--silent-redirect", "-d", outdir, SCRIPT,
           "--binary", WORKLOAD, "--mode", "inject",
           "--first-clock", str(first_clock), "--max-faults", "1", "--probability", "1.0"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
    except subprocess.TimeoutExpired:
        return {"workload": "", "fault": "timeout"}
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
    return {"workload": wl, "fault": faults.splitlines()[0] if faults else ""}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("num_runs", type=int)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    runs_dir = os.path.expanduser("~/gem5-fi/smoke_test/ab_random_runs")
    if os.path.exists(runs_dir): shutil.rmtree(runs_dir)
    os.makedirs(runs_dir, exist_ok=True)
    print(f"B组(随机操作数) ROI: [{ROI_LO},{ROI_HI}] (20-80% of {GOLDEN_NUMCYCLES})")
    print(f"Golden: {GOLDEN_STDOUT}")
    print(f"{'#':>3} {'fc':>7} {'class':>10}  workload")
    clean=exit_d=masked=noout=0
    for i in range(args.num_runs):
        fc = rng.randint(ROI_LO, ROI_HI)
        outdir = os.path.join(runs_dir, f"run_{i:03d}")
        r = run_one(i, fc, outdir)
        wl = r["workload"]
        if not wl: cls="nooutput"; noout+=1
        elif wl==GOLDEN_STDOUT: cls="masked"; masked+=1
        elif "Exiting" in wl: cls="exit_div"; exit_d+=1
        else: cls="DIVERGE"; clean+=1
        if cls in ("DIVERGE","exit_div"):
            print(f"{i:>3} {fc:>7} {cls:>10}  {wl[:60]}")
    total=clean+exit_d+masked+noout
    print(f"\n=== B组: {total} runs, 干净diverge={clean} ({100*clean/total:.1f}%), 退出={exit_d}, masked={masked} ===")
    print(f"=== A组(operand-dict, 已测): 417 runs, 18 diverge 4.3% ===")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_sdc_probe.py — 对 sdc_probe_workload 做多次单 bit 翻转注入, 找 diverge

把 silifuzz SDC 检测用例核心 (e1进位链/e3翻转率/f1 subnormal/v4 LSU往返) 包装的
工作负载, 在 gem5 TaiShan V110 模型上做 N 次单 bit 翻转故障注入 (maxFaults=1),
ROI 在 [20%,80%] numCycles 内随机采样。比较 SUM/CRC 与 golden, 统计 diverge 率
(SDC 检出率)。

用法 (在 0101 上): python3 gem5_sweep_sdc_probe.py <num_runs> [--seed S]
依赖: /home/sdc/wangxu/gem5-fi (root 软链 ~/gem5-fi)
"""
import argparse, os, random, shutil, subprocess, sys
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
WORKLOAD = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload")
HERE = os.path.dirname(os.path.abspath(__file__))
# sdc_probe_workload golden numCycles = 63788 (ITERS=200)
GOLDEN_NUMCYCLES = 63788
ROI_LO = int(GOLDEN_NUMCYCLES * 0.20)
ROI_HI = int(GOLDEN_NUMCYCLES * 0.80)
GOLDEN_STDOUT = "SUM=1176263118239748788 CRC=5b8846f3"

def run_one(i, first_clock, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5, "-r", "-e", "--silent-redirect", "-d", outdir, SCRIPT,
           "--binary", WORKLOAD, "--mode", "inject",
           "--first-clock", str(first_clock), "--max-faults", "1", "--probability", "1.0"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
    simout = ""
    p = os.path.join(outdir, "simout.txt")
    if os.path.exists(p):
        with open(p) as f: simout = f.read()
    wl = ""
    for line in simout.splitlines():
        if "SUM=" in line: wl = line.strip(); break
    faults = ""
    fp = os.path.join(outdir, "fault_injections.log")
    if os.path.exists(fp):
        with open(fp) as f: faults = f.read().strip()
    return {"gem5rc": proc.returncode, "workload": wl, "fault": faults.splitlines()[0] if faults else ""}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("num_runs", type=int)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    runs_dir = os.path.expanduser("~/gem5-fi/smoke_test/sdc_sweep_runs")
    if os.path.exists(runs_dir): shutil.rmtree(runs_dir)
    os.makedirs(runs_dir, exist_ok=True)
    print(f"ROI: [{ROI_LO}, {ROI_HI}] cycles (20%-80% of golden numCycles={GOLDEN_NUMCYCLES})")
    print(f"Golden: {GOLDEN_STDOUT}")
    print(f"Running {args.num_runs} single-injection sims...")
    print(f"{'#':>3} {'firstClock':>10} {'gem5rc':>6} {'class':>10}  workload_line")
    diverge = 0
    for i in range(args.num_runs):
        fc = rng.randint(ROI_LO, ROI_HI)
        outdir = os.path.join(runs_dir, f"run_{i:03d}")
        r = run_one(i, fc, outdir)
        cls = "DIVERGE" if (r["workload"] and r["workload"] != GOLDEN_STDOUT) else ("masked" if r["workload"] == GOLDEN_STDOUT else "nooutput")
        if cls == "DIVERGE": diverge += 1
        print(f"{i:>3} {fc:>10} {r['gem5rc']:>6} {cls:>10}  {r['workload']}  | {r['fault']}")
    print(f"\n=== {args.num_runs} runs: {diverge} diverge (SDC 检出率 {100*diverge/args.num_runs:.1f}%) ===")

if __name__ == "__main__":
    main()

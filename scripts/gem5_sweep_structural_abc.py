#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_structural_abc.py — 结构故障(byte_lane_skew)A/B/C注入sweep

Paper2 best-paper第5微小步骤。bit-flip度量CSP定向未击败随机(C=3.7%<B=8.0%),
结构故障度量是第二机会: CSP定向操作数激活load-data-return路径, byte_lane_skew
结构故障打中forwarding datapath更易diverge。

对A(朴素operand字典)/B(随机)/C(CSP定向配对)三组工作负载, 各跑N次byte_lane_skew
注入, 统计diverge率。目标: C > B (结构度量击败随机)。

用法(0101, 需gem5重编译后): python3 gem5_sweep_structural_abc.py <group> <num_runs> [--seed S]
  group: A=sdc_probe_workload, B=sdc_probe_workload_random, C=sdc_probe_workload_csp
"""
import argparse, os, random, shutil, subprocess, sys
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
SCRIPT_DIR = os.path.expanduser("~/gem5-fi/smoke_test")
WL = {
    "A": os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload"),
    "B": os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_random"),
    "C": os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_csp"),
}
GOLDEN = {
    "A": "SUM=1176263118239748788 CRC=5b8846f3",
    "B": "SUM=10721424292087689827 CRC=6728fc4a",
    "C": "SUM=1626623080976798388 CRC=79113488",
}
NUMCYCLES = {"A": 63788, "B": 71215, "C": 63343}

def run_one(i, fc, group, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5,"-r","-e","--silent-redirect","-d",outdir,SCRIPT,
           "--binary",WL[group],"--mode","inject","--injector","lsq_fwd",
           "--structural-fault","byte_lane_skew","--first-clock",str(fc),
           "--max-faults","1","--probability","1.0","--rng-seed",str(42+i)]
    try: proc = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
    except subprocess.TimeoutExpired: return {"workload":""}
    simout=""
    p=os.path.join(outdir,"simout.txt")
    if os.path.exists(p):
        with open(p,errors='replace') as f: simout=f.read()
    wl=""
    for line in simout.splitlines():
        if "SUM=" in line: wl=line.strip(); break
    return {"workload":wl}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("group", choices=["A","B","C"])
    ap.add_argument("num_runs",type=int)
    ap.add_argument("--seed",type=int,default=42)
    args=ap.parse_args()
    rng=random.Random(args.seed)
    nc=NUMCYCLES[args.group]; ROI_LO=int(nc*0.20); ROI_HI=int(nc*0.80)
    rd=os.path.expanduser(f"~/gem5-fi/smoke_test/struct_{args.group}_runs")
    if os.path.exists(rd): shutil.rmtree(rd)
    os.makedirs(rd,exist_ok=True)
    print(f"结构故障(byte_lane_skew) {args.group}组 ROI:[{ROI_LO},{ROI_HI}] Golden:{GOLDEN[args.group]}")
    clean=exit_d=masked=noout=0
    for i in range(args.num_runs):
        fc=rng.randint(ROI_LO,ROI_HI)
        outdir=os.path.join(rd,f"run_{i:03d}")
        r=run_one(i,fc,args.group,outdir)
        wl=r["workload"]
        if not wl: noout+=1
        elif wl==GOLDEN[args.group]: masked+=1
        elif "Exiting" in wl: exit_d+=1
        else: clean+=1
    total=clean+exit_d+masked+noout
    print(f"=== {args.group}组结构故障: {total} runs, 干净diverge={clean} ({100*clean/total:.1f}%) ===" if total else f"{args.group}: none")

if __name__=="__main__":
    main()

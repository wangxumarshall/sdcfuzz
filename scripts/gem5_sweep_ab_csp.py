#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_ab_csp.py — C组(CSP定向配对)gem5-fi注入sweep

A/B/C对比: A=operand-dict朴素(3.9%), B=随机(8.0%), C=CSP定向配对(目标>B)。
对C组跑N次单bit注入, 统计diverge率, 与A/B对比。
用法(0101): python3 gem5_sweep_ab_csp.py <num_runs> [--seed S]
"""
import argparse, os, random, shutil, subprocess
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
WORKLOAD = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_csp")
GOLDEN_NUMCYCLES = 63343
ROI_LO = int(GOLDEN_NUMCYCLES * 0.20); ROI_HI = int(GOLDEN_NUMCYCLES * 0.80)
GOLDEN_STDOUT = "SUM=1626623080976798388 CRC=79113488"

def run_one(i, fc, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5,"-r","-e","--silent-redirect","-d",outdir,SCRIPT,"--binary",WORKLOAD,
           "--mode","inject","--first-clock",str(fc),"--max-faults","1","--probability","1.0"]
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
    ap.add_argument("num_runs",type=int)
    ap.add_argument("--seed",type=int,default=42)
    args=ap.parse_args()
    rng=random.Random(args.seed)
    rd=os.path.expanduser("~/gem5-fi/smoke_test/ab_csp_runs")
    if os.path.exists(rd): shutil.rmtree(rd)
    os.makedirs(rd,exist_ok=True)
    print(f"C(CSP定向) ROI:[{ROI_LO},{ROI_HI}] Golden:{GOLDEN_STDOUT}")
    clean=exit_d=masked=noout=0
    for i in range(args.num_runs):
        fc=rng.randint(ROI_LO,ROI_HI)
        outdir=os.path.join(rd,f"run_{i:03d}")
        r=run_one(i,fc,outdir)
        wl=r["workload"]
        if not wl: noout+=1
        elif wl==GOLDEN_STDOUT: masked+=1
        elif "Exiting" in wl: exit_d+=1
        else: clean+=1
    total=clean+exit_d+masked+noout
    print(f"=== C组: {total} runs, 干净diverge={clean} ({100*clean/total:.1f}%), 退出={exit_d}, masked={masked} ===")
    print(f"=== A(operand-dict)=3.9% (18/458), B(random)=8.0% (40/500) ===")
    if total and clean:
        print(f"=== A/C={3.9/(100*clean/total):.2f}x, B/C={8.0/(100*clean/total):.2f}x ===")

if __name__=="__main__":
    main()

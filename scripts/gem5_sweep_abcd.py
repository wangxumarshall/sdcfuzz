#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_sweep_abcd.py — A/B/C/D 四组对比 (bit-flip + 结构故障 byte_lane_skew)

A=朴素operand-dict, B=随机, C=CSP配对, D=进化引擎演化。
各跑500次注入, 统计diverge率。目标: D>B (进化击败随机)。
预注册: D≥2×B=显著, 1.5-2×=边际, <1.5×=未击败(诚实)。

用法(0101): python3 gem5_sweep_abcd.py <group> <num_runs> [--seed S] [--structural]
  group: A|B|C|D; --structural: 跑byte_lane_skew(否则bit-flip)
"""
import argparse, os, random, shutil, subprocess
GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
PFX = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload")
WL = {
    "A": PFX,             # 朴素operand-dict
    "B": PFX + "_random", # 随机
    "C": PFX + "_csp",    # CSP配对
    "D": PFX + "_evolved",# 进化引擎演化
}
GOLDEN = {
    "A": "SUM=1176263118239748788 CRC=5b8846f3",
    "B": "SUM=10721424292087689827 CRC=6728fc4a",
    "C": "SUM=1626623080976798388 CRC=79113488",
    "D": "SUM=12547253979180387078 CRC=d1f779e3",
}
NUMCYCLES = {"A":63788, "B":71215, "C":63343, "D":66253}

def run_one(i, fc, group, structural, outdir):
    if os.path.exists(outdir): shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    if structural:
        cmd = [GEM5,"-r","-e","--silent-redirect","-d",outdir,SCRIPT,
               "--binary",WL[group],"--mode","inject","--injector","lsq_fwd",
               "--structural-fault","byte_lane_skew","--first-clock",str(fc),
               "--max-faults","1","--probability","1.0","--rng-seed",str(42+i)]
    else:
        cmd = [GEM5,"-r","-e","--silent-redirect","-d",outdir,SCRIPT,
               "--binary",WL[group],"--mode","inject","--first-clock",str(fc),
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
    ap.add_argument("group", choices=["A","B","C","D"])
    ap.add_argument("num_runs",type=int)
    ap.add_argument("--seed",type=int,default=42)
    ap.add_argument("--structural",action="store_true")
    args=ap.parse_args()
    rng=random.Random(args.seed)
    nc=NUMCYCLES[args.group]; ROI_LO=int(nc*0.20); ROI_HI=int(nc*0.80)
    mode = "结构故障(byte_lane_skew)" if args.structural else "bit-flip"
    rd=os.path.expanduser(f"~/gem5-fi/smoke_test/abcd_{'struct' if args.structural else 'bit'}_{args.group}_runs")
    if os.path.exists(rd): shutil.rmtree(rd)
    os.makedirs(rd,exist_ok=True)
    print(f"{mode} {args.group}组 ROI:[{ROI_LO},{ROI_HI}] Golden:{GOLDEN[args.group]}")
    clean=exit_d=masked=noout=0
    for i in range(args.num_runs):
        fc=rng.randint(ROI_LO,ROI_HI)
        outdir=os.path.join(rd,f"run_{i:03d}")
        r=run_one(i,fc,args.group,args.structural,outdir)
        wl=r["workload"]
        if not wl: noout+=1
        elif wl==GOLDEN[args.group]: masked+=1
        elif "Exiting" in wl: exit_d+=1
        else: clean+=1
    total=clean+exit_d+masked+noout
    if total:
        print(f"=== {args.group}组{mode}: {total} runs, 干净diverge={clean} ({100*clean/total:.1f}%) ===")

if __name__=="__main__":
    main()
# D5 group (全寄存器ACE最大化)
WL_D5 = PFX + "_d5"
GOLDEN_D5 = "SUM=17836490570859964148 CRC=5837cfd3"
NUMCYCLES_D5 = 69171

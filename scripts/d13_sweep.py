import os, random, shutil, subprocess, sys
GEM5=os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT=os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
WL=os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_d13")
GOLDEN="SUM=118831515424667458 CRC=dbc8bf2a"
NC=110946; ROI_LO=int(NC*0.2); ROI_HI=int(NC*0.8)
def sweep(mode, n_runs, seed, structural=False):
    rng=random.Random(seed)
    rd=os.path.expanduser(f"~/gem5-fi/smoke_test/d13_{mode}_runs")
    if os.path.exists(rd): shutil.rmtree(rd)
    os.makedirs(rd)
    c=e=m=n=0
    for i in range(n_runs):
        fc=rng.randint(ROI_LO,ROI_HI)
        out=os.path.join(rd,f"run_{i:03d}")
        os.makedirs(out)
        cmd=[GEM5,"-r","-e","--silent-redirect","-d",out,SCRIPT,"--binary",WL,
             "--mode","inject","--first-clock",str(fc),"--max-faults","1",
             "--probability","1.0","--rng-seed",str(seed+i)]
        if structural: cmd+=["--injector","lsq_fwd","--structural-fault","byte_lane_skew"]
        try: subprocess.run(cmd,capture_output=True,text=True,timeout=200)
        except: n+=1; continue
        sp=os.path.join(out,"simout.txt")
        if not os.path.exists(sp): n+=1; continue
        t=open(sp,errors="replace").read()
        w=""
        for l in t.splitlines():
            if "SUM=" in l: w=l.strip(); break
        if not w: n+=1
        elif w==GOLDEN: m+=1
        elif "Exiting" in w: e+=1
        else: c+=1
    tot=c+e+m+n
    print(f"D13 {mode}: total={tot} clean={c} ({100*c/tot:.1f}%) exit={e} masked={m}")
mode=sys.argv[1] if len(sys.argv)>1 else "bit"
n=int(sys.argv[2]) if len(sys.argv)>2 else 500
s=int(sys.argv[3]) if len(sys.argv)>3 else 42
sweep("struct" if mode=="struct" else "bit",n,s,structural=(mode=="struct"))

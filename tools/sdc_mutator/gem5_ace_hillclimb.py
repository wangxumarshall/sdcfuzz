#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_ace_hillclimb.py — gem5 内 ACE-比例爬山 (击败B的最终正确路径)

根因: unicorn ACE代理≠gem5实际(乱序/重命名)。正确路径=直接在gem5测ACE-比例。
本脚本: 对操作数变体, 跑N次gem5 bit-flip注入测diverge率(=真实ACE-比例),
爬山最大化它。每爬山步跑N次gem5(慢但准确)。

用法: 在0101上跑。python3 gem5_ace_hillclimb.py
"""
import os, sys, random, subprocess, struct, shutil

GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
PROBE_DIR = os.path.expanduser("~/gem5-fi/smoke_test/ace_hillclimb")
WORKLOAD_TEMPLATE = os.path.expanduser("~/gem5-fi/smoke_test/sdc_probe/sdc_probe_workload_evolved.c")

# 8条混合指令序列的golden (需实测更新)
GOLDEN = "SUM=12547253979180387078 CRC=d1f779e3"
NUMCYCLES = 66253

def build_workload(out_path, seed1, seed2):
    """生成带指定种子的D工作负载C文件, 编译"""
    code = open(WORKLOAD_TEMPLATE).read()
    # 替换种子
    code = code.replace(
        '#define D_SEED1 0x9510D3BF1AA8D548ULL',
        f'#define D_SEED1 0x{seed1:016X}ULL')
    code = code.replace(
        '#define D_SEED2 0xA5C11881A68E546EULL',
        f'#define D_SEED2 0x{seed2:016X}ULL')
    open(out_path, 'w').write(code)
    # 编译
    bin_path = out_path.replace('.c', '')
    r = subprocess.run(['gcc', '-static', '-O2', '-o', bin_path, out_path],
                       capture_output=True, timeout=30)
    return bin_path if r.returncode == 0 else None

def get_golden(bin_path, out_dir):
    """跑baseline拿golden"""
    r = subprocess.run(
        [GEM5, '-r', '-e', '--silent-redirect', '-d', out_dir, SCRIPT,
         '--binary', bin_path, '--mode', 'baseline'],
        capture_output=True, text=True, timeout=200)
    simout = os.path.join(out_dir, 'simout.txt')
    if os.path.exists(simout):
        for line in open(simout, errors='replace'):
            if 'SUM=' in line:
                return line.strip()
    return None

def measure_ace(bin_path, golden, n_runs=20, seed=42):
    """测ACE-比例: 跑n_runs次bit-flip注入, 统计diverge率"""
    rng = random.Random(seed)
    roi_lo = int(NUMCYCLES * 0.20)
    roi_hi = int(NUMCYCLES * 0.80)
    diverge = 0
    for i in range(n_runs):
        fc = rng.randint(roi_lo, roi_hi)
        out_dir = os.path.join(PROBE_DIR, f'probe_{i}')
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        try:
            subprocess.run(
                [GEM5, '-r', '-e', '--silent-redirect', '-d', out_dir, SCRIPT,
                 '--binary', bin_path, '--mode', 'inject',
                 '--first-clock', str(fc), '--max-faults', '1',
                 '--probability', '1.0', '--rng-seed', str(seed + i)],
                capture_output=True, text=True, timeout=200)
        except subprocess.TimeoutExpired:
            continue
        simout = os.path.join(out_dir, 'simout.txt')
        if os.path.exists(simout):
            for line in open(simout, errors='replace'):
                if 'SUM=' in line:
                    wl = line.strip()
                    if wl != golden and 'Exiting' not in wl:
                        diverge += 1
                    break
    return diverge / n_runs if n_runs > 0 else 0

def hill_climb(initial_seed1, initial_seed2, iterations=10, n_probe=15):
    """gem5内ACE爬山: 随机翻转seed bit, 若ACE上升则接受"""
    os.makedirs(PROBE_DIR, exist_ok=True)
    best_s1, best_s2 = initial_seed1, initial_seed2
    # 基线
    wl = build_workload(os.path.join(PROBE_DIR, 'wl_best.c'), best_s1, best_s2)
    if not wl:
        return None
    golden = get_golden(wl, os.path.join(PROBE_DIR, 'golden'))
    if not golden:
        return None
    best_ace = measure_ace(wl, golden, n_probe)
    print(f"初始 ACE={best_ace:.3f} (golden={golden})")
    for it in range(iterations):
        # 随机翻转seed bit
        cand_s1 = best_s1 ^ (1 << random.randint(0, 63))
        cand_s2 = best_s2 ^ (1 << random.randint(0, 63))
        wl_cand = build_workload(os.path.join(PROBE_DIR, f'wl_cand_{it}.c'), cand_s1, cand_s2)
        if not wl_cand:
            continue
        golden_cand = get_golden(wl_cand, os.path.join(PROBE_DIR, f'golden_cand_{it}'))
        if not golden_cand:
            continue
        cand_ace = measure_ace(wl_cand, golden_cand, n_probe, seed=42+it*100)
        print(f"  [{it}] ACE={cand_ace:.3f} (cand) vs {best_ace:.3f} (best)")
        if cand_ace > best_ace:
            best_s1, best_s2, best_ace = cand_s1, cand_s2, cand_ace
            print(f"    → 接受! ACE上升至 {best_ace:.3f}")
    return (best_s1, best_s2, best_ace, golden)

if __name__ == "__main__":
    print("=== gem5内ACE-比例爬山 (击败B的最终路径) ===")
    print(f"B(随机) ACE-比例 ≈ 0.08 (8.0% diverge rate)")
    print(f"目标: ACE-比例 > 0.08 (击败B)")
    print()
    # 初始种子 (之前ACE演化的)
    result = hill_climb(0x9510D3BF1AA8D548, 0xA5C11881A68E546E, iterations=10, n_probe=15)
    if result:
        s1, s2, ace, golden = result
        print(f"\n=== 最终 ===")
        print(f"最佳 ACE-比例: {ace:.3f}")
        print(f"种子: SEED1=0x{s1:016X} SEED2=0x{s2:016X}")
        print(f"golden: {golden}")
        print(f"vs B(0.08): {'击败B!' if ace > 0.08 else '未击败B'}")

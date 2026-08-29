#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_ace_scanner.py — gem5 内 ACE-比例扫描器

对工作负载, 扫描每个物理寄存器(target-phys-idx 0..N), 每个跑多次注入,
统计哪些物理寄存器的翻转导致 diverge(=ACE)。得到真实 ACE-比例。
用于对比 B vs D 的 ACE-比例, 确认根因, 并指导爬山。

用法(0101): python3 gem5_ace_scanner.py <workload> <golden> <numcycles> [--n-probe N]
"""
import os, sys, random, shutil, subprocess, argparse, json

GEM5 = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
SCRIPT = os.path.expanduser("~/gem5-fi/smoke_test/configs/two_level_taishan.py")
OUT_BASE = os.path.expanduser("~/gem5-fi/smoke_test/ace_scan")

def scan_ace(workload, golden, numcycles, n_phys=128, n_probes_per_phys=3, seed=42):
    """扫描每个物理寄存器的 ACE-比例"""
    rng = random.Random(seed)
    roi_lo = int(numcycles * 0.20)
    roi_hi = int(numcycles * 0.80)
    results = {}  # phys_idx -> {diverge_count, total, is_free_count}
    out_dir = os.path.join(OUT_BASE, os.path.basename(workload))
    os.makedirs(out_dir, exist_ok=True)

    total_injections = 0
    total_diverge = 0

    for phys_idx in range(n_phys):
        results[phys_idx] = {'diverge': 0, 'total': 0, 'free': 0}
        for probe in range(n_probes_per_phys):
            fc = rng.randint(roi_lo, roi_hi)
            run_dir = os.path.join(out_dir, f'phys{phys_idx}_p{probe}')
            if os.path.exists(run_dir):
                shutil.rmtree(run_dir)
            os.makedirs(run_dir)
            try:
                subprocess.run(
                    [GEMS := GEM5, '-r', '-e', '--silent-redirect', '-d', run_dir,
                     SCRIPT, '--binary', workload, '--mode', 'inject',
                     '--injector', 'phys', '--target-phys-idx', str(phys_idx),
                     '--first-clock', str(fc), '--max-faults', '1',
                     '--probability', '1.0', '--rng-seed', str(seed + phys_idx * 100 + probe)],
                    capture_output=True, text=True, timeout=200)
            except subprocess.TimeoutExpired:
                continue
            # 检查 diverge
            simout = os.path.join(run_dir, 'simout.txt')
            fault_log = os.path.join(run_dir, 'fault_injections.log')
            if os.path.exists(simout):
                wl = ""
                for line in open(simout, errors='replace'):
                    if 'SUM=' in line:
                        wl = line.strip()
                        break
                results[phys_idx]['total'] += 1
                total_injections += 1
                if wl and wl != golden and 'Exiting' not in wl:
                    results[phys_idx]['diverge'] += 1
                    total_diverge += 1
            # 检查 free/inactive
            if os.path.exists(fault_log):
                for line in open(fault_log, errors='replace'):
                    if 'Inactive' in line or 'free' in line.lower():
                        results[phys_idx]['free'] += 1

    # 汇总
    ace_fraction = total_diverge / total_injections if total_injections else 0
    active_regs = sum(1 for r in results.values() if r['total'] > 0 and r['free'] < r['total'])
    ace_regs = sum(1 for r in results.values() if r['diverge'] > 0)
    print(f"\n=== ACE 扫描结果: {os.path.basename(workload)} ===")
    print(f"总注入: {total_injections}")
    print(f"总 diverge: {total_diverge}")
    print(f"ACE-比例: {ace_fraction:.4f} ({100*ace_fraction:.1f}%)")
    print(f"活跃物理寄存器数(至少1次非free): {active_regs}")
    print(f"ACE物理寄存器数(至少1次diverge): {ace_regs}")
    print(f"ACE寄存器分布(前10):")
    for idx in sorted(results.keys()):
        r = results[idx]
        if r['diverge'] > 0:
            print(f"  PhysReg[{idx}]: diverge={r['diverge']}/{r['total']} free={r['free']}")
    # 保存结果
    with open(os.path.join(out_dir, 'ace_scan.json'), 'w') as f:
        json.dump({'ace_fraction': ace_fraction, 'total_diverge': total_diverge,
                   'total_injections': total_injections, 'results': results}, f, indent=2)
    return ace_fraction, results

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('workload', help='工作负载二进制路径')
    ap.add_argument('golden', help='golden SUM/CRC 输出')
    ap.add_argument('numcycles', type=int, help='numCycles')
    ap.add_argument('--n-phys', type=int, default=128)
    ap.add_argument('--n-probe', type=int, default=3)
    args = ap.parse_args()
    scan_ace(args.workload, args.golden, args.numcycles, args.n_phys, args.n_probe)

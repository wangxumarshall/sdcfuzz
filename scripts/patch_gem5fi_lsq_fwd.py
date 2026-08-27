#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""patch_gem5fi_lsq_fwd.py — 给 two_level_taishan.py 加 CHAOSLSQFwd 结构注入器

Paper2 best-paper第4微小步骤: 启用结构故障注入(byte_lane_skew)做A/B/C结构度量。
two_level_taishan.py 当前只有 CHAOSReg/CHAOSPhysReg (bit-flip), 没接 CHAOSLSQFwd
(PAPER.md已实现H5但smoke_test配置没wire)。本补丁加:
  - add_chaos_lsq_fwd() 函数实例化 CHAOSLSQFwd
  - --injector lsq_fwd 选项
  - --structural-fault (none|byte_lane_skew|all_zero) 参数
  - --skew-bytes 参数

用法(0101): python3 patch_gem5fi_lsq_fwd.py <two_level_taishan.py>
"""
import sys, re

def patch(path):
    src = open(path).read()
    # 1. 加 add_chaos_lsq_fwd 函数 (在 add_chaos_phys 后)
    if "def add_chaos_lsq_fwd" not in src:
        lsq_func = '''
def add_chaos_lsq_fwd(system, first_clock=0, max_faults=0, probability=1.0,
                      fault_type="bit_flip", bits=1, rng_seed=0,
                      structural_fault="byte_lane_skew", skew_bytes=0):
    # CHAOSLSQFwd: store-to-load forwarding-path structural fault injector (O3).
    # structuralFault=byte_lane_skew models core-179 D1 (load returned rol_k(stale)).
    fi = CHAOSLSQFwd(
        cpu=system.cpu,
        probability=probability,
        faultType=fault_type,
        bitsToChange=bits,
        firstClock=first_clock,
        lastClock=0,
        maxFaults=max_faults,
        rngSeed=rng_seed,
        structuralFault=structural_fault,
        skewBytes=skew_bytes,
        writeLog=True,
    )
    system.CHAOSLSQFwd = fi
'''
        # 插在 add_chaos_phys 函数后 (system.CHAOSPhysReg = fi 后)
        src = src.replace(
            "    system.CHAOSPhysReg = fi\n",
            "    system.CHAOSPhysReg = fi\n" + lsq_func, 1)
    # 2. 扩展 --injector choices 加 lsq_fwd
    src = src.replace(
        'choices=["reg", "phys"], default="reg"',
        'choices=["reg", "phys", "lsq_fwd"], default="reg"', 1)
    # 3. 加 --structural-fault + --skew-bytes 参数 (在 --fault-mask 后)
    if "--structural-fault" not in src:
        src = src.replace(
            '_ap.add_argument("--fault-mask", type=lambda x: int(x,0), default=0,\n                help="fixed fault mask (0=random); for equivalence tests across modes")',
            '_ap.add_argument("--fault-mask", type=lambda x: int(x,0), default=0,\n                help="fixed fault mask (0=random); for equivalence tests across modes")\n_ap.add_argument("--structural-fault", default="none",\n                choices=["none","byte_lane_skew","all_zero"],\n                help="CHAOSLSQFwd structural fault (P-D1); default none")\n_ap.add_argument("--skew-bytes", type=int, default=0,\n                help="byte_lane_skew rotation 1..7; 0=random per event")',
            1)
    # 4. 在 inject 分支加 lsq_fwd 处理 (else 分支后)
    if "_args.injector == \"lsq_fwd\"" not in src:
        # 找 else: add_chaos(...) 块后加 elif
        src = src.replace(
            "    else:\n        add_chaos(",
            "    elif _args.injector == \"lsq_fwd\":\n        add_chaos_lsq_fwd(\n            system,\n            first_clock=_args.first_clock,\n            max_faults=_args.max_faults,\n            probability=_args.probability,\n            fault_type=_args.fault_type,\n            bits=_args.bits,\n            rng_seed=_args.rng_seed,\n            structural_fault=_args.structural_fault,\n            skew_bytes=_args.skew_bytes,\n        )\n    else:\n        add_chaos(",
            1)
    open(path, 'w').write(src)
    print(f"Patched {path}: add_chaos_lsq_fwd + --injector lsq_fwd + --structural-fault")

if __name__ == "__main__":
    patch(sys.argv[1])

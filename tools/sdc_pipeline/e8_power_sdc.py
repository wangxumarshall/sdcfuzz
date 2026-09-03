#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""e8_power_sdc.py — E8: 功耗应力与 SDC 检出率因果关系 (scheme §5.3 H1/H2/H3 框架内首检)。

H1: 功耗越高 → SDC 脆弱性越强 (检出率越高)
H2: 功耗跳变 (Type-II) vs 持续高功耗 (Type-I) 哪个更易触发 SDC
H3: 定向应力 (单一结构) vs 全局应力

设计 (框架内最小可检版):
- 基础种子 (D13 风格 ALU 链) 派生 3 组候选:
  A 组 baseline: 种子本身 (无应力)
  B 组 Type-I: PowerStressMutator type1 子代 (持续高翻转前置)
  C 组 Type-II: PowerStressMutator type2 子代 (高低交替)
- 每组 3 个候选 × gem5 bit×15 注入 → 检出率
- McPAT 功耗分组对比 + Fisher 检验 (组间)
- 诚实边界: gem5 O3 不能建模真实电压降/时序 — Type-I/II 在 gem5 里的
  "功耗差异"只是指令构成差异; 真实 di/dt 效应需真机验证 (Layer 3/4)
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.sdc_experiment.sim_sweep import fisher_exact
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.evaluators import TogglePowerEvaluator
from tools.sdc_pipeline.mcpat_eval import McPATEvaluator
from tools.sdc_pipeline.mutators import PowerStressMutator
from tools.sdc_pipeline.gem5_runner import Gem5Validator

SEED_ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    adds    x0, x1, x2
    eor     x3, x0, x1
    and     x4, x3, x2
    adds    x5, x4, x3
    eor     x6, x5, x0
    orr     x7, x6, x4
    adds    x8, x7, x5
    eor     x9, x8, x6
"""
N_CAND_PER_ARM = 3
INJECT_RUNS = 15


def main():
    out_dir = "output/experiments/sdc_pipeline_power_sdc"
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(2026)
    regs = {i: rng.getrandbits(64) for i in range(10)}
    seed = make_candidate(SEED_ASM, regs, [], "seed:e8", structure_tags=["alu"])

    arms = {"A_baseline": [seed]}
    t1 = PowerStressMutator(stress_type=1, n_children=N_CAND_PER_ARM).mutate(seed, random.Random(1))
    t2 = PowerStressMutator(stress_type=2, n_children=N_CAND_PER_ARM).mutate(seed, random.Random(2))
    arms["B_type1_sustained"] = t1[:N_CAND_PER_ARM]
    arms["C_type2_oscillating"] = t2[:N_CAND_PER_ARM]

    validator = Gem5Validator(out_root=os.path.join(out_dir, "gem5"))
    mcpat = McPATEvaluator()
    toggle = TogglePowerEvaluator()
    results = {}
    for arm, cands in arms.items():
        runs, diverge = 0, 0
        powers, toggles = [], []
        for c in cands:
            g = validator.register_golden(c)
            if g is None:
                print(f"[{arm}] {c.ident}: golden FAILED (跳过)")
                continue
            m = mcpat.evaluate(c)
            t = toggle.evaluate(c)
            powers.append(m["power_mcpat_w"])
            toggles.append(t["toggle_power_proxy"])
            r = validator.validate_detection(c, n_runs=INJECT_RUNS,
                                             mode="bit", seed=88)
            runs += r["n"]
            diverge += r["clean_diverge"]
            print(f"[{arm}] {c.ident}: mcpat={m['power_mcpat_w']}W "
                  f"toggle={t['toggle_power_proxy']:.4f} "
                  f"bit diverge={r['clean_diverge']}/{r['n']}")
        rate = diverge / runs if runs else 0.0
        results[arm] = {"runs": runs, "diverge": diverge, "rate": round(rate, 4),
                        "mcpat_mean": round(sum(powers) / len(powers), 4) if powers else 0,
                        "toggle_mean": round(sum(toggles) / len(toggles), 6) if toggles else 0}
        print(f"[{arm}] 合计: {diverge}/{runs} rate={rate:.3f}")

    # H1: 功耗 (McPAT) 与检出率的组间方向
    print("\n" + "=" * 66)
    a, b, c = results["A_baseline"], results["B_type1_sustained"], results["C_type2_oscillating"]
    # Fisher: baseline vs type1, baseline vs type2, type1 vs type2
    def fisher(x, y):
        return fisher_exact(x["diverge"], x["runs"] - x["diverge"],
                            y["diverge"], y["runs"] - y["diverge"])
    or1, p1 = fisher(a, b)
    or2, p2 = fisher(a, c)
    or3, p3 = fisher(b, c)
    print(f"H1 功耗-检出率方向: mcpat A={a['mcpat_mean']} B={b['mcpat_mean']} C={c['mcpat_mean']}W")
    print(f"   检出率 A={a['rate']} B={b['rate']} C={c['rate']}")
    h1_dir = "positive" if (b['mcpat_mean'] > a['mcpat_mean']) == (b['rate'] >= a['rate']) else "mixed"
    print(f"   → 方向一致性: {h1_dir} (McPAT 单元duty功耗 ≠ 真实电压降, gem5 无法验证物理 H1)")
    print(f"H2 Type-I vs Type-II: OR={or3:.3f} p={p3:.4g}")
    print(f"   对照 baseline: A-vs-B OR={or1:.3f} p={p1:.4g}; A-vs-C OR={or2:.3f} p={p2:.4g}")
    verdict = "INSUFFICIENT" if min(p1, p2, p3) >= 0.05 else "SIGNIFICANT"
    print(f"   → {verdict} (样本 {INJECT_RUNS}×{N_CAND_PER_ARM}/组)")
    print("诚实边界: gem5 O3 无电压/时序模型, Type-I/II 在仿真中只是指令构成差异;")
    print("物理功耗-SDC 因果 (真实 di/dt) 需真机 Layer 3/4 验证 — 本实验检验的是")
    print("'指令构成维度上的功耗代理与检出率是否同向', 这是框架能诚实回答的部分。")
    summary = {"experiment": "E8_power_sdc", "arms": results,
               "fisher": {"A_vs_B": [or1, p1], "A_vs_C": [or2, p2], "B_vs_C": [or3, p3]},
               "verdict": verdict,
               "config": {"n_cand": N_CAND_PER_ARM, "inject_runs": INJECT_RUNS}}
    with open(os.path.join(out_dir, "e8_result.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n结果已存 {out_dir}/e8_result.json")


if __name__ == "__main__":
    main()

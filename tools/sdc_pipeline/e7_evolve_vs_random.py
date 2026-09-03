#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""e7_evolve_vs_random.py — E7: 闭环演化 vs 纯随机基线 (gem5+CHAOS 检出率对照)。

论文核心 claim 的框架内验证: "directed mutation beyond random"。
- EVOLVE 组: Pipeline 闭环 (评估→Filter top-k→下代父本)
- RANDOM 组: 同 mutator 池/同变异次数, 但 Filter=RandomFilter (无反馈盲走)
- 每组取终代 top-K 候选, gem5 golden + bit 注入 n_runs 次
- 统计: 两组 diverge 数 Fisher 精确检验 (sim_sweep.fisher_exact)

公平性: 两组唯一差异是"下代父本选择策略"; 变异预算完全相同。
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.sdc_experiment.sim_sweep import fisher_exact
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.evaluators import (ACEProxyEvaluator, IBREvaluator,
                                           TogglePowerEvaluator)
from tools.sdc_pipeline.filters import WeightedFilter, RandomFilter
from tools.sdc_pipeline.gem5_runner import Gem5Validator
from tools.sdc_pipeline.mutators import (InsnSequenceMutator, OperandBitFlipMutator,
                                         OperandDictMutator)
from tools.sdc_pipeline.pipeline import HillClimbPolicy, Pipeline
from tools.sdc_pipeline.vault import Vault

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

GENS, PER_GEN, TOP_K, FINAL_K = 4, 4, 3, 3
INJECT_RUNS = 20


def run_arm(arm_name, filt, out_dir, rng_seed):
    rng = random.Random(rng_seed)
    regs = {i: rng.getrandbits(64) for i in range(10)}
    seed = make_candidate(SEED_ASM, regs, [], "seed:e7",
                          structure_tags=["alu"])
    vault = Vault(os.path.join(out_dir, f"vault_{arm_name}"))
    mutators = [OperandBitFlipMutator(4), OperandDictMutator(4),
                InsnSequenceMutator(4)]
    evaluators = [ACEProxyEvaluator(n_probes=10, seed=1), IBREvaluator(),
                  TogglePowerEvaluator()]
    pipe = Pipeline(seeds=[seed], mutators=mutators, evaluators=evaluators,
                    filt=filt, vault=vault,
                    policy=HillClimbPolicy([m.name for m in mutators]),
                    rng_seed=rng_seed)
    report = pipe.run(generations=GENS, per_gen_mutations=PER_GEN, top_k=TOP_K)
    return vault, report, pipe


def main():
    out_dir = "output/experiments/sdc_pipeline_e7"
    os.makedirs(out_dir, exist_ok=True)
    real_filt = WeightedFilter({"ace_proxy": 0.6, "ibr": 0.2,
                                "toggle_power_proxy": 0.2})
    results = {}
    validator = Gem5Validator(out_root=os.path.join(out_dir, "gem5"))

    for arm, filt in [("EVOLVE", real_filt),
                      ("RANDOM", RandomFilter(real_filt, rng_seed=999))]:
        print(f"===== {arm} 组: {GENS} 代 × {PER_GEN} 变异 =====")
        t0 = time.time()
        vault, report, pipe = run_arm(arm, filt, out_dir, rng_seed=2026)
        # 终代候选 = 该组**自己演化路径的终态 pool** (pipe.pool)。
        # E7 第一轮分析 bug: 两组都用 vault.top_by(ace) 全局排序 →
        # 选到同一批候选, 组间差异被抹掉 (5/60 vs 5/60 完全打平的假象)。
        # 修正: EVOLVE 的 pool 是 Filter 选的 top, RANDOM 的 pool 是
        # 随机选的 — 各自反映本组策略的终代。
        top = [(c.ident, None) for c in pipe.pool[:FINAL_K]]
        print(f"  闭环完成 ({time.time()-t0:.0f}s), Vault={vault.count_candidates()}, "
              f"终代 pool: {[i for i, _ in top]}")
        arm_runs, arm_diverge = 0, 0
        for ident, _ace in top:
            cand = vault.get(ident)
            # Candidate 从 vault 取回无 code_bytes, 重编译
            cand = make_candidate(cand.source_asm, cand.regs_init,
                                  cand.parents, cand.origin,
                                  cand.structure_tags)
            g = validator.register_golden(cand)
            if g is None:
                print(f"  {ident}: golden FAILED (跳过, 如实记录)")
                continue
            r = validator.validate_detection(cand, n_runs=INJECT_RUNS,
                                             mode="bit", seed=77)
            arm_runs += r["n"]
            arm_diverge += r["clean_diverge"]
            print(f"  {ident}: bit diverge={r['clean_diverge']}/{r['n']} "
                  f"rate={r['rate']} CI=[{r['wilson_low']},{r['wilson_high']}]")
        results[arm] = {"runs": arm_runs, "diverge": arm_diverge,
                        "candidates": [(i, v) for i, v in top]}
        print(f"  {arm} 合计: {arm_diverge}/{arm_runs}")

    # Fisher 精确检验 (EVOLVE vs RANDOM)
    a = results["EVOLVE"]["diverge"]; b = results["EVOLVE"]["runs"] - a
    c = results["RANDOM"]["diverge"]; d = results["RANDOM"]["runs"] - c
    orv, p = fisher_exact(a, b, c, d)
    rate_e = a / results["EVOLVE"]["runs"] if results["EVOLVE"]["runs"] else 0
    rate_r = c / results["RANDOM"]["runs"] if results["RANDOM"]["runs"] else 0
    verdict = "BEAT" if (rate_e > rate_r and p < 0.05) else \
              ("TIE/INSUFFICIENT" if p >= 0.05 else "WORSE")
    print("\n" + "=" * 62)
    print(f"E7 结果: EVOLVE {a}/{results['EVOLVE']['runs']} ({rate_e:.3f}) vs "
          f"RANDOM {c}/{results['RANDOM']['runs']} ({rate_r:.3f})")
    print(f"Fisher: OR={orv:.3f} p={p:.4g} → {verdict}")
    print("诚实边界: 单种子单次实验, 样本有限; gem5 O3 ≠ TSV110 RTL")
    summary = {"experiment": "E7", "evolve": results["EVOLVE"],
               "random": results["RANDOM"], "fisher": {"odds_ratio": orv, "p": p},
               "verdict": verdict,
               "config": {"gens": GENS, "per_gen": PER_GEN, "top_k": TOP_K,
                           "final_k": FINAL_K, "inject_runs": INJECT_RUNS}}
    with open(os.path.join(out_dir, "e7_result.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"结果已存 {out_dir}/e7_result.json")


if __name__ == "__main__":
    main()

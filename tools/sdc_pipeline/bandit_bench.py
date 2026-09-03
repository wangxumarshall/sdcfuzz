#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""bandit_bench.py — bandit vs hill-climb 策略基准 (10 种子, 可复现产物)。

回应评审: v2 论文引用的 5/3/2 对比此前只存在于 commit message,
本脚本将其固化为可复现实验 (结果 JSON 落盘)。
"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.evaluators import (ACEProxyEvaluator, IBREvaluator,
                                           TogglePowerEvaluator)
from tools.sdc_pipeline.filters import WeightedFilter
from tools.sdc_pipeline.mutators import (InsnSequenceMutator, OperandBitFlipMutator,
                                         OperandDictMutator)
from tools.sdc_pipeline.pipeline import (EpsilonGreedyBanditPolicy,
                                         HillClimbPolicy, Pipeline)
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
N_TRIALS = 10
GENERATIONS = 8


def main():
    filt = WeightedFilter({"ace_proxy": 0.6, "ibr": 0.2, "toggle_power_proxy": 0.2})
    wins = {"hill": 0, "bandit": 0, "tie": 0}
    detail = []
    for trial in range(N_TRIALS):
        rng = random.Random(1000 + trial)
        regs = {i: rng.getrandbits(64) for i in range(10)}
        seed = make_candidate(SEED_ASM, regs, [], f"seed:bb{trial}",
                              structure_tags=["alu"])
        mutators = [OperandBitFlipMutator(3), OperandDictMutator(3),
                    InsnSequenceMutator(3)]
        mnames = [m.name for m in mutators]
        evaluators = [ACEProxyEvaluator(n_probes=10, seed=1), IBREvaluator(),
                      TogglePowerEvaluator()]
        bests = {}
        for pol_name, policy in [("hill", HillClimbPolicy(mnames)),
                                  ("bandit", EpsilonGreedyBanditPolicy(mnames, epsilon=0.2))]:
            with tempfile.TemporaryDirectory() as td:
                vault = Vault(td)
                pipe = Pipeline(seeds=[seed], mutators=mutators,
                                evaluators=evaluators, filt=filt, vault=vault,
                                policy=policy, rng_seed=1000 + trial)
                pipe.run(generations=GENERATIONS, per_gen_mutations=3, top_k=3)
                bests[pol_name] = max(v for _, v in vault.top_by("ace_proxy", 1000))
        if bests["bandit"] > bests["hill"]:
            wins["bandit"] += 1
        elif bests["hill"] > bests["bandit"]:
            wins["hill"] += 1
        else:
            wins["tie"] += 1
        detail.append({"trial": trial, "hill": bests["hill"],
                       "bandit": bests["bandit"]})
        print(f"trial {trial}: hill={bests['hill']:.3f} bandit={bests['bandit']:.3f}")
    # 符号检验 (双尾): hill 胜 5, bandit 胜 3, tie 2 → 非 tie 的 8 次里 hill 5
    from math import comb
    n_untied = wins["hill"] + wins["bandit"]
    k = max(wins["hill"], wins["bandit"])
    p_sign = sum(comb(n_untied, i) for i in range(k, n_untied + 1)) / 2 ** n_untied * 2
    p_sign = min(1.0, p_sign)
    print(f"\n结果: {wins} (bandit 每代 1 臂 = 1/3 变异预算)")
    print(f"符号检验 (排除 tie): p={p_sign:.3f} → {'无显著差异' if p_sign >= 0.05 else '显著'}")
    out = {"experiment": "bandit_bench", "wins": wins,
           "sign_test_p": round(p_sign, 4), "n_trials": N_TRIALS,
           "generations": GENERATIONS, "detail": detail,
           "note": "bandit 用 1/3 预算 (每代 1 臂 vs 全臂); parity 结论"}
    os.makedirs("output/experiments/bandit_bench", exist_ok=True)
    with open("output/experiments/bandit_bench/result.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("已存 output/experiments/bandit_bench/result.json")


if __name__ == "__main__":
    main()

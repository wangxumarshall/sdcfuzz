#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""e8v2_power_sdc.py — E8v2: 功耗应力-检出率实验加强版 (回应评审)。

相对 E8v1 的整改:
1. 样本量: 每臂 5 候选 × 20 注入 = 100/臂 (达到论文声明的显著性门槛)
2. **长度配平对照臂 D**: 非应力 NOP 填充到与 Type-II 等长 → 隔离
   "程序长度改变故障落点 ROI" 伪影 (评审指出的混杂)
3. 候选级呈现 (per-candidate diverge) + 组级 Fisher, 嵌套结构如实报告
4. 措辞: correlational direction (非 causality)
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

N_CAND = 5
INJECT = 20  # 每候选 20 → 每臂 100


def _body(lines_prefix, lines_suffix=""):
    return (SEED_ASM.replace("_start:\n", "_start:\n" + lines_prefix)
            + lines_suffix)


def build_arms(rng):
    """4 臂 × N_CAND 候选。块长每候选 +1 保证 ident 不撞。"""
    arms = {"A_baseline": [], "B_type1": [], "C_type2": [], "D_lenmatch": []}
    for i in range(N_CAND):
        n = 16 + i
        hi = "\n".join(f"    {'add' if j % 2 == 0 else 'eor'}     x9, x9, x9"
                       for j in range(n))
        lo = "\n".join("    nop" for _ in range(n // 2))
        # Type-I: 高翻转前缀
        t1 = SEED_ASM.replace("_start:\n", "_start:\n" + hi + "\n")
        # Type-II: 高-低-高交替 (总长 = n + n//2 + n = 2.5n)
        t2 = SEED_ASM.replace("_start:\n", "_start:\n" + hi + "\n" + lo + "\n" + hi + "\n")
        # 长度配平: NOP 填充, 总长 == Type-II
        pad = "\n".join("    nop" for _ in range(n + n // 2 + n))
        dl = SEED_ASM.replace("_start:\n", "_start:\n" + pad + "\n")
        arms["A_baseline"].append(SEED_ASM)
        arms["B_type1"].append(t1)
        arms["C_type2"].append(t2)
        arms["D_lenmatch"].append(dl)
    return arms


def main():
    out_dir = "output/experiments/sdc_pipeline_e8v2"
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(2026)
    regs = {i: rng.getrandbits(64) for i in range(10)}
    arms_asm = build_arms(rng)
    validator = Gem5Validator(out_root=os.path.join(out_dir, "gem5"))
    mcpat = McPATEvaluator()
    toggle = TogglePowerEvaluator()
    results = {}
    t_all = time.time()
    for arm, asms in arms_asm.items():
        per_cand = []
        runs = diverge = 0
        for k, asm in enumerate(asms):
            c = make_candidate(asm, regs, [], f"e8v2:{arm}:{k}",
                               structure_tags=["alu", f"{arm}"])
            g = validator.register_golden(c)
            if g is None:
                print(f"[{arm}][{k}] golden FAILED")
                continue
            m = mcpat.evaluate(c)
            r = validator.validate_detection(c, n_runs=INJECT, mode="bit",
                                             seed=500 + k)
            per_cand.append({"ident": c.ident, "n": r["n"],
                             "diverge": r["clean_diverge"],
                             "nc": g["nc"], "mcpat": m["power_mcpat_w"],
                             "insns": len(c.code_bytes) // 4})
            runs += r["n"]
            diverge += r["clean_diverge"]
            print(f"[{arm}][{k}] insns={len(c.code_bytes)//4} nc={g['nc']} "
                  f"mcpat={m['power_mcpat_w']}W div={r['clean_diverge']}/{r['n']}")
        results[arm] = {"runs": runs, "diverge": diverge,
                        "rate": round(diverge / runs, 4) if runs else 0,
                        "per_candidate": per_cand}
        print(f"[{arm}] arm total: {diverge}/{runs} = {results[arm]['rate']:.3f}")
    # 组级 Fisher
    a, b, c_, d = (results["A_baseline"], results["B_type1"],
                   results["C_type2"], results["D_lenmatch"])
    fishers = {}
    for name, (x, y) in {"A_vs_B": (a, b), "A_vs_C": (a, c_),
                         "A_vs_D": (a, d), "C_vs_D": (c_, d),
                         "B_vs_D": (b, d), "B_vs_C": (b, c_)}.items():
        orv, p = fisher_exact(x["diverge"], x["runs"] - x["diverge"],
                              y["diverge"], y["runs"] - y["diverge"])
        fishers[name] = [round(orv, 3), p]
    print("\n" + "=" * 66)
    print("E8v2: 4 臂 × 100 注入 (长度配平对照)")
    for arm in results:
        r = results[arm]
        ic = [pc["insns"] for pc in r["per_candidate"]]
        print(f"  {arm:14s} {r['diverge']}/{r['runs']} = {r['rate']:.3f} "
              f"(insns {min(ic)}-{max(ic)})")
    print("  Fisher:", {k: (v[0], f"p={v[1]:.4g}") for k, v in fishers.items()})
    # 关键判定: C vs D (同长度, 应力 vs 非应力)
    key = fishers["C_vs_D"]
    verdict = ("STRESS EFFECT (C>D 显著)" if key[1] < 0.05 and c_["rate"] > d["rate"]
               else "LENGTH ARTIFACT (C≈D 或反向)" if abs(c_["rate"] - d["rate"]) < 0.05
               else "DIRECTIONAL (未达显著)")
    print(f"  长度配平判定: {verdict}")
    summary = {"experiment": "E8v2", "arms": results, "fisher": fishers,
               "verdict": verdict, "config": {"n_cand": N_CAND, "inject": INJECT},
               "elapsed_s": round(time.time() - t_all)}
    with open(os.path.join(out_dir, "e8v2_result.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"已存 {out_dir}/e8v2_result.json ({summary['elapsed_s']}s)")


if __name__ == "__main__":
    main()

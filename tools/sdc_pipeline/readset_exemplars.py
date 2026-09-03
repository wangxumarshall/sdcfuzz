#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""readset_exemplars.py — 读集感知变异有效性双 exemplar 验证 (回应评审).

Exemplar 1 (M2 案例结构): aware 6/6 vs naive 0/1
Exemplar 2 (mul链+不同覆盖结构): aware 6/6 vs naive 2/6
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.mutators import OperandDictMutator
from tools.sdc_pipeline.gem5_runner import Gem5Validator
from tools.sdc_pipeline.readset import first_read_live

ASM1 = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    adds    x0, x1, x2
    eor     x3, x0, x1
    and     x4, x3, x2
    adds    x5, x4, x3
    eor     x6, x5, x0
"""
ASM2 = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mul     x3, x1, x2
    eor     x4, x3, x1
    and     x5, x4, x2
    orr     x6, x5, x3
    adds    x7, x6, x4
"""

def run_exemplar(tag, asm, out_root, rng_seed):
    rng = random.Random(rng_seed)
    regs = {i: rng.getrandbits(64) for i in range(8)}
    seed = make_candidate(asm, regs, [], f"seed:rs_{tag}", structure_tags=["alu"])
    live = sorted(first_read_live(seed.code_bytes))
    v = Gem5Validator(out_root=out_root)
    g = v.register_golden(seed)
    aware = OperandDictMutator(6, readset_aware=True)
    naive = OperandDictMutator(6, readset_aware=False)
    res = {}
    for name, m in (("aware", aware), ("naive", naive)):
        kids = m.mutate(seed, random.Random(7))
        d = sum(1 for k in kids
                if (gk := v.register_golden(k)) and gk["golden"] != g["golden"])
        res[name] = f"{d}/{len(kids)}"
    print(f"exemplar {tag}: first_read_live={live} aware={res['aware']} naive={res['naive']}")
    return {"exemplar": tag, "live": live, **res}

def main():
    out = "output/experiments/readset_exemplars"
    os.makedirs(out, exist_ok=True)
    r1 = run_exemplar("E1_adds_chain", ASM1, os.path.join(out, "gem5_e1"), 2026)
    r2 = run_exemplar("E2_mul_chain", ASM2, os.path.join(out, "gem5_e2"), 31)
    json.dump([r1, r2], open(os.path.join(out, "result.json"), "w"),
              indent=1, ensure_ascii=False)
    print(f"已存 {out}/result.json")

if __name__ == "__main__":
    main()

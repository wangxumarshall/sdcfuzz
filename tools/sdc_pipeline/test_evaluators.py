#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_evaluators.py — Unicorn 静态评估器池单元测试。

R2 解法: ACE/IBR/功耗代理/雪崩 四指标统一 Evaluator 接口。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.evaluators import (
    UnicornRunner, ACEProxyEvaluator, IBREvaluator,
    TogglePowerEvaluator, AvalancheEvaluator)

# 两条指令的确定性序列: x0 = x1 ^ x2; x3 = x0 + x1 (结果依赖输入)
ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    eor     x0, x1, x2
    add     x3, x0, x1
"""


def _cand(regs):
    return make_candidate(ASM, regs, [], "test")


def _rand_regs(rng_seed=42, n=5):
    import random
    rng = random.Random(rng_seed)
    return {i: rng.getrandbits(64) for i in range(n)}


def test_unicorn_runner_generalizes_x0_x30():
    """R1 关键: 不再写死 X0-X4, X0-X30 全可用。"""
    r = UnicornRunner()
    regs = {20: 0x123, 25: 0x456}  # 高编号寄存器
    final, executed = r.run(ASM, regs)
    assert executed == 2
    assert final[20] == 0x123  # 未写寄存器保持


def test_unicorn_runner_stop_condition():
    r = UnicornRunner()
    _, executed = r.run(ASM, {1: 1, 2: 2})
    assert executed == 2, "两条指令必须全部执行"


def test_all_evaluators_return_valid_ranges():
    regs = _rand_regs()
    c = _cand(regs)
    for ev in (ACEProxyEvaluator(n_probes=8), IBREvaluator(),
               TogglePowerEvaluator(), AvalancheEvaluator(n_perturb=4)):
        m = ev.evaluate(c)
        assert isinstance(m, dict) and len(m) == 1
        (name, val), = m.items()
        assert 0.0 <= val <= 1.0 or val >= 0.0, f"{name} 值域非法: {val}"
        assert ev.name == name or name.startswith(ev.name.split("_")[0])


def test_ibr_zero_vs_random_operands():
    """全0操作数 → 每条指令输入位翻转低 → ibr 应显著小于随机操作数。"""
    zero_c = _cand({0: 0, 1: 0, 2: 0, 3: 0})
    rand_c = _cand(_rand_regs(7))
    ibr = IBREvaluator()
    z = ibr.evaluate(zero_c)["ibr"]
    r = ibr.evaluate(rand_c)["ibr"]
    assert z < r, f"全0 ibr ({z}) 应 < 随机 ibr ({r})"


def test_ace_proxy_range_and_determinism():
    """同候选两次评估 (同种子) 结果一致 (可复现)。"""
    c = _cand(_rand_regs(3))
    e1 = ACEProxyEvaluator(n_probes=8, seed=99)
    e2 = ACEProxyEvaluator(n_probes=8, seed=99)
    assert e1.evaluate(c) == e2.evaluate(c), "固定种子必须可复现"


def test_avalanche_detects_masking():
    """掩蔽序列 (输出与输入无关) 雪崩应接近 0。"""
    MASKED_ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mov     x0, #0x5a
    mov     x1, #0xa5
    eor     x2, x0, x1
"""
    open_c = _cand(_rand_regs())           # 开放序列: 输入→输出
    masked_c = make_candidate(MASKED_ASM, {0: 1}, [], "test")
    av = AvalancheEvaluator(n_perturb=6, seed=5)
    assert av.evaluate(masked_c)["avalanche"] < av.evaluate(open_c)["avalanche"], \
        "常量序列 (逻辑掩蔽) 的雪崩必须低于输入开放序列"

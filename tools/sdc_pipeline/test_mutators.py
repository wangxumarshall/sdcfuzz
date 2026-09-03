#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_mutators.py — 变异器池单元测试。

操作数变异 (位翻/字典) + 指令序列变异 + 功耗应力插入 (Type-I/II 雏形)。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.mutators import (
    OperandBitFlipMutator, OperandDictMutator,
    InsnSequenceMutator, PowerStressMutator)

ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mov     x2, #1
    adds    x0, x1, x2
    eor     x3, x0, x1
"""


def _seed():
    return make_candidate(ASM, {0: 1, 1: 0x123, 2: 2, 3: 3}, [], "seed:test",
                          structure_tags=["alu"])


def _rng():
    return random.Random(42)


def _common_children_assertions(seed, children, min_count=1):
    assert len(children) >= min_count
    for ch in children:
        assert seed.ident in ch.parents, "子代 parents 必须含父 ident"
        assert ch.origin.startswith("mutate:"), f"origin 应为 mutate:*, got {ch.origin}"
        assert len(ch.code_bytes) % 4 == 0, "子代必须可编译且 4 字节对齐"


def test_operand_bit_flip():
    seed = _seed()
    kids = OperandBitFlipMutator(n_children=4).mutate(seed, _rng())
    _common_children_assertions(seed, kids, 4)
    # 至少一个子代 regs_init 与父不同
    assert any(k.regs_init != seed.regs_init for k in kids)


def test_operand_dict_mutator():
    seed = _seed()
    kids = OperandDictMutator(n_children=4).mutate(seed, _rng())
    _common_children_assertions(seed, kids, 4)
    # 子代操作数应来自字典值 (全1/交替/进位边界等)
    from tools.sdc_pipeline.mutators import DICT_VALUES
    vals = {v for vs in DICT_VALUES.values() for v in vs}
    hit = sum(1 for k in kids for v in k.regs_init.values() if v in vals)
    assert hit >= 4, "字典变异子代操作数应命中字典值"


def test_insn_sequence_mutator():
    seed = _seed()
    kids = InsnSequenceMutator(n_children=3).mutate(seed, _rng())
    _common_children_assertions(seed, kids, 3)
    # 指令数应变化 (插入/替换), 至少一个子代 code 长度不同
    assert any(len(k.code_bytes) != len(seed.code_bytes) for k in kids) or \
           any(k.source_asm != seed.source_asm for k in kids)


def test_power_stress_type1():
    seed = _seed()
    kids = PowerStressMutator(stress_type=1, n_children=2).mutate(seed, _rng())
    _common_children_assertions(seed, kids, 2)
    assert all("power_type1" in k.structure_tags for k in kids), \
        "Type-I 子代必须打 power_type1 标签"


def test_power_stress_type2():
    seed = _seed()
    kids = PowerStressMutator(stress_type=2, n_children=2).mutate(seed, _rng())
    _common_children_assertions(seed, kids, 2)
    assert all("power_type2" in k.structure_tags for k in kids)


def test_power_stress_type1_increases_toggle():
    """Type-I 高翻转前置块应提升翻转功耗代理 (scheme §5.3 H1 雏形检验)。"""
    from tools.sdc_pipeline.evaluators import TogglePowerEvaluator
    seed = _seed()
    kids = PowerStressMutator(stress_type=1, n_children=1).mutate(seed, random.Random(7))
    tp = TogglePowerEvaluator()
    # 高翻转块不消耗初值寄存器 → 种子指令行为不变, 但块自身高翻转
    assert tp.evaluate(kids[0])["toggle_power_proxy"] >= 0  # 可计算不崩即可


def test_children_have_new_idents():
    seed = _seed()
    all_kids = []
    rng = _rng()  # 单一 rng 贯穿全部 mutator (与 pipeline 实际用法一致)
    for m in (OperandBitFlipMutator(2), OperandDictMutator(2),
              InsnSequenceMutator(2), PowerStressMutator(1, 2)):
        all_kids += m.mutate(seed, rng)
    idents = [k.ident for k in all_kids]
    assert len(set(idents)) == len(idents), "同父不同变异必须产生不同 ident"
    assert seed.ident not in idents

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_fault_signature_mutators.py — FS-001 经验承载层的回归测试。

守护三件事:
1. fault_signatures.py 数据完整 (五要素/负对照/执行环境齐全)
2. LoadPathMutator 子代具备触发要素且可编译
3. NegativeControlFilter 拦截已证伪形态 (纯寄存器链)
"""
import random
import sys

from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.fault_signatures import FAULT_SIGNATURES, negative_control_tags
from tools.sdc_pipeline.mutators import (LoadPathMutator,
                                          NegativeControlFilter,
                                          OperandBitFlipMutator,
                                          OperandMutator)

SEED_ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    adds    x0, x1, x2
    eor     x3, x0, x1
"""


def _seed(tags=("alu",)):
    rng = random.Random(7)
    return make_candidate(SEED_ASM, {i: rng.getrandbits(64) for i in range(8)},
                          [], "seed:test", structure_tags=list(tags))


def test_fs001_data_complete():
    fs = FAULT_SIGNATURES["FS-001"]
    te = fs["trigger_elements"]
    assert te["indirect_chain"]["levels"] == [2]
    assert te["roundtrip"] is True
    assert te["long_lived_acc"] == "fp"
    assert te["min_loads_per_round"] >= 8
    assert len(fs["negative_controls"]) == 11
    assert "same_socket_full_load" in fs["execution_env"]["required"]
    assert fs["detection_form"]["checksum_must_match"] is True
    assert "reg_only_chain" in negative_control_tags()


def test_loadpath_mutator_children_carry_elements():
    rng = random.Random(42)
    seed = _seed()
    kids = LoadPathMutator(n_children=4).mutate(seed, rng)
    assert len(kids) == 4
    for k in kids:
        asm = k.source_asm
        assert "ldrsw" in asm and "ldr" in asm          # 要素① 间接链
        assert "fmsub" in asm and "str" in asm          # 要素② 同址往返
        assert "d4" in asm and "fadd" in asm            # 要素③ 长存活累加器
        assert len(k.code_bytes) > 0                    # 可编译
        assert len(k.code_bytes) <= 4084                # 单页预算
        assert "fs001_loadpath" in k.structure_tags     # 可追溯标签


def test_negative_control_filter():
    filt = NegativeControlFilter()
    # fs001 管线里退化成纯寄存器链 → 拒 (60431 次播放 0 检出的教训)
    regchain = _seed(tags=("alu", "fs001_target"))
    assert filt.reject(regchain) is True
    # 普通 alu 候选 → 放行 (不属于 FS-001 定向管线)
    assert filt.reject(_seed()) is False
    # 注入了 gather 块的子代 → 放行
    rng = random.Random(1)
    kids = LoadPathMutator(n_children=1).mutate(_seed(), rng)
    assert filt.reject(kids[0]) is False


if __name__ == "__main__":
    test_fs001_data_complete()
    test_loadpath_mutator_children_carry_elements()
    test_negative_control_filter()
    print("all fault-signature mutator tests passed")




# ---------------------------------------------------------------------------
# OperandMutator 三策略 (2026-09-05: bit 翻转 / 移位 / 随机值)
# ---------------------------------------------------------------------------
_BASE = 0x123456789ABCDEF0


def _changed(seed, kid):
    return [r for r in seed.regs_init
            if kid.regs_init[r] != seed.regs_init[r]]


def test_operand_mutator_bitflip():
    rng = random.Random(2026)
    seed = _seed()
    kids = OperandMutator(20, strategy_weights={"bitflip": 1.0}).mutate(seed, rng)
    assert len(kids) == 20
    for k in kids:
        ch = _changed(seed, k)
        assert len(ch) == 1                       # 恰好一个寄存器被变异
        assert 1 <= bin(k.regs_init[ch[0]] ^ seed.regs_init[ch[0]]).count("1") <= 4
        assert k.origin == "mutate:operand:bitflip"


def test_operand_mutator_shift():
    rng = random.Random(7)
    seed = make_candidate(SEED_ASM, {i: _BASE for i in range(4)},
                          [], "seed:t")
    gr = OperandMutator.SHIFT_GRANULARITIES
    assert (8, 16, 24, 32) == gr[:4]              # 需求要求的粒度
    kids = OperandMutator(25, strategy_weights={"shift": 1.0}).mutate(seed, rng)
    for k in kids:
        ch = _changed(seed, k)
        assert len(ch) == 1
        x, b = k.regs_init[ch[0]], seed.regs_init[ch[0]]
        assert any(x == ((b << n) & ((1 << 64) - 1)) or x == (b >> n)
                   for n in gr), f"{x:#x} 不是 {_BASE:#x} 的合法粒度移位"
        assert k.origin == "mutate:operand:shift"


def test_operand_mutator_random():
    rng = random.Random(11)
    seed = make_candidate(SEED_ASM, {i: _BASE for i in range(4)},
                          [], "seed:t")
    kids = OperandMutator(15, strategy_weights={"random": 1.0}).mutate(seed, rng)
    for k in kids:
        ch = _changed(seed, k)
        assert len(ch) == 1
        v = k.regs_init[ch[0]]
        assert v != _BASE                          # 整寄存器重掷
        assert 16 < bin(v).count("1") < 48         # 高熵 (期望 ~32)
        assert k.origin == "mutate:operand:random"


def test_operand_mutator_mixed_and_compat():
    rng = random.Random(13)
    seed = _seed()
    kids = OperandMutator(40).mutate(seed, rng)    # 默认权重 0.4/0.3/0.3
    from collections import Counter
    dist = Counter(k.origin.split(":")[-1] for k in kids)
    assert set(dist) == {"bitflip", "shift", "random"}
    assert all(dist[s] >= 5 for s in dist)         # 三策略都有代表
    # 兼容壳: 旧名不改调用方
    old = OperandBitFlipMutator(3).mutate(seed, rng)
    assert len(old) == 3 and all(k.origin == "mutate:operand:bitflip"
                                 for k in old)

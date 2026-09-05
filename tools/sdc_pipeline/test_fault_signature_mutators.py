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
from tools.sdc_pipeline.mutators import LoadPathMutator, NegativeControlFilter

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

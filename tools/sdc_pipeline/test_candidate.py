#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_candidate.py — Candidate 统一抽象单元测试。

验证 R1 解法: .S 文本与 bytes 双形态打通, 身份=内容 hash 稳定。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import Candidate, make_candidate, compile_asm

# 最小可汇编模板 (与 seeds/*.S 同构: .include 公共宏 + _start)
MINIMAL_ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mov     x1, #1
    adds    x0, x1, x1
"""

SEEDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "seeds")


def test_compile_asm_produces_aarch64():
    code = compile_asm(MINIMAL_ASM)
    assert isinstance(code, bytes)
    assert len(code) >= 4
    assert len(code) % 4 == 0, "AArch64 指令必须 4 字节对齐"


def test_compile_asm_deterministic():
    assert compile_asm(MINIMAL_ASM) == compile_asm(MINIMAL_ASM)


def test_candidate_identity_stable():
    regs = {0: 1, 1: 2, 2: 3}
    c1 = make_candidate(MINIMAL_ASM, regs, [], "seed:test")
    c2 = make_candidate(MINIMAL_ASM, regs, [], "seed:test")
    assert c1.ident == c2.ident, "同输入必须同 ident (内容 hash)"


def test_candidate_identity_differs_on_change():
    regs = {0: 1, 1: 2, 2: 3}
    c1 = make_candidate(MINIMAL_ASM, regs, [], "seed:test")
    c2 = make_candidate(MINIMAL_ASM, {0: 9, 1: 2, 2: 3}, [], "seed:test")
    assert c1.ident != c2.ident, "操作数不同必须不同 ident"


def test_candidate_fields():
    regs = {0: 1, 1: 2}
    c = make_candidate(MINIMAL_ASM, regs, ["parent123"], "mutate:test_op",
                       structure_tags=["alu", "carry_chain"])
    assert isinstance(c, Candidate)
    assert c.parents == ["parent123"]
    assert c.origin == "mutate:test_op"
    assert c.structure_tags == ["alu", "carry_chain"]
    assert len(c.code_bytes) % 4 == 0
    assert all(0 <= r <= 30 for r in c.regs_init), "寄存器号必须在 X0-X30"


def test_candidate_regs_init_keys_bounded():
    try:
        make_candidate(MINIMAL_ASM, {31: 1}, [], "seed:bad")
        assert False, "X31(ZR)/越界寄存器必须被拒"
    except ValueError:
        pass

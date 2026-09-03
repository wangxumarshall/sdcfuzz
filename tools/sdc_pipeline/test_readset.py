#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_readset.py — 读集分析单元测试 (反逻辑屏蔽防线)。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.readset import readset, live_readset, writeset

# M2 的活教材: x5 被 adds x5,x4,x3 写前不读覆写
ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    adds    x0, x1, x2
    eor     x3, x0, x1
    and     x4, x3, x2
    adds    x5, x4, x3
    eor     x6, x5, x0
"""


def _cand(regs):
    return make_candidate(ASM, regs, [], "test")


def test_readset_finds_consumed_regs():
    c = _cand({i: i for i in range(7)})
    rs = readset(c.code_bytes)
    # 消费: x1,x2 (首条), x0,x1 (eor), x3,x2 (and), x4,x3 (adds), x5,x0 (eor)
    assert rs == {0, 1, 2, 3, 4, 5}, f"读集错误: {rs}"


def test_writeset():
    c = _cand({i: i for i in range(7)})
    ws = writeset(c.code_bytes)
    assert ws == {0, 3, 4, 5, 6}, f"写集错误: {ws}"


def test_live_readset_intersects_regs_init():
    # 只初始化了 x1,x2,x5 → 可变异域 = {1,2,5}
    c = _cand({1: 1, 2: 2, 5: 5})
    assert live_readset(c) == {1, 2, 5}


def test_live_readset_excludes_write_only():
    # x6 只写不读 → 不在 live; x7 不在指令里 → 不在 live
    c = _cand({1: 1, 2: 2, 6: 6, 7: 7})
    ls = live_readset(c)
    assert 6 not in ls, "写前不读的寄存器 (M2 逻辑掩蔽案例) 必须排除"
    assert 7 not in ls, "未参与指令的寄存器必须排除"
    assert ls == {1, 2}


def test_first_read_live_ordered():
    """定序分析: x4 先被 and 覆写再被读 → 初值无效; x1,x2 首引用即读 → 有效。"""
    from tools.sdc_pipeline.readset import first_read_live, live_first_read
    c = _cand({i: i for i in range(7)})
    fl = first_read_live(c.code_bytes)
    # x4: and x4,x3,x2 先写 → 初值死。x0: 首条 adds x0,x1,x2 是写 → 初值死
    # (x0 初值无效, 但后续 eor x3,x0,x1 读的是 adds 的结果)。
    # 有效: x1, x2 (首条就被读)
    assert fl == {1, 2}, f"定序有效域错误: {fl}"
    # ∩ regs_init
    c2 = _cand({1: 1, 2: 2, 4: 4})
    assert live_first_read(c2) == {1, 2}

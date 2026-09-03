#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""readset.py — 指令序列读集分析 (反逻辑屏蔽的第一道防线)。

M2 实证的浪费: operand_dict 变异了 x5, 但 x5 被 "adds x5,x4,x3" 写前不读
覆写 → 变异无效 (输出不变)。E7 后续加强的必要组件: 变异目标必须落在
指令序列**实际消费 (写前读)** 的寄存器上。

用法: readset(code_bytes) -> set[int]  # 消费的寄存器号 (x0-x30)
      live_readset(cand) -> set[int]   # 候选读集 ∩ regs_init 键 (可变异域)
"""
import capstone

_cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
_cs.detail = True


def readset(code_bytes: bytes) -> set:
    """全序列读集: 任一指令读过的寄存器号集合 (不含 nzcv 等非通用寄存器)。"""
    reads = set()
    for insn in _cs.disasm(code_bytes, 0x10000):
        r, _w = insn.regs_access()
        for reg in r:
            name = insn.reg_name(reg)
            if name.startswith("x") and name[1:].isdigit():
                reads.add(int(name[1:]))
    return reads


def live_readset(cand) -> set:
    """可变异域: 读集 ∩ 初值寄存器 (变异这些寄存器才可能改变行为)。"""
    return readset(cand.code_bytes) & set(cand.regs_init.keys())


def writeset(code_bytes: bytes) -> set:
    """全序列写集 (诊断用)。"""
    writes = set()
    for insn in _cs.disasm(code_bytes, 0x10000):
        _r, w = insn.regs_access()
        for reg in w:
            name = insn.reg_name(reg)
            if name.startswith("x") and name[1:].isdigit():
                writes.add(int(name[1:]))
    return writes


def first_read_live(code_bytes: bytes) -> set:
    """**定序**初值有效域: 首引用是"读"的寄存器集合。

    静态 readset 的不足 (读集感知验证发现: 2/6 而非 6/6 生效):
    x4 出现在 adds x5,x4,x3 的读集里, 但它先被 and x4,x3,x2 **覆写** —
    初值从未被消费。只有"第一次被引用时是读"的寄存器, 其初值变异才能
    改变程序行为。这是真正的反逻辑掩蔽域。
    """
    live = set()
    seen = set()  # 已被写过的寄存器 (初值已死)
    for insn in _cs.disasm(code_bytes, 0x10000):
        r, w = insn.regs_access()
        reads_now = set()
        writes_now = set()
        for reg in r:
            name = insn.reg_name(reg)
            if name.startswith("x") and name[1:].isdigit():
                reads_now.add(int(name[1:]))
        for reg in w:
            name = insn.reg_name(reg)
            if name.startswith("x") and name[1:].isdigit():
                writes_now.add(int(name[1:]))
        # 本条指令内先读后写 (如 add x3, x3, x0): 读有效
        for x in reads_now:
            if x not in seen:
                live.add(x)
        # 写入 → 初值死亡 (对本条及后续)
        seen |= writes_now
    return live


def live_first_read(cand) -> set:
    """候选的定序有效初值域 ∩ regs_init。"""
    return first_read_live(cand.code_bytes) & set(cand.regs_init.keys())

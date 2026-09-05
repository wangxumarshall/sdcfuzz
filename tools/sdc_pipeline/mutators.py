#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""mutators.py — 变异器池 (sdc_pipeline Gen 层)。

统一 Mutator 接口 (mutate(Candidate, rng) -> list[Candidate]), 打通两套
体系 (R1):
  - OperandBitFlipMutator: regs_init 位翻 (evolution_engine 爬山算子泛化)
  - OperandDictMutator: operand_mutator 的 INT_DICT/FSU_DICT 字典值直接
    作操作数级替换 (不再走 .S 文本变体路线)
  - InsnSequenceMutator: 指令级变异 (插入/替换合法指令)
  - PowerStressMutator: scheme §5.3 功耗应力 Type-I (持续高翻转前置块) /
    Type-II (高低翻转交替) 雏形

所有子代: parents 含父 ident, origin=mutate:<op>, 可汇编 (compile_asm 保证)。
"""
import random

from tools.sdc_pipeline.candidate import make_candidate

# 操作数字典 (与 operand_mutator.INT_DICT 同源, 值级; FSU 字典值是
# double 位模式的 int 表示)
DICT_VALUES = {
    "int": [0xFFFFFFFFFFFFFFFF, 0x5555555555555555, 0xAAAAAAAAAAAAAAAA,
            0x00000000FFFFFFFF, 0x0000FFFFFFFFFFFF, 0x00FF00FF00FF00FF,
            0x0000FFFF0000FFFF, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000,
            0x0000000000000001],
    "fsu": [0x3FF0000000000000,   # 1.0
            0x0000000000000001,   # 最小 subnormal
            0x7FF8000000000000,   # QNaN
            0x7FF0000000000000,   # +Inf
            0x8000000000000000,   # -0.0
            0x7FEFFFFFFFFFFFFF],  # 最大有限值
}

# 指令序列变异的合法指令池 (纯寄存器运算, 无内存/分支 → 汇编必合法)
INSN_POOL = [
    "    add     x9, x9, x9",
    "    eor     x9, x9, x9",
    "    and     x9, x9, x9",
    "    orr     x9, x9, x9",
    "    lsl     x9, x9, #1",
    "    mul     x9, x9, x9",
    "    sub     x9, x9, x9",
]


class MutatorBase:
    """统一接口骨架。"""
    name = "base"

    def mutate(self, cand, rng: random.Random) -> list:
        raise NotImplementedError

    def _child(self, cand, asm: str, regs: dict, tag: str) -> object:
        return make_candidate(asm, regs, [cand.ident],
                              f"mutate:{self.name}{tag}",
                              structure_tags=cand.structure_tags)


class OperandBitFlipMutator(MutatorBase):
    """操作数位翻: 随机选寄存器翻 1-4 bit (toggle_hill_climb 的候选生成泛化)。

    readset_aware=True 时只变异 live_readset 内的寄存器 (M2 实证的
    逻辑掩蔽防线: 变异被"写前不读"覆写的寄存器是纯浪费)。
    """
    name = "operand_bitflip"

    def __init__(self, n_children=4, max_bits=4, readset_aware=True):
        self.n_children = n_children
        self.max_bits = max_bits
        self.readset_aware = readset_aware

    def _pick_reg(self, cand, rng):
        if self.readset_aware:
            from tools.sdc_pipeline.readset import live_first_read
            live = sorted(live_first_read(cand))
            if live:
                return rng.choice(live)
        return rng.choice(sorted(cand.regs_init))

    def mutate(self, cand, rng):
        kids = []
        for _ in range(self.n_children):
            if not cand.regs_init:
                break
            regs = dict(cand.regs_init)
            reg = self._pick_reg(cand, rng)
            for _ in range(rng.randint(1, self.max_bits)):
                regs[reg] ^= 1 << rng.randrange(64)
            kids.append(self._child(cand, cand.source_asm, regs, ""))
        return kids


class OperandDictMutator(MutatorBase):
    """操作数字典替换: 用 DICT_VALUES 的极端值族替换操作数 (体系打通)。

    readset_aware=True 时只替换 live_readset 内的寄存器 (同上, 反掩蔽)。
    """
    name = "operand_dict"

    def __init__(self, n_children=4, readset_aware=True):
        self.n_children = n_children
        self.readset_aware = readset_aware

    def mutate(self, cand, rng):
        if not cand.regs_init:
            return []
        all_vals = DICT_VALUES["int"] + DICT_VALUES["fsu"]
        kids = []
        for _ in range(self.n_children):
            regs = dict(cand.regs_init)
            if self.readset_aware:
                from tools.sdc_pipeline.readset import live_first_read
                live = sorted(live_first_read(cand))
                reg = rng.choice(live) if live else rng.choice(sorted(regs))
            else:
                reg = rng.choice(sorted(regs))
            regs[reg] = rng.choice(all_vals)
            kids.append(self._child(cand, cand.source_asm, regs, ""))
        return kids


class InsnSequenceMutator(MutatorBase):
    """指令级变异: 在 _start 后随机插入或替换一条池内指令。"""
    name = "insn_seq"

    def __init__(self, n_children=3):
        self.n_children = n_children

    def mutate(self, cand, rng):
        lines = cand.source_asm.splitlines()
        # 找 _start: 后第一个非空行位置 (插入点)
        try:
            start_idx = next(i for i, l in enumerate(lines) if l.strip() == "_start:")
        except StopIteration:
            return []
        body_start = start_idx + 1
        while body_start < len(lines) and \
                (not lines[body_start].strip() or lines[body_start].strip().startswith("//")):
            body_start += 1
        kids = []
        for _ in range(self.n_children):
            new_lines = lines[:]
            insn = rng.choice(INSN_POOL)
            if rng.random() < 0.5 and body_start < len(new_lines):
                new_lines[body_start] = insn + "    // insn_seq 替换"
            else:
                new_lines.insert(body_start, insn + "    // insn_seq 插入")
            kids.append(self._child(cand, "\n".join(new_lines) + "\n",
                                    cand.regs_init, ""))
        return kids


class PowerStressMutator(MutatorBase):
    """功耗应力插入 (scheme §5.3 雏形):
    Type-I  持续高功耗: 头部插入高翻转块 (add/eor 交替, 复用
            encode_high_power_alu 思路, 用 x9 不碰初值寄存器)
    Type-II 功耗跳变: 高翻转块与低活动 nop 块交替 (di/dt 振荡)
    子代 structure_tags 附加 power_typeN (功耗-SDC 关联实验的分组标签)。
    """
    name = "power_stress"

    def __init__(self, stress_type=1, n_children=2, block_len=8):
        assert stress_type in (1, 2)
        self.stress_type = stress_type
        self.n_children = n_children
        self.block_len = block_len

    def _high_block(self) -> str:
        return "\n".join(
            f"    {'add' if i % 2 == 0 else 'eor'}     x9, x9, x9"
            for i in range(self.block_len))

    def mutate(self, cand, rng):
        tag = f":type{self.stress_type}"
        kids = []
        for i in range(self.n_children):
            lines = cand.source_asm.splitlines()
            try:
                start_idx = next(j for j, l in enumerate(lines)
                                 if l.strip() == "_start:")
            except StopIteration:
                return []
            if self.stress_type == 1:
                # 每个子代块长不同 (变异多样性, 防止 ident 碰撞)
                block_len = self.block_len + i
                hi = "\n".join(
                    f"    {'add' if j % 2 == 0 else 'eor'}     x9, x9, x9"
                    for j in range(block_len))
                block = hi + "    // Type-I 持续高功耗前置"
                insert = [block]
            else:
                hi = self._high_block()
                lo = "\n".join("    nop" for _ in range(self.block_len // 2 + i))
                block = (hi + "\n" + lo + "\n" + hi +
                         "\n    // Type-II 高低翻转交替")
                insert = [block]
            new_lines = lines[:start_idx + 1] + insert + lines[start_idx + 1:]
            asm = "\n".join(new_lines) + "\n"
            child = self._child(cand, asm, cand.regs_init, tag)
            child.structure_tags = list(cand.structure_tags) + [f"power_type{self.stress_type}"]
            kids.append(child)
        return kids


# ===========================================================================
# 故障签名先验变异器 (经验模式 FS-001 的可执行承载)
# 来源: tools/sdc_pipeline/fault_signatures.py + docs/fault_signature_playbook.md
# 确证案例: 0102 cpu179 load 返回通路缺陷 (2026-09-05 loadsink 4/11 轮检出)
# ===========================================================================

# FS-001 触发要素的指令积木 (与 loadsink_gen.py 同源, 结构参数化)
_GATHER_BLOCK = """    ldrsw   x12, [x6, x3, lsl #2]    // FS-001 要素① 间接寻址: 索引表
    ldr     d0, [x7, x12, lsl #3]     //   两级追逐: 数据表 gather
    fmsub   d0, d5, d4, d0            // 要素② load→FMA
    str     d0, [x7, x12, lsl #3]     //   →store 同址往返 (陈旧行回放窗口)
    add     x3, x3, #1"""

_ROUNDTRIP_HEADER = """    mov     x3, #0                     // gather 游标清零
    fmov    d4, x9                     // 要素③ 长存活 FP 累加器"""

_FOOTER = """    fadd    d4, d4, d5                // 累加器跨循环存活"""


class LoadPathMutator(MutatorBase):
    """FS-001 定向变异器: 把候选改造成带触发五要素的 load 密集形态。

    经验来源 (fault_signatures.FS001.trigger_elements):
      ① 间接寻址链 (索引表→数据表两级 gather)
      ② load→FMA→store 同址往返
      ③ 长存活 FP 累加器
      ④ 偶发 fdiv (cdiv 相位)
      ⑤ 满载执行环境 (由部署侧负责, 非指令层)

    行为: 在候选 _start 后注入参数化的 gather 链块。chain_len/roundtrips/
    div_prob 从 FS-001 要素参数空间采样; chain×round 乘积钳在页预算内。
    子代 structure_tags 附加 "fs001_loadpath" (评估/统计分组用)。
    """
    name = "fs001_loadpath"

    def __init__(self, n_children=2, max_chain_product=110, fs_id="FS-001"):
        from tools.sdc_pipeline import fault_signatures
        self.fs = fault_signatures.get(fs_id)
        te = self.fs["trigger_elements"]
        self.fma_op = te["fma_ops"][0]          # fmsub
        self.div_prob = te["cond_branch_fp_div"]
        self.min_loads = te["min_loads_per_round"]
        self.n_children = n_children
        self.max_chain_product = max_chain_product

    def _emit_block(self, rng):
        chain_len = rng.choice([8, 12, 16, 20])
        max_r = max(2, self.max_chain_product // chain_len)
        rounds = rng.randint(max(2, max_r // 2), max_r)
        div_on = rng.random() < self.div_prob
        lines = [_ROUNDTRIP_HEADER]
        for _ in range(rounds):
            lines.append(f"    .rept {chain_len}")
            lines.append(_GATHER_BLOCK)
            lines.append("    .endr")
            lines.append(_FOOTER)
            if div_on and rng.random() < 0.5:
                lines.append("    fdiv d6, d4, d5    // 要素④ cdiv 相位")
        return "\n".join(lines)

    def mutate(self, cand, rng):
        lines = cand.source_asm.splitlines()
        try:
            start_idx = next(i for i, l in enumerate(lines)
                             if l.strip() == "_start:")
        except StopIteration:
            return []
        kids = []
        for _ in range(self.n_children):
            block = self._emit_block(rng)
            new_lines = (lines[:start_idx + 1] +
                         [block + "    // fs001_loadpath 注入"] +
                         lines[start_idx + 1:])
            asm = "\n".join(new_lines) + "\n"
            child = self._child(cand, asm, cand.regs_init, "")
            child.structure_tags = list(set(cand.structure_tags +
                                            ["fs001_loadpath"]))
            kids.append(child)
        return kids


class NegativeControlFilter:
    """FS 负对照过滤: 拦截命中"已证伪形态"的候选, 省变异预算。

    经验来源 (fault_signatures.FS001.negative_controls): 11 个真机证伪
    形态 (纯 FMA/纯 gather/纯 NEON/密集 GEMM/...)。检测规则:
      - 候选 asm 无任何 load 指令 且 候选带 fs001 检出意图 → reg_only_chain
        (纯寄存器链对 load 通路缺陷 0 检出, sdcbench 60431 次播放的教训)
    后续模式追加时在此扩展判定。
    用法: filt = NegativeControlFilter(); filt.reject(cand) -> bool
    """
    def __init__(self, fs_ids=("FS-001",)):
        from tools.sdc_pipeline import fault_signatures
        self.tags = set()
        for fid in fs_ids:
            self.tags.update(fault_signatures.get(fid)["negative_controls"])

    def reject(self, cand) -> bool:
        asm = cand.source_asm
        has_load = any(op in asm for op in ("ldr", "ldp"))
        # 规则1: 若管线目标是 FS-001 (cand 带 fs001 标签或其父代带),
        #        纯寄存器链是已证伪形态
        if "fs001_loadpath" in getattr(cand, "structure_tags", []):
            pass  # 已注入 gather 块, 必有 load
        elif not has_load and any("fs001" in t for t in
                                  getattr(cand, "structure_tags", [])):
            return True   # fs001 定向管线里退化成纯寄存器链 → 拒
        return False

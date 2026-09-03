#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""evaluators.py — Unicorn 静态评估器池 (sdc_pipeline R2 解法)。

统一 Evaluator 接口 (evaluate(Candidate) -> {metric: value}), 把散落在
sdc_mutator 三个文件里的 ACE/翻转/雪崩测量通用化为四个可组合插件:
  - ACEProxyEvaluator: 执行中翻转寄存器 bit → 输出 diverge 比例
    (ace_workload_engine.run_with_midflip 语义, 即 gem5 注入的 Unicorn 代理)
  - IBREvaluator: 逐指令源操作数输入位翻转率 (Harpocrates IBR 的
    Unicorn 可计算近似: 输入位翻转 / 总输入位)
  - TogglePowerEvaluator: 每指令寄存器写翻转量/指令数, 归一到 0..1
    (di/dt 功耗代理 — McPAT 未接入前的诚实降级, 命名带 proxy)
  - AvalancheEvaluator: 1-bit 输入扰动 → 输出差异 (反逻辑屏蔽指标)

R1 关键通用化: 寄存器 X0-X30 全支持 (不再写死 X0-X4), 指令数上限可配。
"""
import random

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_PC, UC_ARM64_REG_SP

import unicorn.arm64_const as _a64c

# X0-X30 → unicorn 常量 (getattr 逐个取, X31=ZR 不含)
REG_MAP = {i: getattr(_a64c, f"UC_ARM64_REG_X{i}") for i in range(31)}
REG_BACK = {v: k for k, v in REG_MAP.items()}


class UnicornRunner:
    """通用 Unicorn 执行器: .S 文本 + 初始寄存器 → (终态, 执行指令数)。

    evolution_engine.EvolutionEngine 的通用化: X0-X30 全寄存器、
    指令数上限 max_insns 可配、计数用 hook (不依赖 PC 推进, 分支安全)。
    """

    def __init__(self, code_addr=0x10000, stack_addr=0x80000, max_insns=256):
        self.code_addr = code_addr
        self.stack_addr = stack_addr
        self.max_insns = max_insns

    def _make_uc(self, code_bytes: bytes, regs_init: dict):
        mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        mu.mem_map(self.code_addr, max(0x1000, (len(code_bytes) + 0xFFF) & ~0xFFF),
                   UC_PROT_ALL)
        mu.mem_map(self.stack_addr, 0x1000, UC_PROT_ALL)
        mu.mem_write(self.code_addr, code_bytes)
        for idx, val in regs_init.items():
            mu.reg_write(REG_MAP[idx], val & 0xFFFFFFFFFFFFFFFF)
        mu.reg_write(UC_ARM64_REG_SP, self.stack_addr + 0x800)
        mu.reg_write(UC_ARM64_REG_PC, self.code_addr)
        return mu

    def run(self, asm_text_or_bytes, regs_init: dict, midflip=None):
        """执行一次。midflip=(insn_index, reg, bit) 可选: 执行到第
        insn_index 条指令后翻转该寄存器 bit 再继续 (模拟 gem5 注入)。
        返回 ({reg_idx: 终态值}, 执行指令数)。"""
        # Candidate 的 code_bytes 优先; 也可直接传 .S (测试便利)
        code = asm_text_or_bytes if isinstance(asm_text_or_bytes, bytes) else None
        if code is None:
            from tools.sdc_pipeline.candidate import compile_asm
            code = compile_asm(asm_text_or_bytes)
        mu = self._make_uc(code, regs_init)
        count = [0]
        flip_done = [False]

        def _hook(uc, address, size, user_data):
            count[0] += 1
            if (midflip is not None and not flip_done[0]
                    and count[0] == midflip[0] + 1):
                insn_idx, reg, bit = midflip
                # 指令执行前翻转 → 该指令读到翻转后的值
                uc.reg_write(REG_MAP[reg],
                             uc.reg_read(REG_MAP[reg]) ^ (1 << bit))
                flip_done[0] = True

        h = mu.hook_add(UC_HOOK_CODE, _hook, begin=self.code_addr,
                        end=self.code_addr + len(code))
        try:
            mu.emu_start(self.code_addr, self.code_addr + len(code),
                         timeout=1_000_000, count=self.max_insns)
        except Exception:
            pass  # runaway / 非法指令: 用已执行的计数与终态 (既有语义)
        finally:
            mu.hook_del(h)
        final = {i: mu.reg_read(REG_MAP[i]) for i in range(31)}
        return final, count[0]


def _popcount(x: int) -> int:
    return bin(x).count("1")


class EvaluatorBase:
    """统一接口骨架: evaluate(Candidate) -> {metric_name: value}。"""
    name = "base"

    def evaluate(self, cand) -> dict:
        raise NotImplementedError


class ACEProxyEvaluator(EvaluatorBase):
    """ACE 比例代理: 随机 (指令位置, 寄存器, bit) 注入点翻转 → 输出 diverge 比例。

    ace_workload_engine.measure_workload_ace 的通用化 (X0-X30 全寄存器)。
    seed 固定则注入点序列可复现。
    """
    name = "ace_proxy"

    def __init__(self, runner=None, n_probes=20, seed=None):
        self.runner = runner or UnicornRunner()
        self.n_probes = n_probes
        self.rng = random.Random(seed)

    def evaluate(self, cand) -> dict:
        regs = cand.regs_init
        base_final, _ = self.runner.run(cand.code_bytes, regs)
        n_insn = len(cand.code_bytes) // 4
        if n_insn == 0:
            return {self.name: 0.0}
        diverge = 0
        observed_regs = sorted(regs.keys()) or [0]
        for _ in range(self.n_probes):
            insn = self.rng.randrange(n_insn)
            reg = self.rng.choice(observed_regs)
            bit = self.rng.randrange(64)
            cand_final, _ = self.runner.run(cand.code_bytes, regs,
                                            midflip=(insn, reg, bit))
            # 输出 diverge: 任一初值寄存器终态变化
            if any(base_final[r] != cand_final[r] for r in observed_regs):
                diverge += 1
        return {self.name: diverge / self.n_probes}


class IBREvaluator(EvaluatorBase):
    """IBR (Input Bit-toggling Rate): 逐指令源操作数输入位翻转率。

    Harpocrates IBR 的 Unicorn 近似: hook 每条指令执行, 对比其执行前
    各寄存器值与序列初值 (或上一快照) 的 XOR popcount。这里取可观测
    口径: 每条指令执行时全部 X0-X30 相对上一指令的位翻转总数 / (64*31),
    序列平均 → "指令流输入翻转密度"。
    """
    name = "ibr"

    def __init__(self, runner=None):
        self.runner = runner or UnicornRunner()

    def evaluate(self, cand) -> dict:
        code = cand.code_bytes
        n_insn = len(code) // 4
        if n_insn == 0:
            return {self.name: 0.0}
        mu = self.runner._make_uc(code, cand.regs_init)
        prev = {i: mu.reg_read(REG_MAP[i]) for i in range(31)}
        toggles = []
        state = {"count": 0}

        def _hook(uc, address, size, user_data):
            cur = {i: uc.reg_read(REG_MAP[i]) for i in range(31)}
            toggles.append(sum(_popcount(prev[i] ^ cur[i]) for i in range(31)))
            for i in range(31):
                prev[i] = cur[i]
            state["count"] += 1

        h = mu.hook_add(UC_HOOK_CODE, _hook, begin=self.runner.code_addr,
                        end=self.runner.code_addr + len(code))
        try:
            mu.emu_start(self.runner.code_addr, self.runner.code_addr + len(code),
                         timeout=1_000_000, count=self.runner.max_insns)
        except Exception:
            pass
        finally:
            mu.hook_del(h)
        if not toggles:
            return {self.name: 0.0}
        max_bits = 64 * 31
        return {self.name: sum(toggles) / len(toggles) / max_bits}


class TogglePowerEvaluator(EvaluatorBase):
    """翻转功耗代理: 每指令寄存器写翻转量 / 指令数, 归一 0..1。

    di/dt 功耗的 Unicorn 代理 (与 evolution_engine 的 T 因子同源但归一)。
    McPAT 未接入前的诚实降级 — 指标名带 proxy。
    """
    name = "toggle_power_proxy"

    def __init__(self, runner=None):
        self.runner = runner or UnicornRunner()

    def evaluate(self, cand) -> dict:
        final, executed = self.runner.run(cand.code_bytes, cand.regs_init)
        if executed == 0:
            return {self.name: 0.0}
        init = {i: cand.regs_init.get(i, 0) for i in range(31)}
        total = sum(_popcount(init[i] ^ final[i]) for i in range(31))
        per_insn = total / executed
        return {self.name: min(1.0, per_insn / (64 * 31))}


class AvalancheEvaluator(EvaluatorBase):
    """雪崩/反逻辑屏蔽: 1-bit 输入扰动 → 输出差异位数 (归一 0..1)。

    evolution_engine.avalanche_test 语义: 扰动某初值寄存器 1 bit,
    对比终态输出差异 popcount / (64 * n_observed)。
    """
    name = "avalanche"

    def __init__(self, runner=None, n_perturb=5, seed=None):
        self.runner = runner or UnicornRunner()
        self.n_perturb = n_perturb
        self.rng = random.Random(seed)

    def evaluate(self, cand) -> dict:
        regs = cand.regs_init
        observed = sorted(regs.keys())
        if not observed:
            return {self.name: 0.0}
        base_final, _ = self.runner.run(cand.code_bytes, regs)
        total_diff = 0
        for _ in range(self.n_perturb):
            reg = self.rng.choice(observed)
            bit = self.rng.randrange(64)
            perturbed = dict(regs)
            perturbed[reg] ^= 1 << bit
            p_final, _ = self.runner.run(cand.code_bytes, perturbed)
            total_diff += sum(_popcount(base_final[r] ^ p_final[r]) for r in observed)
        return {self.name: total_diff / self.n_perturb / (64 * len(observed))}

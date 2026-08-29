#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ace_workload_engine.py — 工作负载级 ACE-比例定向进化 (击败B的正确路径)

根因洞察(subagent AVF定理 + 数据分析):
  序列级雪崩(操作数扰动)击败B(6.8>6.4), 但gem5注入级仍<B。
  因为gem5翻转的是"执行中物理寄存器bit"(中间状态), 不是"操作数bit"(输入)。
  正确目标=最大化"执行中翻转寄存器bit导致最终输出diverge"的比例 = ACE-比例。

本引擎: 用unicorn hook在执行中某条指令后翻转寄存器bit, 继续跑完, 测输出diverge。
直接模拟gem5注入, 最大化ACE-比例(不是T, 不是操作数雪崩)。
"""
import sys, os, random, math, copy
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import EvolutionEngine, popcount, hamming_entropy, encode_adds_x0_x1_x2
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL, UC_HOOK_CODE
from unicorn.arm64_const import *

REG_MAP = {0: UC_ARM64_REG_X0, 1: UC_ARM64_REG_X1, 2: UC_ARM64_REG_X2, 3: UC_ARM64_REG_X3, 4: UC_ARM64_REG_X4}

class ACEWorkloadEngine(EvolutionEngine):
    """工作负载级 ACE-比例测量 + 爬山"""

    def measure_workload_ace(self, regs, n_probes=20):
        """测工作负载级 ACE-比例: 在执行中翻转寄存器bit, 测最终输出diverge比例
        模拟gem5注入(随机寄存器+随机cycle), 直接测ACE-比例"""
        # 基线输出
        base_final, base_T, _, _, _ = self.run_once(regs)
        diverge_count = 0
        for _ in range(n_probes):
            # 随机选注入点: 指令位置(0-7) + 寄存器(0-4) + bit(0-63)
            inj_insn = random.randint(0, max(1, len(self.code_bytes)//4 - 1))
            inj_reg = random.choice(list(regs.keys()))
            inj_bit = random.randint(0, 63)
            # 跑到注入点, 翻转bit, 继续跑完
            cand_final = self.run_with_midflip(regs, inj_insn, inj_reg, inj_bit)
            # 输出是否 diverge
            if any(base_final[i] != cand_final[i] for i in range(5)):
                diverge_count += 1
        return diverge_count / n_probes if n_probes > 0 else 0

    def run_with_midflip(self, regs, flip_insn, flip_reg, flip_bit):
        """跑到 flip_insn 指令后, 翻转 flip_reg 的 flip_bit, 继续跑完, 返回终态"""
        mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        mu.mem_map(self.code_addr, 0x1000, UC_PROT_ALL)
        mu.mem_map(self.stack_addr, 0x1000, UC_PROT_ALL)
        mu.mem_write(self.code_addr, self.code_bytes)
        for idx, val in regs.items():
            if idx in REG_MAP:
                mu.reg_write(REG_MAP[idx], val & 0xFFFFFFFFFFFFFFFF)
        mu.reg_write(UC_ARM64_REG_SP, self.stack_addr + 0x800)
        mu.reg_write(UC_ARM64_REG_PC, self.code_addr)
        # hook 每条指令, 在 flip_insn 后翻转
        insn_count = [0]
        def hook_code(uc, address, size, user_data):
            insn_count[0] += 1
            if insn_count[0] == flip_insn + 1:  # 在 flip_insn 条指令执行后
                cur = uc.reg_read(REG_MAP[flip_reg])
                uc.reg_write(REG_MAP[flip_reg], cur ^ (1 << flip_bit))
        mu.hook_add(UC_HOOK_CODE, hook_code)
        try:
            mu.emu_start(self.code_addr, self.code_addr + len(self.code_bytes),
                         timeout=1000000, count=max(64, len(self.code_bytes)//4 * 2))
        except Exception:
            pass
        return {idx: mu.reg_read(REG_MAP[idx]) for idx in range(5)}

    def ace_workload_hill_climb(self, regs_init, iterations=25, n_probe=15):
        """方案: 工作负载级 ACE-比例爬山
        随机翻转操作数bit, 若 ACE-比例上升则接受 (直接最大化gem5会测的diverge率)"""
        best_regs = dict(regs_init)
        best_ace = self.measure_workload_ace(best_regs, n_probe)
        best_E = hamming_entropy(self.run_once(best_regs)[0][0])
        best_score = best_ace + 0.3 * best_E
        history = [(0, best_ace, best_score)]
        for it in range(iterations):
            reg_idx = random.choice(list(best_regs.keys()))
            candidate = dict(best_regs)
            for _ in range(random.randint(1, 3)):
                candidate[reg_idx] ^= (1 << random.randint(0, 63))
            cand_ace = self.measure_workload_ace(candidate, n_probe)
            cand_E = hamming_entropy(self.run_once(candidate)[0][0])
            cand_score = cand_ace + 0.3 * cand_E
            if cand_score > best_score:
                best_regs = candidate
                best_ace, best_E, best_score = cand_ace, cand_E, cand_score
                history.append((it+1, best_ace, best_score))
        return best_regs, best_ace, best_score, history

def main():
    # 8条混合指令序列
    seq = b''
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('230200ca')  # eor x3,x1,x2
    seq += bytes.fromhex('610c029b')  # mul x1,x2,x3
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2
    seq += bytes.fromhex('6300008b')  # add x3,x3,x3
    seq += bytes.fromhex('640200ca')  # eor x4,x1,x2
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2

    eng = ACEWorkloadEngine(seq)
    print("=== 工作负载级 ACE-比例定向进化 ===")
    print(f"序列: 8条混合指令 (add/eor/mul/adds)")

    # 初始普通操作数
    regs = {0: 0x111, 1: 0x222, 2: 0x333, 3: 0x444, 4: 0x555}
    init_ace = eng.measure_workload_ace(regs, 20)
    print(f"初始 ACE-比例: {init_ace:.3f} (执行中翻转20bit, diverge比例)")

    # B(随机)对照
    b_regs = {i: random.getrandbits(64) for i in range(5)}
    b_ace = eng.measure_workload_ace(b_regs, 20)
    print(f"B(随机) ACE-比例: {b_ace:.3f}")

    # 爬山最大化 ACE-比例
    print(f"\n=== ACE-比例爬山 (25轮) ===")
    best, best_ace, best_score, hist = eng.ace_workload_hill_climb(regs, 25, 15)
    print(f"  ACE-比例: {init_ace:.3f} → {best_ace:.3f}")
    print(f"  接受变异: {len(hist)-1}次")
    print(f"  vs B(随机){b_ace:.3f}: {'击败' if best_ace > b_ace else '未击败'} B")

    # 对比: T目标 vs ACE目标
    print(f"\n=== 对比 ===")
    t_best, t_T, _, _ = eng.toggle_hill_climb(regs, 25)
    t_ace = eng.measure_workload_ace(t_best, 15)
    print(f"  T目标演化: T={t_T}, ACE-比例={t_ace:.3f}")
    print(f"  ACE目标演化: ACE-比例={best_ace:.3f}")
    print(f"  → ACE目标{'>' if best_ace > t_ace else '<'} T目标的ACE-比例")

if __name__ == "__main__":
    main()

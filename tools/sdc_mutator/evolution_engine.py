#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""evolution_engine.py — 基于 Unicorn 反馈的 SDC 自适应进化引擎

设计概念 (用户指定):
  Score = W1*T(di/dt) + W2*M(Path) + W3*E(AntiMasking)
  - T(di/dt): 寄存器 bit 翻转量 (popcount of reg_toggle)
  - M(Path): 微架构深度 (指令数/cycle 代理, 慢路径)
  - E(AntiMasking): 结果高熵 + 雪崩效应 (反掩蔽)

三个变异算子:
  1. Toggle-Driven 梯度爬山: 随机翻转操作数 bit, 若 T 上升则接受 (梯度上升)
  2. 边界差异放大: 操作数 ±1/位移, 若微架构状态差异大 (新 op_reg_toggle feature) 则保留
  3. 上下文重组: 插入高功耗指令序列前后 (Voltage Droop 制造)

工作流: Seed → Evaluate → Fuzzing Loop (Mutate/Simulate/Score/Select/AntiMasking)
       → Emit SDC Testcase → 上硅

本原型实现: 适应度函数 + 算子一(toggle梯度爬山) + 基础进化循环。
从普通指令(ADD等)开始, 自动演化出高翻转量操作数。
"""
import sys, struct, random, math
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_NZCV)
import capstone

# 适应度函数权重 (用户公式 Score = W1*T + W2*M + W3*E)
W1, W2, W3 = 1.0, 0.5, 0.8

# AArch64 寄存器映射 (X0-X4)
REG_MAP = {0: UC_ARM64_REG_X0, 1: UC_ARM64_REG_X1, 2: UC_ARM64_REG_X2, 3: UC_ARM64_REG_X3, 4: UC_ARM64_REG_X4}

def popcount(x):
    return bin(x).count('1')

def hamming_entropy(val, bits=64):
    """位间香农熵: 高熵=无结构(反掩蔽), 低熵=结构化(易掩蔽)"""
    ones = popcount(val & ((1<<bits)-1))
    p = ones / bits
    if p == 0 or p == 1:
        return 0.0
    return -p*math.log2(p) - (1-p)*math.log2(1-p)

class EvolutionEngine:
    def __init__(self, code_bytes, code_addr=0x10000, stack_addr=0x80000):
        self.code_bytes = code_bytes
        self.code_addr = code_addr
        self.stack_addr = stack_addr
        self.cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

    def run_once(self, regs_init):
        """跑一次 Unicorn, 返回 (终态寄存器, 翻转量T, 指令数M, 结果熵E)"""
        mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        mu.mem_map(self.code_addr, 0x1000, UC_PROT_ALL)
        mu.mem_map(self.stack_addr, 0x1000, UC_PROT_ALL)
        mu.mem_write(self.code_addr, self.code_bytes)
        # 设初始寄存器
        for idx, val in regs_init.items():
            if idx in REG_MAP:
                mu.reg_write(REG_MAP[idx], val & 0xFFFFFFFFFFFFFFFF)
        mu.reg_write(UC_ARM64_REG_SP, self.stack_addr + 0x800)
        mu.reg_write(UC_ARM64_REG_PC, self.code_addr)
        # 记录初始寄存器 (X0-X4)
        init_vals = {idx: mu.reg_read(REG_MAP[idx]) for idx in range(5)}
        # 跑 (最多 N 条指令, 防 runaway)
        insn_count = 0
        try:
            mu.emu_start(self.code_addr, self.code_addr + len(self.code_bytes), timeout=1000000, count=64)
        except Exception:
            pass
        # 终态寄存器
        final_vals = {idx: mu.reg_read(REG_MAP[idx]) for idx in range(5)}
        # T(di/dt): 总翻转量 = sum over regs of popcount(init XOR final)
        T = sum(popcount(init_vals[i] ^ final_vals[i]) for i in range(5))
        # M(Path): 执行的指令数 (cycle 代理, 这里用 PC 推进距离/4)
        M = (mu.reg_read(UC_ARM64_REG_PC) - self.code_addr) // 4
        # E(AntiMasking): 终态结果的香农熵 (越高越好, 全0/全1→0)
        # 用所有终态寄存器的合并熵
        all_bits = 0
        for i in range(5):
            all_bits ^= final_vals[i]
        E = hamming_entropy(all_bits, 64)
        # Score
        score = W1*T + W2*M + W3*E
        return final_vals, T, M, E, score

    def avalanche_test(self, regs_init, perturb_reg, perturb_bit):
        """雪崩测试: 操作数改变1bit, 对比两次输出结果差异 bit 数"""
        r1, _, _, _, _ = self.run_once(regs_init)
        regs2 = dict(regs_init)
        regs2[perturb_reg] = regs_init[perturb_reg] ^ (1 << perturb_bit)
        r2, _, _, _, _ = self.run_once(regs2)
        # 输出结果差异 bit 数
        diff = sum(popcount(r1[i] ^ r2[i]) for i in range(5))
        return diff

    def toggle_hill_climb(self, regs_init, iterations=30):
        """变异算子一: Toggle-Driven 梯度爬山
        随机翻转操作数 bit, 若 T(翻转量)上升则接受 (梯度上升)
        自动逼近该指令序列的物理翻转极限"""
        best_regs = dict(regs_init)
        _, best_T, _, _, best_score = self.run_once(best_regs)
        history = [(0, best_T, best_score)]
        for it in range(iterations):
            # 随机选一个寄存器和若干 bit 翻转
            reg_idx = random.choice(list(best_regs.keys()))
            n_bits = random.randint(1, 4)
            candidate = dict(best_regs)
            for _ in range(n_bits):
                bit = random.randint(0, 63)
                candidate[reg_idx] ^= (1 << bit)
            # 跑
            _, cand_T, cand_M, cand_E, cand_score = self.run_once(candidate)
            # 梯度上升: T 上升则接受
            if cand_T > best_T or (cand_T == best_T and cand_score > best_score):
                best_regs = candidate
                best_T, best_score = cand_T, cand_score
                history.append((it+1, best_T, best_score))
        return best_regs, best_T, best_score, history

def encode_add_x0_x1_x2():
    """ADD X0, X1, X2 (普通指令, 起始seed)"""
    return bytes.fromhex('200b008b')  # add x0, x1, x2

def encode_adds_x0_x1_x2():
    """ADDS X0, X1, X2 (设置flags)"""
    return bytes.fromhex('200b00ab')  # adds x0, x1, x2

def main():
    # 起始: 普通指令 ADDS X0,X1,X2, 初始操作数是普通值 (非魔术数字)
    code = encode_adds_x0_x1_x2()
    print(f"=== 进化引擎: 起始指令 ADDS X0,X1,X2 ({len(code)} bytes) ===")
    eng = EvolutionEngine(code)

    # 初始操作数: 普通业务数据 (纯天然, 非全0/全1)
    regs_init = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    r, T, M, E, S = eng.run_once(regs_init)
    print(f"初始: regs={ {k:hex(v) for k,v in regs_init.items()} }")
    print(f"  T(翻转)={T} M(指令)={M} E(熵)={E:.3f} Score={S:.2f}")

    # 算子一: Toggle 梯度爬山 (30轮)
    print(f"\n=== 算子一: Toggle梯度爬山 (30轮) ===")
    best_regs, best_T, best_score, hist = eng.toggle_hill_climb(regs_init, 30)
    print(f"演化后: regs={ {k:hex(v) for k,v in best_regs.items()} }")
    print(f"  T={best_T} Score={best_score:.2f} (初始 T={T})")
    print(f"  接受变异次数: {len(hist)-1}")
    r2, T2, M2, E2, S2 = eng.run_once(best_regs)
    print(f"  终态: X0={hex(r2[0])} E(熵)={E2:.3f}")

    # 雪崩测试 (反掩蔽)
    print(f"\n=== 雪崩测试 (反掩蔽, 1bit扰动) ===")
    for reg in [0, 1, 2]:
        for bit in [0, 31, 63]:
            diff = eng.avalanche_test(best_regs, reg, bit)
            print(f"  扰动 X{reg} bit{bit}: 输出差异={diff} bits {'(高雪崩/反掩蔽)' if diff > 10 else '(低雪崩/易掩蔽)'}")

if __name__ == "__main__":
    main()

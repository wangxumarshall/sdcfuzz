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

    def boundary_amplify(self, regs_init, iterations=20):
        """变异算子二: 边界差异放大
        操作数 ±1/位移, 检测突变点 (微小输入变化导致大微架构状态差异)
        触碰进位链断裂/符号扩展边界。突变点操作数加入精英池"""
        best_regs = dict(regs_init)
        _, best_T, _, _, best_score = self.run_once(best_regs)
        elite_pool = []  # 突变点操作数
        for it in range(iterations):
            reg_idx = random.choice(list(best_regs.keys()))
            candidate = dict(best_regs)
            op = random.choice(['add1', 'sub1', 'shl1', 'shr1', 'not'])
            if op == 'add1': candidate[reg_idx] = (candidate[reg_idx] + 1) & 0xFFFFFFFFFFFFFFFF
            elif op == 'sub1': candidate[reg_idx] = (candidate[reg_idx] - 1) & 0xFFFFFFFFFFFFFFFF
            elif op == 'shl1': candidate[reg_idx] = (candidate[reg_idx] << 1) & 0xFFFFFFFFFFFFFFFF
            elif op == 'shr1': candidate[reg_idx] = candidate[reg_idx] >> 1
            elif op == 'not': candidate[reg_idx] = ~candidate[reg_idx] & 0xFFFFFFFFFFFFFFFF
            # 跑
            r1, T1, M1, E1, S1 = self.run_once(best_regs)
            r2, T2, M2, E2, S2 = self.run_once(candidate)
            # 突变点检测: 微小输入变化 → 大状态差异 (T 差异大 或 结果差异大)
            state_diff = sum(popcount(r1[i] ^ r2[i]) for i in range(5))
            if state_diff > 10 or T2 > best_T + 4:
                # 触碰突变点 (进位链/符号边界), 加入精英池
                elite_pool.append((dict(candidate), T2, state_diff, op))
            if S2 > best_score:
                best_regs = candidate
                best_T, best_score = T2, S2
        return best_regs, best_T, best_score, elite_pool

    def context_crossover(self, regs_init, high_power_code, iterations=15):
        """变异算子三: 上下文污染与重组 (Crossover)
        插入高功耗指令序列前后 (Voltage Droop 制造), 再跑高di/dt指令"""
        # 高功耗序列 + 原指令 拼接
        combined = high_power_code + self.code_bytes
        eng2 = EvolutionEngine(combined, self.code_addr, self.stack_addr)
        best_regs = dict(regs_init)
        _, best_T, _, _, best_score = eng2.run_once(best_regs)
        for it in range(iterations):
            reg_idx = random.choice(list(best_regs.keys()))
            candidate = dict(best_regs)
            # 随机翻转若干bit (复用算子一策略, 但在高功耗上下文中)
            for _ in range(random.randint(1, 4)):
                candidate[reg_idx] ^= (1 << random.randint(0, 63))
            _, cand_T, _, _, cand_score = eng2.run_once(candidate)
            if cand_T > best_T:
                best_regs = candidate
                best_T, best_score = cand_T, cand_score
        return best_regs, best_T, best_score

def encode_add_x0_x1_x2():
    """ADD X0, X1, X2 (普通指令, 起始seed)"""
    return bytes.fromhex('200b008b')  # add x0, x1, x2

def encode_adds_x0_x1_x2():
    """ADDS X0, X1, X2 (设置flags)"""
    return bytes.fromhex('200b00ab')  # adds x0, x1, x2

def encode_high_power_alu():
    """纯 ALU 高功耗序列 (ADD/EOR 交替, 不影响 X0-X2 目标, 上下文重组用)
    多条 ALU 指令制造 di/dt 压力 (Voltage Droop), 紧接 ADDS 高翻转指令"""
    seq = b''
    # add x3,x3,x3 ; eor x4,x4,x4 (反复, 高翻转, 不碰 x0-x2)
    for _ in range(8):
        seq += bytes.fromhex('6300008b')  # add x3, x3, x3
        seq += bytes.fromhex('640000ca')  # eor x4, x4, x4
    return seq

def main():
    # 起始: 普通指令 ADDS X0,X1,X2, 初始操作数是普通值 (非魔术数字)
    code = encode_adds_x0_x1_x2()
    print(f"=== 进化引擎: 起始指令 ADDS X0,X1,X2 ({len(code)} bytes) ===")
    eng = EvolutionEngine(code)

    # 初始操作数: 普通业务数据 (纯天然, 非全0/全1)
    regs_init = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    r, T, M, E, S = eng.run_once(regs_init)
    print(f"初始: T(翻转)={T} M(指令)={M} E(熵)={E:.3f} Score={S:.2f}")

    # 算子一: Toggle 梯度爬山 (30轮)
    print(f"\n=== 算子一: Toggle梯度爬山 (30轮) ===")
    r1, T1, S1, hist = eng.toggle_hill_climb(regs_init, 30)
    print(f"  T={T}→{T1} Score={S:.2f}→{S1:.2f} 接受{len(hist)-1}次")

    # 算子二: 边界差异放大 (20轮, 找突变点)
    print(f"\n=== 算子二: 边界差异放大 (20轮, 找突变点) ===")
    r2, T2, S2, elite = eng.boundary_amplify(r1, 20)
    print(f"  T={T1}→{T2} Score={S1:.2f}→{S2:.2f} 精英池(突变点)={len(elite)}个")
    if elite:
        print(f"  示例突变点: T={elite[0][1]} 状态差异={elite[0][2]} 算子={elite[0][3]}")

    # 算子三: 上下文重组 (高功耗 FMLA 前置, 15轮)
    print(f"\n=== 算子三: 上下文重组 (FMLA前置+ADDS, 15轮) ===")
    high_power = encode_high_power_alu()
    r3, T3, S3 = eng.context_crossover(r2, high_power, 15)
    print(f"  T={T2}→{T3} Score={S2:.2f}→{S3:.2f} (高功耗上下文中)")

    # 雪崩测试 (反掩蔽)
    print(f"\n=== 雪崩测试 (反掩蔽, 1bit扰动) ===")
    for reg in [0, 1, 2]:
        diff = eng.avalanche_test(r3, reg, 31)
        print(f"  扰动 X{reg} bit31: 输出差异={diff} bits {'(高雪崩/反掩蔽)' if diff > 10 else '(低雪崩/易掩蔽)'}")

    # 最终: 三算子演化结果 vs 初始
    print(f"\n=== 进化结果 ===")
    print(f"初始 T={T} Score={S:.2f} → 演化后 T={T3} Score={S3:.2f}")
    print(f"翻转量提升: {T3/T if T else 0:.1f}x")
    print(f"演化操作数: { {k:hex(v) for k,v in r3.items()} }")

if __name__ == "__main__":
    main()

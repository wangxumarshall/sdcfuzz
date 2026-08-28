#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ace_fraction_engine.py — 方案1: ACE-比例定向进化 (击败B的正确目标)

subagent研究结论: 当前T目标'集中'翻转降低AVF。正确目标=ACE-比例
(live ACE bits / live bits)。diverge率=ACE比例(均匀注入下,AVF定理)。

本引擎: 对操作数变体, 测'翻转任意单个bit是否导致输出diverge'的比例
(工作负载级ACE-比例代理, 非per-cycle, 但比T目标更接近真AVF)。
爬山最大化ACE-比例(不是T), 直接最大化diverge率分子。

Score = ACE_fraction + W3 * E(AntiMasking)
ACE_fraction = (# flipped bits causing output diverge) / (# total bits flipped)
"""
import sys, os, random, math
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import EvolutionEngine, popcount, hamming_entropy, encode_adds_x0_x1_x2

class ACEFractionEngine(EvolutionEngine):
    """方案1: ACE-比例定向进化 (继承EvolutionEngine, 加ACE测量)"""

    def measure_ace_fraction(self, regs, n_probe_bits=20):
        """测 ACE-比例: 随机选 n_probe_bits 个 bit 翻转, 看多少导致输出 diverge
        ACE-比例 = diverge数 / 探测bit数"""
        base_final, base_T, _, _, _ = self.run_once(regs)
        diverge_count = 0
        probed = 0
        for _ in range(n_probe_bits):
            # 随机选一个寄存器和1个bit翻转
            reg_idx = random.choice(list(regs.keys()))
            bit = random.randint(0, 63)
            candidate = dict(regs)
            candidate[reg_idx] ^= (1 << bit)
            cand_final, _, _, _, _ = self.run_once(candidate)
            # 输出是否 diverge (任何终态寄存器不同)
            if any(base_final[i] != cand_final[i] for i in range(5)):
                diverge_count += 1
            probed += 1
        return diverge_count / probed if probed > 0 else 0

    def ace_hill_climb(self, regs_init, iterations=30, n_probe=15):
        """方案1爬山: 最大化 ACE-比例 (不是T)
        随机翻转操作数bit, 若ACE-比例上升则接受"""
        best_regs = dict(regs_init)
        best_ace = self.measure_ace_fraction(best_regs, n_probe)
        best_E = hamming_entropy(self.run_once(best_regs)[0][0])  # 结果熵
        best_score = best_ace + 0.5 * best_E  # ACE为主 + 反掩蔽熵辅助
        history = [(0, best_ace, best_score)]
        for it in range(iterations):
            reg_idx = random.choice(list(best_regs.keys()))
            n_bits = random.randint(1, 3)
            candidate = dict(best_regs)
            for _ in range(n_bits):
                bit = random.randint(0, 63)
                candidate[reg_idx] ^= (1 << bit)
            cand_ace = self.measure_ace_fraction(candidate, n_probe)
            cand_E = hamming_entropy(self.run_once(candidate)[0][0])
            cand_score = cand_ace + 0.5 * cand_E
            if cand_score > best_score:
                best_regs = candidate
                best_ace, best_E, best_score = cand_ace, cand_E, cand_score
                history.append((it+1, best_ace, best_score))
        return best_regs, best_ace, best_score, history

def main():
    print("=== 方案1: ACE-比例定向进化 ===")
    code = encode_adds_x0_x1_x2()
    eng = ACEFractionEngine(code)

    # 初始普通操作数
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    init_ace = eng.measure_ace_fraction(regs, 20)
    print(f"初始 ACE-比例: {init_ace:.3f} (随机翻转20bit, diverge比例)")

    # 对照: B(随机)的ACE-比例 (用随机操作数测)
    b_regs = {i: random.getrandbits(64) for i in range(5)}
    b_ace = eng.measure_ace_fraction(b_regs, 20)
    print(f"B(随机) ACE-比例: {b_ace:.3f}")

    # 爬山最大化ACE-比例
    print(f"\n=== ACE-比例爬山 (30轮) ===")
    best, best_ace, best_score, hist = eng.ace_hill_climb(regs, 30)
    print(f"  ACE-比例: {init_ace:.3f} → {best_ace:.3f}")
    print(f"  接受变异: {len(hist)-1}次")
    print(f"  演化操作数: { {k:hex(v) for k,v in best.items()} }")

    # 对比: ACE-比例 vs T目标
    print(f"\n=== 对比: ACE-比例 vs T目标 ===")
    t_best, t_T, _, _ = eng.toggle_hill_climb(regs, 30)
    t_ace = eng.measure_ace_fraction(t_best, 20)
    print(f"  T目标演化: T={t_T}, ACE-比例={t_ace:.3f}")
    print(f"  ACE目标演化: ACE-比例={best_ace:.3f}")
    print(f"  → ACE目标{'>' if best_ace > t_ace else '<'} T目标的ACE-比例")

if __name__ == "__main__":
    main()

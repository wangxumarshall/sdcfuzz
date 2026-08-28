#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_evolution_engine.py — 进化引擎单元测试 (TDD)

验证: 适应度函数(popcount/hamming_entropy/run_once) + 三算子(toggle_hill_climb/
boundary_amplify/context_crossover) + 雪崩测试(avalanche_test)。
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import (EvolutionEngine, popcount, hamming_entropy,
    encode_adds_x0_x1_x2, encode_high_power_alu)

def test_popcount():
    assert popcount(0xFF) == 8
    assert popcount(0) == 0
    assert popcount(0xFFFFFFFFFFFFFFFF) == 64
    assert popcount(0x55) == 4
    print("✓ popcount")

def test_hamming_entropy():
    assert hamming_entropy(0) == 0.0          # 全0, 低熵
    assert hamming_entropy(0xFFFFFFFFFFFFFFFF) == 0.0  # 全1, 低熵
    assert 0.9 <= hamming_entropy(0x5555555555555555) <= 1.0  # 50% 翻转, 高熵(=1.0最大)
    print("✓ hamming_entropy")

def test_run_once_returns_score():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    final, T, M, E, S = eng.run_once(regs)
    assert T >= 0 and M >= 0 and E >= 0 and S >= 0, f"负值: T={T} M={M} E={E} S={S}"
    assert isinstance(final, dict)
    assert len(final) == 5  # X0-X4
    print(f"✓ run_once (T={T} M={M} E={E:.3f} S={S:.2f})")

def test_toggle_hill_climb_increases_T():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    _, init_T, _, _, _ = eng.run_once(regs)
    best, best_T, _, _ = eng.toggle_hill_climb(regs, iterations=20)
    assert best_T >= init_T, f"爬山后T({best_T}) < 初始T({init_T})"
    print(f"✓ toggle_hill_climb (T {init_T}→{best_T})")

def test_boundary_amplify_returns_elite():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    best, T, S, elite = eng.boundary_amplify(regs, iterations=10)
    assert isinstance(elite, list)
    assert T >= 0
    print(f"✓ boundary_amplify (T={T} 精英池={len(elite)}个)")

def test_context_crossover_runs():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    best, T, S = eng.context_crossover({0:0x123,1:0x456,2:0x789,3:0xabc,4:0xdef},
                                        encode_high_power_alu(), iterations=5)
    assert T >= 0
    print(f"✓ context_crossover (T={T} S={S:.2f})")

def test_avalanche_test():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    diff = eng.avalanche_test(regs, 1, 0)  # 扰动 X1 bit0
    assert diff >= 0
    print(f"✓ avalanche_test (扰动X1 bit0 差异={diff})")

def test_long_sequence_evolution():
    """长指令序列进化 (Task2 前置: 多指令混合序列)"""
    seq = b''
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('230200ca')  # eor x3,x1,x2
    seq += bytes.fromhex('610c029b')  # mul x1,x2,x3
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2
    seq += bytes.fromhex('6300008b')  # add x3,x3,x3
    seq += bytes.fromhex('640200ca')  # eor x4,x1,x2
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2
    eng = EvolutionEngine(seq)
    regs = {0: 0x111, 1: 0x222, 2: 0x333, 3: 0x444, 4: 0x555}
    _, T, _, _, _ = eng.run_once(regs)
    assert T > 0, "长序列应有翻转"
    best, best_T, _, _ = eng.toggle_hill_climb(regs, 30)
    assert best_T >= T
    print(f"✓ long_sequence_evolution (长序列 T={T}→{best_T})")

if __name__ == "__main__":
    test_popcount()
    test_hamming_entropy()
    test_run_once_returns_score()
    test_toggle_hill_climb_increases_T()
    test_boundary_amplify_returns_elite()
    test_context_crossover_runs()
    test_avalanche_test()
    test_long_sequence_evolution()
    print("\nAll tests passed")

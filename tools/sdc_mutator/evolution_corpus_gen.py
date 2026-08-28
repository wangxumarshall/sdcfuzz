#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""evolution_corpus_gen.py — 用进化引擎批量生成语料 D (高压操作数 .bin)

对多个指令序列模板, 各跑进化引擎(三算子), 收集 Score 超阈值的演化操作数,
输出 .bin (movz/movk 装入操作数 + 模板指令序列), 供 snap_tool make → 语料 D。
"""
import sys, os, struct, random
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import EvolutionEngine, encode_adds_x0_x1_x2

# 多个指令序列模板 (覆盖不同微架构压力)
TEMPLATES = [
    ('add_chain', bytes.fromhex('200b008b' * 4)),  # 4x ADD
    ('mul_chain', bytes.fromhex('610c029b' * 4)),  # 4x MUL
    ('toggle_chain', bytes.fromhex('200b008b' + '230200ca' * 3)),  # ADD+EOR
    ('mixed', bytes.fromhex('200b008b' + '610c029b' + '230200ca' + '200b00ab')),  # 混合
    ('adds_carry', bytes.fromhex('200b00ab' * 4)),  # 4x ADDS (进位链)
]

def build_bin_with_operands(template_code, regs):
    """构造 .bin: movz/movk 装入操作数(X0-X4) + 模板指令序列"""
    out = b''
    for idx in range(5):
        val = regs.get(idx, 0) & 0xFFFFFFFFFFFFFFFF
        # movz xN, #imm16, lsl #0  (encoding: 0xD2800000 | (imm16<<5) | N)
        out += struct.pack('<I', 0xD2800000 | (idx) | ((val & 0xFFFF) << 5))
        if (val >> 16) & 0xFFFF:
            out += struct.pack('<I', 0xF2A00000 | (idx) | (((val >> 16) & 0xFFFF) << 5))
        if (val >> 32) & 0xFFFF:
            out += struct.pack('<I', 0xF2C00000 | (idx) | (((val >> 32) & 0xFFFF) << 5))
        if (val >> 48) & 0xFFFF:
            out += struct.pack('<I', 0xF2E00000 | (idx) | (((val >> 48) & 0xFFFF) << 5))
    out += template_code
    return out

def generate_evolved_corpus(out_dir, n_per_template=10, iterations=40):
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    score_threshold = 10.0  # 只收集 Score 超阈值的
    for name, code in TEMPLATES:
        eng = EvolutionEngine(code)
        for i in range(n_per_template):
            # 随机初始操作数 (非魔术数字)
            regs = {j: random.getrandbits(64) for j in range(5)}
            # 三算子演化
            r1, T1, _, _ = eng.toggle_hill_climb(regs, iterations)
            r2, T2, _, elite = eng.boundary_amplify(r1, iterations // 2)
            # 跑最终 Score
            _, T_final, M_final, E_final, S_final = eng.run_once(r2)
            if S_final >= score_threshold:
                bin_bytes = build_bin_with_operands(code, r2)
                open(f'{out_dir}/d_{name}_{i:02d}.bin', 'wb').write(bin_bytes)
                total += 1
    print(f"Generated {total} evolved .bin to {out_dir} (threshold Score>={score_threshold})")
    return total

if __name__ == "__main__":
    n = generate_evolved_corpus('output/bin_evolved')

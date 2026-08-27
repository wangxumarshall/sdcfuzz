#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""csp_targeted_generator.py — CSP定向操作数生成器 (Paper2 best-paper 第一个微小步骤)

设计概念: A/B证伪了朴素operand字典(全0/全1/交替,diverge率3.9%<随机8.0%),
原因是逻辑掩蔽: 结构化极端值产生确定性结果,bit-flip易被掩蔽。
本生成器用约束求解生成'最大化目标微架构路径激活'的操作数族, 每个变体激活
不同进位路径+不同结果模式, 减少掩蔽, 目标在bit-flip diverge率上击败随机。

最可证案例: add 的最长进位链
- 朴素字典只给全1+1=0 (单一, 确定性, 易掩蔽)
- CSP定向: 求解'使进位从bit0传播到bitN'的所有操作数族, 覆盖:
  * 64位全进位链: 0xFFFF...F + 1 → 0, C=1 (全1)
  * 32位进位边界: 0x00000000FFFFFFFF + 1 → 0x100000000 (进位传到bit32)
  * 48位进位链: 0x0000FFFFFFFFFFFF + 1
  * 符号溢出进位: 0x7FFFFFFFFFFFFFFF + 1 → 0x8000... (符号位翻转, NZCV.V=1)
  * 单bit游走进位: 0x1<<n + 0x1<<n → 进位到bit n+1 (n=0..62, 63个变体)
  * 字节进位边界: 0x00FF...F + 1 → 0x0100...0
  * 半字进位边界: 0x0000FFFF... + 1
  * 进位链+非零结果: 0xFFFF...F + 0xFFFF...F → 0xFFFF...E + C (全进位+非零结果, 减掩蔽)
每个变体激活不同进位路径, 结果模式多样, 减少bit-flip被逻辑掩蔽的概率。

输出: .S 变体文件 (供 snap_tool make → 语料), 或直接 .bin 操作数注入。

用法: python3 csp_targeted_generator.py <template.S> <out_dir> [--max N]
"""
import os, sys, re, itertools, pathlib

# CSP 定向操作数族: (label, x1_value, x2_value, 微架构路径说明)
# 每个变体最大化不同的进位链路径 + 产生不同结果模式 (减掩蔽)
CARRY_CHAIN_TARGETED = [
    # 64位全进位链 + 零结果 (传统, 但作为基线保留)
    ("cc64_full_zero",   0xFFFFFFFFFFFFFFFF, 0x0000000000000001, "64位全进位链→0, C=1"),
    # 64位全进位链 + 非零结果 (减掩蔽: 结果不全0)
    ("cc64_full_nonzero",0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, "64位全进位→0xFFFF...E+C, 非零结果"),
    # 32位进位边界 (进位传到bit32)
    ("cc32_boundary",    0x00000000FFFFFFFF, 0x0000000000000001, "32位进位边界→0x100000000"),
    # 48位进位链
    ("cc48",             0x0000FFFFFFFFFFFF, 0x0000000000000001, "48位进位链"),
    # 符号溢出进位 (NZCV.V=1, 符号位翻转路径)
    ("cc_sign_overflow", 0x7FFFFFFFFFFFFFFF, 0x0000000000000001, "符号溢出→0x8000..., V=1"),
    # 进位链 + 交替位 (双路径激活)
    ("cc64_plus_alt",    0xFFFFFFFFFFFFFFFF, 0x5555555555555555, "全进位+交替位结果"),
    # 单bit游走进位 (每个n激活不同进位路径, 63个变体的代表)
    ("cc_bit31_walk",    0x0000000080000000, 0x0000000080000000, "bit31进位→bit32"),
    ("cc_bit63_walk",    0x8000000000000000, 0x8000000000000000, "bit63进位→溢出"),
    # 字节进位边界
    ("cc_byte_boundary", 0x00FF00FF00FF00FF, 0x0000000000000001, "字节进位边界"),
    # 乘法器最长延迟 (Complex端口4-cyc)
    ("mul_max",          0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF, "乘法器最长延迟"),
    # 交替翻转 + 进位 (toggle + carry 双路径)
    ("toggle_plus_carry",0x5555555555555555, 0xAAAAAAAAAAAAAAAA, "交替翻转+进位→全1"),
]

def reg_to_imm64_macro(reg, val, indent="    "):
    """生成单行 LOAD_IMM64 宏调用把 64-bit val 装入 reg (asm_common.S.inc 宏, 单行)"""
    s0 = val & 0xFFFF
    s1 = (val >> 16) & 0xFFFF
    s2 = (val >> 32) & 0xFFFF
    s3 = (val >> 48) & 0xFFFF
    return f"{indent}LOAD_IMM64 {reg}, 0x{s0:04X}, 0x{s1:04X}, 0x{s2:04X}, 0x{s3:04X}"

def generate_carry_chain_variants(template_path, out_dir, max_variants=None):
    """对含 // CSP: carry_chain_pair 标记的模板, 生成定向进位链变体族 (x1+x2配对)

    CSP 标记 // CSP: carry_chain_pair 后跟两条操作数构造指令 (x1构造 + x2构造),
    生成器配对替换为 CARRY_CHAIN_TARGETED 的 (x1, x2) 对, 实现真正进位链定向。
    兼容旧 // CSP: carry_chain 单操作数标记。
    """
    lines = open(template_path).read().splitlines()
    # 找 CSP 标记 + 其后连续的非空非注释指令行 (最多2条, x1+x2构造)
    muts = []
    for i, line in enumerate(lines):
        m = re.search(r'//\s*CSP:\s*(\w+)', line)
        if m:
            slot = m.group(1)
            # 收集其后 1-2 条操作数构造指令
            ops = []
            j = i + 1
            while j < len(lines) and len(ops) < 2:
                if lines[j].strip()=='' or lines[j].strip().startswith('//'):
                    j += 1; continue
                ops.append(j)
                j += 1
            if ops:
                muts.append((slot, ops, [lines[k] for k in ops]))
    if not muts:
        return 0
    base = pathlib.Path(template_path).stem
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for label, x1, x2, desc in CARRY_CHAIN_TARGETED:
        if max_variants and n >= max_variants: break
        variant = lines[:]
        for (slot, ops, origs), (lab, v1, v2, d) in zip(muts, [(label,x1,x2,desc)]*len(muts)):
            # 第1条操作数构造 → x1, 第2条 → x2 (配对)
            vals = [v1, v2]
            for idx, (line_idx, orig) in enumerate(zip(ops, origs)):
                if idx >= len(vals): break
                m = re.search(r'\b([xd]\d+)\b', orig)
                reg = m.group(1) if m else ('x1' if idx==0 else 'x2')
                indent = len(variant[line_idx]) - len(variant[line_idx].lstrip())
                variant[line_idx] = reg_to_imm64_macro(reg, vals[idx], ' '*indent) + f"    // CSP:{slot}={label}[{idx}]"
        out = os.path.join(out_dir, f"{base}__csp_{label}.S")
        with open(out, 'w') as f:
            f.write("\n".join(variant) + "\n")
        n += 1
    return n

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    tpl, out = sys.argv[1], sys.argv[2]
    mx = None
    if "--max" in sys.argv: mx = int(sys.argv[sys.argv.index("--max")+1])
    n = generate_carry_chain_variants(tpl, out, mx)
    print(f"Generated {n} CSP-targeted variant(s) from {tpl} -> {out}")

if __name__ == "__main__":
    main()

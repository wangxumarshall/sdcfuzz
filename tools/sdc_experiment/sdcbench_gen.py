#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sdcbench_gen.py — 高 SDC 检出率检测序列生成器

设计原则 (实测验证 2026-09-05):
  1. 独立累加器链: 8 条互相不依赖的 ADD/SUB/MUL 链, 任何一条上的单 bit
     翻转都会存活到末尾 (不被后继指令重新混合覆盖 — 这是 xorshift 链
     0% SDC 的教训: 值被反复改写, 翻转被吞).
  2. 结尾 XOR 聚合: 所有链的结果异或成单一 checksum, 单链翻转必然传播.
  3. 操作数注入: movz/movk 前缀装载常量, 核心链指令 + 步进常量.
  4. gem5 注入协议: CHAOSPhysReg arch_frontend 模式, first_clock 取
     ROI 中段 (需按序列 cycle 数自适应), max_faults=1, bit_flip.

变异维度 (生成 1000+ 个不同序列):
  - 核心链指令: adds/subs/mul/add/eor/and/orr/bic (微架构压力多样性)
  - 操作数常量: 字典值 (进位边界/交替位/最大最小/随机) — CSP 定向族
  - 链长: 60-120 iter
  - 聚合方式: eor/add 聚合
  - 寄存器分配: 固定 8 链 x0-x7 + 步进 x9, 或引入第二常量 x10

输出: 每序列一个 .c 源 + 静态 ELF, 以及 manifest.json (序列元数据).
"""
import os, sys, json, random, subprocess, struct

# 操作数字典 — (name, init, step) 步进链族。溯源 (2026-09-05 逐值审计):
#   - 8 族值借自 csp_targeted_generator.CARRY_CHAIN_TARGETED (同名同值);
#   - cc64_full/cc64_nonzero 是其 cc64_full_zero/cc64_full_nonzero 改名简化;
#   - 8 族 (alt01_step/golden_step/sparse_walk 等) 为 sdcbench 原创步进链设计
#     (golden_step=0x9E3779B97F4A7C15 溯源校准实验 sdcbench2.c), CSP 表无对应物。
#   注意语义差异: CSP 表是 (x1,x2) 操作数对, 本表是 (init,step) 步进对 —
#   不做强行合并 (两语义塞一张表是假抽象)。
OPERAND_FAMILIES = [
    ("cc64_full",        0xFFFFFFFFFFFFFFFF, 0x0000000000000001),  # 64位全进位链→0
    ("cc64_nonzero",     0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF),  # 全进位+非零结果
    ("cc32_boundary",    0x00000000FFFFFFFF, 0x0000000000000001),  # 进位传到bit32
    ("cc48",             0x0000FFFFFFFFFFFF, 0x0000000000000001),  # 48位进位链
    ("cc_sign_overflow", 0x7FFFFFFFFFFFFFFF, 0x0000000000000001),  # 符号溢出 V=1
    ("cc64_plus_alt",    0xFFFFFFFFFFFFFFFF, 0x5555555555555555),  # 全进位+交替位
    ("cc_bit31_walk",    0x0000000080000000, 0x0000000080000000),  # bit31→bit32
    ("cc_bit63_walk",    0x8000000000000000, 0x8000000000000000),  # bit63→溢出
    ("cc_byte_boundary", 0x00FF00FF00FF00FF, 0x0000000000000001),  # 字节进位边界
    ("toggle_plus_carry",0x5555555555555555, 0xAAAAAAAAAAAAAAAA),  # 交替翻转+进位
    ("alt01_step",       0x5555555555555555, 0x0000000000000001),  # 交替位+步进
    ("alt10_step",       0xAAAAAAAAAAAAAAAA, 0x0000000000000001),
    ("maxpos_step",      0x7FFFFFFFFFFFFFFF, 0x0000000000000002),
    ("maxneg_step",      0x8000000000000000, 0x0000000000000002),
    ("golden_step",      0x9E3779B97F4A7C15, 0x9E3779B97F4A7C15),  # 黄金比率步进
    ("sparse_walk",      0x0001000100010001, 0x0001000100010001),  # 稀疏位游走
    ("densr_walk",       0x7FFF7FFF7FFF7FFF, 0x0002000200020002),
    ("rand_mix",         0x3CEF3CEF3CEF3CEF, 0x0F0F0F0F0F0F0F0F),
]

# 核心链指令模板 (8 链并行, 每链一条指令/iter)
CHAIN_OPS = {
    "adds":  "adds x{d}, x{d}, x{a}",        # 进位链压力
    "subs":  "subs x{d}, x{d}, x{a}",        # 借位链
    "mul":   "mul  x{d}, x{d}, x{a}",        # 乘法器 (4-cyc 延迟)
    "add":   "add  x{d}, x{d}, x{a}",        # 无标志加
    "eor":   "eor  x{d}, x{d}, x{a}",        # 异或翻转 (非自耗: eor 链步进非零则翻转存活)
    "and":   "and  x{d}, x{d}, x{a}",        # 掩码 (低 SDC 风险, 保留作对照)
    "orr":   "orr  x{d}, x{d}, x{a}",
    "bic":   "bic  x{d}, x{d}, x{a}",        # 位清除
    "mixed": None,                            # 特殊: 每链不同 op
}
CHAIN_OP_NAMES = ["adds", "subs", "mul", "add", "eor", "orr", "bic", "and"]


def movz_seq(reg, val):
    """movz/movk 装载 64 位常量到 x<reg>."""
    out = [f"movz x{reg}, #{val & 0xFFFF}"]
    for i, shift in enumerate((16, 32, 48)):
        word = (val >> shift) & 0xFFFF
        if word:
            out.append(f"movk x{reg}, #{word}, lsl #{shift}")
    return "\n".join(out)


def gen_asm(op_name, init_val, step_val, iters, seed):
    """生成一条检测序列的 asm 块."""
    rng = random.Random(seed)
    lines = []
    # 初始化 8 链初值: 全部用 init_val 族的不同相位
    for i in range(8):
        # 每链不同初值: init_val 旋转 i*7 位 再异或链号扩散 — 保证 8 链互不相等 (全1 旋转会退化, 故叠加链号)
        rot = ((init_val << (i * 7)) | (init_val >> (64 - i * 7))) & 0xFFFFFFFFFFFFFFFF if i else init_val
        v = (rot ^ (0x9E3779B97F4A7C15 * (i + 1))) & 0xFFFFFFFFFFFFFFFF
        lines.append(movz_seq(i, v))
    # 步进常量
    lines.append(movz_seq(9, step_val))
    lines.append(movz_seq(10, (step_val ^ 0xA5A5A5A5A5A5A5A5) & 0xFFFFFFFFFFFFFFFF))
    # 核心链
    lines.append(f".rept {iters}")
    for i in range(8):
        if op_name == "mixed":
            op = CHAIN_OP_NAMES[(i + seed) % len(CHAIN_OP_NAMES)]
        else:
            op = op_name
        # 步进源交替 x9/x10 增加转发路径多样性
        src = 9 if (i + iters) % 2 == 0 else 10
        lines.append(CHAIN_OPS[op].format(d=i, a=src))
    lines.append(".endr")
    # XOR 聚合 (所有链折叠到 x0)
    for i in range(1, 8):
        lines.append(f"eor x0, x0, x{i}")
    return "\n".join(lines)


C_TEMPLATE = r'''#include <unistd.h>
#include <stdint.h>
static void put_hex(unsigned long v){
    char buf[16];
    for (int i=15;i>=0;--i){ unsigned d = v & 0xf; buf[i] = d<10? '0'+d : 'a'+d-10; v>>=4; }
    write(1,buf,16); write(1,"\n",1);
}
int main(void){
    unsigned long r;
    asm volatile(
{ASM}
        "mov %0, x0"
        : "=r"(r) :: "x0","x1","x2","x3","x4","x5","x6","x7","x9","x10","cc");
    put_hex(r);
    return 0;
}
'''


def gen_source(op_name, init_val, step_val, iters, seed):
    asm = gen_asm(op_name, init_val, step_val, iters, seed)
    asm_lines = "\n".join(f'        "{l}\\n"' for l in asm.split("\n"))
    return C_TEMPLATE.replace("{ASM}", asm_lines)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "output/sdcbench"
    n_target = int(sys.argv[2]) if len(sys.argv) > 2 else 1400
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "src"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "bin"), exist_ok=True)

    manifest = []
    seq_id = 0
    rng = random.Random(20260905)
    # 组合空间: op(9) × 族(18) × iters(4) = 648 基础组合, 之后叠加 seed 变体轮次直到 n_target.
    combo_round = 0
    while seq_id < n_target:
      round_start = seq_id
      for op in ["adds", "subs", "mul", "add", "eor", "mixed", "orr", "bic", "and"]:
        for fam_name, init_v, step_v in OPERAND_FAMILIES:
            for iters in (60, 80, 100, 120):
                if seq_id >= n_target:
                    break
                seed = rng.randrange(1 << 30)
                name = f"seq_{seq_id:04d}_{op}_{fam_name}_i{iters}" + (f"_v{combo_round}" if combo_round else "")
                src = gen_source(op, init_v, step_v, iters, seed)
                src_path = os.path.join(out_dir, "src", name + ".c")
                bin_path = os.path.join(out_dir, "bin", name)
                with open(src_path, "w") as f:
                    f.write(src)
                r = subprocess.run(["gcc", "-static", "-O2", "-o", bin_path, src_path],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    print(f"COMPILE FAIL {name}: {r.stderr[:200]}", file=sys.stderr)
                    continue
                manifest.append({
                    "name": name, "id": seq_id, "op": op, "family": fam_name,
                    "iters": iters, "seed": seed, "init": hex(init_v),
                    "step": hex(step_v), "bin": bin_path, "src": src_path,
                })
                seq_id += 1
            if seq_id >= n_target:
                break
        if seq_id >= n_target:
            break
      if seq_id == round_start or combo_round > 12:
            break  # 本轮无新增(全部编译失败)或超轮次上限
      combo_round += 1
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"Generated {len(manifest)} sequences in {out_dir}")


if __name__ == "__main__":
    main()

// SPDX-License-Identifier: Apache-2.0
// e1_carry_chain.S — E1: 加法器最长进位链
//
// 模板（plan E1，对应设计概念"操作数翻转率最大化 + 进位链极限", weak 因素②老化）:
//   强制加法器进位信号从 bit0 传播到 bit63（最长组合逻辑路径），延迟最大、
//   最易被时序违例击穿。配合 32/48 位进位边界变异，覆盖不同进位链长度。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 变体1: 64 位全进位链 (0xFFF..F + 1 = 0, C=1)
    // MUT: carry_chain
    LOAD_ALL_ONES  x1
    mov     x2, #1
    adds    x0, x1, x2          // 进位 bit0→bit63, x0=0, C=1
    // SDC 验证: x0=0, NZCV.C=1

    // 变体2: 32 位进位边界 (0x00000000FFFFFFFF + 1)
    LOAD_CARRY32   x3
    mov     x4, #1
    adds    x5, x3, x4          // 32→64 位进位传播边界, x5=0x100000000

    // 变体3: 48 位进位链 (0x0000FFFFFFFFFFFF + 1)
    LOAD_CARRY48   x6
    mov     x7, #1
    adds    x8, x6, x7          // 48 位进位链, x8=0x0001000000000000

    // 变体4: 最大正 + 1 (有符号溢出, 测 NZCV flags 生成逻辑)
    LOAD_MAX_POS   x9
    mov     x10, #1
    adds    x11, x9, x10        // 0x7FFF..F + 1 = 0x8000..0, V=1(溢出), N=1
    // SDC 验证: x11=0x8000000000000000, NZCV.V=1

    // 变体5: 单 bit 游走进位 (bit 31)
    mov     x12, #0x80000000
    mov     x13, #0x80000000
    adds    x14, x12, x13       // bit31 进位 → bit32, x14=0x100000000

    // 验证锚点: 汇总多个进位结果
    eor     x15, x0, x5         // 0 ^ 0x100000000
    add     x16, x8, x11

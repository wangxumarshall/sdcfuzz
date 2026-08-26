// SPDX-License-Identifier: Apache-2.0
// e2_mul_extreme.S — E2: 乘法器极端操作数
//
// 模板（plan E2，对应设计概念"乘法极端操作数激活最长延迟路径"）:
//   V110 Complex 端口乘法器 4-cycle latency。两个最大值相乘走最长延迟路径。
//   umull/smull 测无符号/有符号符号处理逻辑。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 构造 0xFFFFFFFF (32-bit max)
    movz    x1, #0xFFFF, lsl #0
    movk    x1, #0xFFFF, lsl #16    // x1 = 0x00000000FFFFFFFF
    mov     x2, x1                    // x2 = 0xFFFFFFFF

    // umull: 32×32→64 无符号, 0xFFFFFFFF × 0xFFFFFFFF = 0xFFFFFFFE00000001
    umull   x0, w1, w2
    // SDC 验证: x0 必须 = 0xFFFFFFFE00000001

    // smull: 有符号, w1/w2 = -1, -1 × -1 = 1
    smull   x3, w1, w2
    // SDC 验证: x3 必须 = 1 (符号处理逻辑)

    // 全 1 × 交替 (不同乘法器内部路径)
    // MUT: int
    LOAD_ALL_ONES  x4
    LOAD_ALT_01    x5
    mul     x6, x4, x5             // 全1 × 01, 走 Complex

    // 最大正 × 最大正 (符号位路径)
    LOAD_MAX_POS   x7
    mul     x8, x7, x7             // maxpos²

    // madd 链 (Complex 端口连续压力)
    madd    x9,  x4, x5, x6
    msub    x10, x7, x4, x8

    // 验证锚点
    eor     x11, x0, x3            // 0xFFFFFFFE00000001 ^ 1
    add     x12, x6, x9

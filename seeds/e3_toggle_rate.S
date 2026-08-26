// SPDX-License-Identifier: Apache-2.0
// e3_toggle_rate.S — E3: 高翻转率交替操作数
//
// 模板（plan E3，对应设计概念"操作数翻转率最大化 (Max Toggle Rate)", weak 因素②老化）:
//   0x5555... 与 0xAAAA... 交替 → 每个 bit 都翻转 → 100% bit-toggle
//   → 最大动态功耗/di/dt, 激发 HCI/NBTI 老化失效。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALT_01    x1             // 0x5555555555555555
    LOAD_ALT_10    x2             // 0xAAAAAAAAAAAAAAAA

    add     x3, x1, x2            // ALU 所有 bit 0→1 或 1→0 (结果 0xFFFFFFFFFFFFFFFF)
    add     x4, x2, x1            // 再次全翻转 (输入顺序换, 结果同)
    sub     x5, x1, x2            // 减法路径也全翻转
    eor     x6, x1, x2            // XOR: 0xFFFF... (全1, 输出翻转)
    eor     x7, x2, x1            // XOR: 相同 (但 ALU 输入全翻转)
    and     x8, x1, x2            // AND: 0x0 (全0, 输出翻转)
    orr     x9, x1, x2            // OR:  0xFFFF... (全1, 输出翻转)
    bic     x10, x1, x2           // BIC: x1 & ~x2
    orn     x11, x2, x1           // ORN: x2 | ~x1
    eon     x12, x1, x2           // EON: x1 ^ ~x2

    // 重复多轮加深翻转压力
    add     x13, x3, x4
    eor     x14, x5, x6
    and     x15, x7, x8
    orr     x16, x9, x10
    add     x17, x11, x12
    eor     x18, x13, x14

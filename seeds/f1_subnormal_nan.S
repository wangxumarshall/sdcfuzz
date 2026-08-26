// SPDX-License-Identifier: Apache-2.0
// f1_subnormal_nan.S — F1: Subnormal/NaN 等 FSU 慢路径覆盖
//
// 模板（plan F1，对应设计概念"FSU 特殊操作数攻击"）:
//   Subnormal 指数全0尾数非0, 大多数 FSU 用微码/慢路径处理, 是 Gate 覆盖盲区。
//   NaN 传播逻辑、Infinity 运算、符号位翻转 (IEEE 754 特殊规则) 极少被测试。
//   覆盖率 80% → 90%+ 的关键。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    movi    d0, #0                // +0.0 (所有位清零)

    // 构造最小正 Subnormal (0x0000000000000001)
    LOAD_SUBNORMAL_MIN d1, x0     // d1 = 最小正 subnormal

    fadd    d2, d0, d1            // 0 + Subnormal → FSU 慢路径
    fmul    d3, d1, d1            // Subnormal × Subnormal → 可能下溢到 0
    fdiv    d4, d1, d0            // Subnormal / 0 → +Infinity (特殊处理)

    // NaN 传播测试
    LOAD_QNAN       d5, x1        // d5 = Quiet NaN (0x7FF8000000000000)
    fadd    d6, d5, d1            // NaN + 任何数 = NaN (传播逻辑)
    fmul    d7, d5, d5            // NaN × NaN = NaN
    fcmp    d5, d1                // NaN 比较 → 总是 Unordered (NZCV 特殊设置)

    // Infinity 运算
    LOAD_POS_INF    d8, x2        // +Inf
    fadd    d9,  d8, d8           // Inf + Inf = Inf
    fsub    d10, d8, d8           // Inf - Inf = NaN (特殊)
    fdiv    d11, d8, d0           // Inf / 0 = Inf

    // 符号位翻转 (+0.0 vs -0.0)
    LOAD_NEG_ZERO    d12, x3      // -0.0
    fadd    d13, d0, d12          // +0 + -0 = +0 (IEEE 754 规则)
    fcmp    d0, d12               // +0 == -0 (比较相等, 但符号位不同)

    // 最大有限值 (接近溢出边界)
    LOAD_MAX_FINITE  d14, x4      // 0x7FEFFFFFFFFFFFFF
    fmul    d15, d14, d14         // 接近溢出
    fadd    d16, d14, d14         // 可能溢出到 Inf

    // 验证锚点: 把 FSU 结果回读整数寄存器
    fmov    x5, d2                // 0+subnormal 结果
    fmov    x6, d6                // NaN+subnormal 结果 (应为 NaN)
    fmov    x7, d9                // Inf+Inf 结果 (应为 Inf)
    fmov    x8, d13               // +0+-0 结果

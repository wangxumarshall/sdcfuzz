// SPDX-License-Identifier: Apache-2.0
// v1_fsu_vdroop.S — V1: FSU 功耗振荡器 (Voltage Droop Oscillator)
//
// 攻击向量（plan 文档 V1，对应设计概念"FSU Vdroop 激发 transient"）：
//   TaiShan V110 双 FSU×128-bit NEON，FP32 FMA 7-cycle latency。
//   NOP 窗口(低功耗, 电压恢复标称) → 双 FSU 满载 FMLA 爆发(高 di/dt) →
//   NOP 窗口(电压跌落尾巴, 时序裕量最薄) → 验证锚点指令。
//   在电压振荡谷底执行验证指令，是 SDC 最易发生窗口。
//
// 操作数空间压力（设计概念"FSU 特殊操作数攻击"，落地 weak 因素②老化）：
//   FMLA 爆发段注入操作数字典全谱——全 1/交替位/subnormal/NaN/Inf，
//   不同操作数激活 FSU 内部不同 Gate 子集，subnormal/NaN 走微码慢路径
//   （极低覆盖盲区），把覆盖率从"指令种类"扩展到"操作数组合"。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // ---- 低功耗窗口 (8×nop, 让电压恢复到标称值) ----
    NOP_FILL 8

    // ---- 操作数构造: 向量寄存器注入操作数字典全谱 ----
    // v16/v17 = 全 1 (最大翻转); v18/v19 = 交替 01/10 (50%/100% toggle)
    LOAD_ALL_ONES  x0
    fmov    d16, x0
    dup     v16.4s, v16.s[0]              // v16 = 全 1 ×4 lane
    mov     v17.16b, v16.16b             // v17 = 全 1
    LOAD_ALT_01    x1
    fmov    d18, x1
    dup     v18.4s, v18.s[0]              // v18 = 0x5555... ×4
    LOAD_ALT_10    x2
    fmov    d19, x2
    dup     v19.4s, v19.s[0]              // v19 = 0xAAAA... ×4
    // v20 = subnormal (FSU 慢路径), v21 = Quiet NaN (传播), v22 = +Inf
    LOAD_SUBNORMAL_MIN d0, x3
    fmov    d20, d0
    dup     v20.4s, v20.s[0]              // subnormal 复制到 4 lane
    LOAD_QNAN       d1, x4
    fmov    d21, d1
    dup     v21.4s, v21.s[0]              // QNaN ×4
    LOAD_POS_INF    d2, x5
    fmov    d22, d2
    dup     v22.4s, v22.s[0]              // +Inf ×4

    // ---- 高功耗爆发: 双 FSU 满载 FMLA, 无依赖链 ----
    // 每对相邻 FMLA 用不同目标寄存器, 消除 WAW/RAW 依赖, 双端口可同时发射
    fmla    v0.4s,  v16.4s, v17.4s       // FSU port 0 (全1×全1)
    fmla    v1.4s,  v18.4s, v19.4s       // FSU port 1 (01×10 → 全翻转)
    fmla    v2.4s,  v20.4s, v21.4s       // subnormal × NaN (慢路径)
    fmla    v3.4s,  v22.4s, v16.4s       // Inf × 全1 (特殊处理)
    fmla    v4.4s,  v17.4s, v19.4s
    fmla    v5.4s,  v18.4s, v16.4s
    fmla    v6.4s,  v19.4s, v17.4s
    fmla    v7.4s,  v16.4s, v18.4s
    fmla    v8.4s,  v20.4s, v22.4s       // subnormal × Inf (下溢路径)
    fmla    v9.4s,  v21.4s, v18.4s       // NaN × 交替 (传播)
    fmla    v10.4s, v16.4s, v19.4s
    fmla    v11.4s, v17.4s, v18.4s
    fmla    v12.4s, v19.4s, v16.4s
    fmla    v13.4s, v18.4s, v17.4s
    fmla    v14.4s, v22.4s, v21.4s       // Inf × NaN

    // ---- 低功耗窗口 (电压跌落尾巴, SDC 最易发生处) ----
    NOP_FILL 4

    // ---- 验证锚点 (此时核心电压可能仍在振荡谷底) ----
    // end-state 比对这些寄存器终态值; 任何一位翻转即 SDC
    // 用 x9-x14 (避开 x6/x7 data 基址, x30 链接寄存器)
    add     x9,  x0, x1                   // 整数加, 全1+01
    eor     x10, x2, x3                  // 位运算, 对时序更敏感
    madd    x11, x4, x5, x9              // 整数乘加, 走 Complex 端口(4-cyc)
    mov     x12, v0.d[0]                 // 把 FSU 结果回读整数寄存器 (SDC 锚点)
    mov     x13, v2.d[0]                 // subnormal×NaN 结果锚点

    NOP_FILL 4

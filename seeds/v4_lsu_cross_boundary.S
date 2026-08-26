// SPDX-License-Identifier: Apache-2.0
// v4_lsu_cross_boundary.S — V4: LSU 跨边界访存压榨
//
// 攻击向量（plan V4 + L2 双 AGU split，对应设计概念"LSU 跨 cache line/前递压力"）:
//   V110 2×AGU, cross-16B +1-2cyc, StFwd 6-7cyc。LSU 内部 split-access 逻辑
//   在连续高频触发时是 SDC 缺陷易藏处。
//
// 寻址约束（实测）: stp/ldp 仅 [Xn,#imm(8倍数)] 或 [Xn]，不接受 [Xn,Xm]。
//   跨边界须先 add 计算非对齐地址到寄存器，再 [reg]。
//   x6 = data1_range.base (0x7'0000'0000, 4MB, 初值 0)。
//
// SDC 检测: store→load 往返自洽, end-state checksum 捕获翻转。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 操作数构造: 宽交替字节 (最大化拼接路径差异)
    // MUT: int
    LOAD_BYTE_ALT  x0           // 0x00FF00FF00FF00FF
    LOAD_ALL_ONES  x1
    LOAD_ALT_01    x2
    LOAD_ALT_10    x3

    // 模式A: 跨 16B 边界 Load/Store Pair (add 计算非对齐基址)
    add     x8, x6, #14         // x8 = data1_base + 14 (跨 16B 边界, 16B 访问 14..29)
    stp     x0, x1, [x8]       // 跨边界写入 16B
    ldp     x4, x5, [x8]       // 立即读回 (跨边界 StFwd, 6-7+1-2 cyc)
    // SDC 检测: x4 应= x0, x5 应= x1

    // 模式B: 跨 64B Cache Line 边界
    add     x9, x6, #60        // x9 = base + 60 (16B 访问 60..75 跨 64B line)
    stp     x2, x3, [x9]
    ldp     x10, x11, [x9]     // x10 应= x2, x11 应= x3

    // 模式C: 跨 128B L3 Line 边界 (实测 L3 line=128B)
    add     x10, x6, #124       // base+124, 16B 访问 124..139 跨 128B L3 line
    stp     x0, x1, [x10]
    ldp     x12, x13, [x10]

    // 模式D: 128-bit 向量跨边界 (最大压力)
    fmov    d0, x0
    fmov    d1, x1
    // 跨 16B 边界的 128-bit store/load
    add     x11, x6, #14
    stur    q0, [x11]          // 128-bit store 跨 16B 边界
    ldur    q2, [x11]          // 128-bit load 跨边界 (split-merge 双份压力)
    // SDC 检测: q2 应= q0

    // 模式E: 交错跨边界 load/store (压满 2 个 AGU)
    add     x12, x6, #14       // AGU0 基址 (跨边界)
    add     x13, x6, #78       // AGU1 基址 (另一个跨边界)
    ldp     x14, x15, [x12]    // AGU0 split access
    ldp     x16, x17, [x13]    // AGU1 同时 split access

    // 验证锚点 (整数结果汇总)
    eor     x18, x4, x0        // x4(读回) vs x0(写入), 应=0
    eor     x19, x10, x2       // x10 vs x2, 应=0
    add     x20, x18, x19      // 汇总

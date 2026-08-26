// SPDX-License-Identifier: Apache-2.0
// l2_dualagu_split.S — L2: 多端口 AGU 并发 + 跨边界
//
// 模板（plan L2，对应设计概念"双 AGU 并发 split access"）:
//   V110 L1D 支持 2×128-bit/cycle (2 load 或 1 load+1 store)。
//   同时打满 2 个 AGU, 两个访存都跨 16B 边界 → LSU split-merge 逻辑双份压力。
//   x6 = data1_base。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1
    LOAD_ALT_10    x2
    LOAD_BYTE_ALT  x3

    // 预写数据到两个跨边界区域
    add     x8, x6, #14              // AGU0 基址 (跨 16B 边界)
    add     x9, x6, #78              // AGU1 基址 (跨另一个 16B 边界, 64+14)
    stp     x0, x1, [x8]             // 写 AGU0 区域
    stp     x2, x3, [x9]             // 写 AGU1 区域

    // 同时两个跨边界 Load Pair (压满 2 AGU, split-merge 双份)
    ldp     x4, x5, [x8]             // AGU0: split access
    ldp     x10, x11, [x9]           // AGU1: 同时 split (避免覆盖 x6 基址)

    // SDC 检测: x4=x0, x5=x1, x10=x2, x11=x3

    // 验证锚点
    eor     x12, x4, x0
    eor     x13, x5, x1
    eor     x14, x10, x2
    eor     x15, x11, x3
    add     x16, x12, x13
    add     x17, x16, x14
    add     x18, x17, x15

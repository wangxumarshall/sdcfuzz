// SPDX-License-Identifier: Apache-2.0
// l1_disambig.S — L1: 地址歧义与乱序访存 (Memory Disambiguation)
//
// 模板（plan L1，对应设计概念"LSU Store Buffer/Load Queue/地址歧义"）:
//   Store 地址依赖长延迟计算, Load 地址立即可用 → LSU 须推测判断是否冲突。
//   推测"不冲突"但实际冲突 → SDC。
//   安全构造: mul 计算小偏移 (延迟可用), store 地址 = base + 小偏移 (落在页内),
//   load 地址 = base。中间用 mul 制造地址"未知"窗口。
//   x6 = data1_base 全程保留不动。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1

    // 先在 data1 base 写入已知值
    str     x0, [x6]                  // [base] = 全1

    // 地址歧义: store 偏移用 mul (Complex 4-cyc 延迟), 地址"未知"
    mov     x2, #3
    mov     x3, #2
    mul     x4, x2, x3               // x4 = 6 (延迟可用的小偏移)
    add     x8, x6, x4               // store 地址 = base + 6 (页内安全)
    str     x1, [x8]                 // Store base+6 = 01 (地址歧义, 依赖 x8 计算)
    ldr     x9, [x6]                  // Load base (立即可用), 须等 store 地址确定
    // x4=6 与 base 不同 cache line(64B), 推测"不冲突"正确 → x9 应= 全1

    // 歧义场景2: store base+8, load base (同 16B/64B, 更易触发前递逻辑)
    add     x10, x6, #8
    str     x1, [x10]                // Store base+8 = 01
    ldr     x11, [x6]                 // Load base (同 cache line, 须等 store)
    // SDC 检测: x11 应= 全1 (若 store base+8 误前递到 base 则错)

    // 验证锚点
    eor     x12, x9, x0               // x9 vs 全1, 应=0
    eor     x13, x11, x0              // x11 vs 全1, 应=0
    add     x14, x12, x13

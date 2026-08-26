// SPDX-License-Identifier: Apache-2.0
// m1_tlb_thrash.S — M1: TLB Thrashing（TLB 颠簸）
//
// 模板（plan M1，对应设计概念"MMU TLB/PTW 盲区突破", 覆盖率 20%→60%+）:
//   访问不同 4KB 页面, 强制 TLB Miss, 高频激活 PTW 状态机 (4级遍历)。
//   每条 LDR 目标寄存器不同, 消除数据依赖, 让 OoO 并行发起多个 PTW。
//   约束: SnapMaker 默认 max_pages_to_add=5 (硬上限 20)。本模板访问 5 页,
//   每页跨步 4096, 仍能触发 TLB Miss + PTW 状态机 (dTLB 32-entry, 5 页足够 miss)。
//   x6 = data1_base。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 5 页 (步长 4096, 立即数偏移可用), 每条不同寄存器 (消除依赖, 并行 PTW)
    ldr     x0, [x6]                 // page 0 → TLB Miss → PTW 全4级遍历
    ldr     x1, [x6, #4096]          // page 1 → TLB Miss
    ldr     x2, [x6, #8192]          // page 2 → TLB Miss
    ldr     x3, [x6, #12288]         // page 3 → TLB Miss
    ldr     x4, [x6, #16384]         // page 4 → TLB Miss

    // Store 制造 Dirty (TLB + 写回路径)
    str     x0, [x6]
    str     x1, [x6, #4096]

    // 重新读 (TLB 部分命中 + 部分miss 混合, 压测替换逻辑)
    ldr     x5, [x6]
    ldr     x8, [x6, #4096]
    ldr     x9, [x6, #8192]

    // 验证锚点
    eor     x10, x5, x0              // 读回 vs 原值 (x0=读到的0), 应=0
    eor     x11, x8, x1              // 应=0
    eor     x12, x9, x2              // 应=0
    add     x13, x10, x11
    add     x14, x13, x12

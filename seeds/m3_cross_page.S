// SPDX-License-Identifier: Apache-2.0
// m3_cross_page.S — M3: 跨 4KB 页边界访存（MMU + LSU 联合压测）
//
// 模板（plan M3，对应设计概念"MMU 跨页 + TLB 双查询"）:
//   单条访存指令跨越 4KB 页边界 → MMU 最复杂路径: 一次访存需 2 次 TLB 查询
//   + 2 次权限检查 + 合并结果, 任何一步出错都是 SDC。
//   x6 = data1_base。跨页点在 page_base + 4088 (Load Pair 16B: 前8B在页N, 后8B在页N+1)。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // MUT: int
    LOAD_BYTE_ALT  x0           // 0x00FF00FF00FF00FF (字节交替, 最大化拼接)
    LOAD_ALL_ONES  x1
    LOAD_ALT_01    x2
    LOAD_ALT_10    x3

    // 跨 4KB 页边界 (offset=4088, 16B 访问 4088..4103, 跨页 4096)
    add     x8, x6, #4088       // x8 = data1_base + 4088 (页 N 末尾)
    stp     x0, x1, [x8]        // 跨页写入: 前8B在页N, 后8B在页N+1
    ldp     x4, x5, [x8]        // 跨页读回 (2次TLB查询+权限检查+合并)
    // SDC 检测: x4=x0, x5=x1

    // 不同跨界字节位置变异 (offset=4089..4095)
    add     x9, x6, #4090       // offset 4090, 16B 访问 4090..4105
    stp     x2, x3, [x9]
    ldp     x10, x11, [x9]

    // 跨页 128-bit 向量 (最大压力)
    fmov    d0, x0
    fmov    d1, x1
    add     x12, x6, #4088
    stur    q0, [x12]            // 128-bit 跨页 store (注: q0 高64位来自d1)
    ldur    q2, [x12]            // 128-bit 跨页 load (split + 2×TLB)
    // SDC 检测: q2 = q0

    // 验证锚点
    eor     x13, x4, x0          // x4(读回) vs x0(写入), 应=0
    eor     x14, x10, x2         // x10 vs x2, 应=0
    add     x15, x13, x14

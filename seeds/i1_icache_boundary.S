// SPDX-License-Identifier: Apache-2.0
// i1_icache_boundary.S — I1: 指令缓存边界压测
//
// 模板（plan I1，对应设计概念"IFU L1I 边界 + 分支预测/BTB 路径", 覆盖率66%→80%+）:
//   V110 L1I: 64KB, 4-way, 256 sets, 64B line。将关键指令精确放置到
//   64B Cache Line 边界, 触发 L1I 跨行取指逻辑。
//   配合 NOP 填充 (.balign 64 + 15×nop=60B), 使下一条指令跨 64B 边界。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 对齐到 64B Cache Line 边界
    .balign 64
    // 15 × 4B = 60B 的 NOP 填充, 使下一条指令的 bytes [60,63] 在 Line N
    NOP_FILL 15
    // 此时 PC = base + 60, 下一条 4B 指令跨越 64B 边界 (bytes 60-63 在 Line N,
    // 64B line 末尾)。用多条指令连续跨多个 line 边界加深压力
    add     x0, x1, x2              // 跨 64B 边界的关键指令
    add     x3, x4, x5
    // 再对齐 + 填充, 制造第二个跨边界点
    .balign 64
    NOP_FILL 15
    eor     x8, x0, x3               // 验证锚点 (跨第二个 64B 边界后, 避免覆盖 x6)
    madd    x9, x0, x3, x8

    // 第三个跨边界点
    .balign 64
    NOP_FILL 15
    add     x10, x8, x9
    eor     x11, x10, x0

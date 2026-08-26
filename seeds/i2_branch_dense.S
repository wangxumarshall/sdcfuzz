// SPDX-License-Identifier: Apache-2.0
// i2_branch_dense.S — I2: 分支密集场景
//
// 模板（plan I2，对应设计概念"IFU 分支密集 + BTB 溢出"）:
//   V110: 分支间隔 ≤16B 时 +1 cycle BPU 带宽惩罚。连续 20+ 短跳转
//   持续触发 BPU 密集分支处理逻辑, 配合 64-entry BTB 制造溢出。
//   实测: 前向 b 跳转有效, 退出序列按 PC 边界捕获。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1

    // 连续短跳转序列 (间隔 4B ≤16B → BPU 惩罚), 每跳转后少量计算
    b       .L1
.L1:
    b       .L2
.L2:
    b       .L3
.L3:
    b       .L4
.L4:
    b       .L5
.L5:
    b       .L6
.L6:
    b       .L7
.L7:
    b       .L8
.L8:
    b       .L9
.L9:
    b       .L10
.L10:
    b       .L11
.L11:
    b       .L12
.L12:
    b       .L13
.L13:
    b       .L14
.L14:
    b       .L15
.L15:
    b       .L16
.L16:
    b       .L17
.L17:
    b       .L18
.L18:
    b       .L19
.L19:
    b       .L20
.L20:
    // 20+ 跳转后, 验证锚点 (BPU 溢出压力下)
    add     x8, x0, x1               // 验证锚点 (避免覆盖 x6)
    madd    x9, x0, x1, x8
    eor     x10, x0, x1

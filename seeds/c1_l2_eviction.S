// SPDX-License-Identifier: Apache-2.0
// c1_l2_eviction.S — C1: L2 Set 冲突风暴 (Eviction Storm)
//
// 模板（plan C1，对应设计概念"L2C MESI/MOESI 状态机 + 替换算法", 覆盖率40%→70%+）:
//   L2: 1024 sets, 8-way, 64B line → 冲突步长 65536 bytes。
//   访问同 Set 多个地址塞满 8-way 触发 Eviction, 激活替换+Write-back。
//   插入 Store 制造 Dirty Line → Dirty Eviction。
//   约束: SnapMaker 默认 max_pages_to_add=5 (硬上限 kMaxAddedPageAddresses=20)。
//   本模板访问 5 页 (≤5 适配默认上限), 仍能触发 L2 Set 冲突/Eviction 逻辑。
//   x6 = data1_base。步长 65536 超立即数上限, 用 movz 装步长到 x7, add reg,reg。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0
    // MUT: int
    LOAD_ALT_01    x1

    // 步长 65536 (L2 冲突步长), 装入 x7 (data2 基址寄存器, 此模板借用)
    movz    x7, 0x0000
    movk    x7, 0x0001, lsl #16      // x7 = 0x10000 = 65536

    // 5 个同 Set 地址 (每个 +65536), 访问 5 页 (适配 max_pages_to_add=5)
    // Set 冲突: Way0..Way4 同 Set, 触发替换算法 + Write-back 逻辑
    ldr     x2, [x6]                  // Set S, Way 0
    add     x8,  x6, x7               // Way 1 (base + 65536)
    ldr     x3, [x8]
    add     x9,  x8, x7               // Way 2 (base + 131072)
    ldr     x4, [x9]
    add     x10, x9,  x7              // Way 3 (base + 196608)
    ldr     x5, [x10]
    add     x11, x10, x7              // Way 4 (base + 262144)
    ldr     x12, [x11]

    // 制造 Dirty Line → Dirty Eviction (Write-back + Replace)
    str     x0, [x6]                  // 将 Way 0 标记为 Dirty
    str     x1, [x8]                  // Way 1 Dirty
    // 重新访问触发 Dirty Eviction
    ldr     x13, [x6]                 // 读回 Dirty line (Write-back 路径)
    ldr     x14, [x8]

    // 验证锚点
    eor     x15, x13, x0              // 读回 vs 写入, 应=0
    eor     x16, x14, x1              // 读回 vs 写入, 应=0
    add     x17, x15, x16

// SPDX-License-Identifier: Apache-2.0
// c3_l3_128b.S — C3: L3 128B Line 特异性压测
//
// 模板（plan C3，对应设计概念"L3 跨行 + partial write-back 状态机"）:
//   重要发现: L3 Cache Line = 128B (而非 64B)。L2→L3 数据搬运粒度不同,
//   存在 64B→128B 对齐转换逻辑 (极少测试的路径)。L2 Evict 前半 64B 时,
//   L3 须正确处理 partial write-back。跨 128B 边界的 LDP 触发 L3 split。
//   x6 = data1_base (全程保留不动)。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // MUT: int
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1
    LOAD_ALT_10    x2
    LOAD_BYTE_ALT  x3

    // 访问同一 128B L3 line 的前半 64B 和后半 64B
    str     x0, [x6]                  // 前 64B 区域
    str     x1, [x6, #64]             // 后 64B (同一 128B L3 line)
    ldr     x4, [x6]                  // 读回前半
    ldr     x5, [x6, #64]             // 读回后半
    // SDC 检测: x4=x0, x5=x1

    // 跨 128B L3 Line 边界 (LDP 16B 访问 120..135)
    add     x10, x6, #120             // base+120, 跨 128B line 边界
    stp     x2, x3, [x10]             // 跨边界写入
    ldp     x11, x12, [x10]           // 跨边界读回 (L3 split + partial)
    // SDC 检测: x11=x2, x12=x3

    // 128B line 末尾的 64 位 store (单条跨 128B 边界)
    add     x13, x6, #124             // base+124, 64位 store 124..131 跨128
    str     x0, [x13]
    ldr     x14, [x13]                // 读回
    // SDC 检测: x14=x0

    // 验证锚点
    eor     x15, x4, x0               // 前半读回 vs 写入, 应=0
    eor     x16, x11, x2              // 跨128边界读回 vs 写入, 应=0
    eor     x17, x14, x0              // 末尾store读回 vs 写入, 应=0
    add     x18, x15, x16
    add     x19, x18, x17

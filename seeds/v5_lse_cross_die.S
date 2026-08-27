// SPDX-License-Identifier: Apache-2.0
// v5_lse_cross_die.S — V5/LSE: 多核一致性 LSE 原子指令跨 Die 缓存行乒乓
//
// 模板（plan V5 系统级 NUMA 维度深化 + 项9 多核一致性专项）:
//   利用 LSE 原子指令 (LDADD/CASAL/SWPAL) 对同一 cache line 高频原子操作,
//   在多核/跨 Die 环境制造缓存行乒乓, 专攻 HCCS 一致性状态机。
//   注: silifuzz runner 单线程执行, 此模板在单进程内高频原子操作,
//   压测 LSE 硬件单元 + cache line MESI 状态转换 (真多核由 orchestrator
//   多核并行触发跨核 invalidate 流量)。
//   x6 = data1_base (0x7'0000'0000)。
//   .arch armv8-a+lse (LSE 扩展, 实测非 banned, 通过过滤)。

    .include "asm_common.S.inc"
    .arch armv8-a+lse
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0           // 原子加值
    LOAD_ALT_01    x1           // CAS 期望值
    LOAD_ALT_10    x2           // CAS 新值

    // 阶段1: 高频 LDADD 原子加 (压 MESI 状态转换 + LSE 单元)
    // 对同一 cache line 多次原子加, 制造 invalidate 流量
    .rept 8
    ldadd  x0, x3, [x6]         // 原子加, 返回旧值
    .endr
    ldadda x0, x4, [x6]        // acquire 语义 (跨核内存序)
    ldaddl x0, x5, [x6]        // release 语义

    // 阶段2: CASAL 比较交换 (最严格的内存序, 跨核乒乓核心)
    // 反复 CAS 同一地址, 多核下产生最强一致性流量
    .rept 8
    casal  x1, x2, [x6]         // 比较 x1, 相等则写 x2, acquire
    .endr
    casa  x1, x2, [x6]         // 无 acquire 版本

    // 阶段3: SWPAL 交换 (写+读原子, 压 store buffer + LSE)
    // 用 x7 (data2 基址寄存器, 此模板借用) 作交换目标, 避免覆盖 x6 基址
    .rept 4
    swpal x0, x7, [x6]          // 交换, acquire
    .endr
    swp   x0, x8, [x6]

    // 阶段4: 跨 cache line 原子 (LDADD 到不同 offset, 触发跨 line 一致性)
    add   x10, x6, #64          // 跨 64B cache line
    ldadd x0, x11, [x10]
    casal x1, x2, [x10]

    // 验证锚点
    add   x12, x3, x4           // 汇总原子加返回值
    eor   x13, x11, x0          // CAS 后值校验
    add   x14, x12, x13

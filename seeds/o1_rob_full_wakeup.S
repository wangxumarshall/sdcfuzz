// SPDX-License-Identifier: Apache-2.0
// o1_rob_full_wakeup.S — O1: ROB + Scheduler 满载 + 唤醒风暴
//
// 模板（plan O1，对应设计概念"OoO ROB/Scheduler 满载唤醒 + di/dt", 覆盖率56%→72%+）:
//   用一条长延迟 Load 阻塞管线, 积压 30+ 条依赖指令到 scheduler(~33-entry)。
//   当数据返回时所有指令"同时唤醒" → 瞬间极高 di/dt, 时序裕量最小
//   → SDC 最易发生窗口。穿插 flag-setting 耗尽 flag rename(~31)。
//   x6 = data1_base (Load 来源, 数据页初值0, 但延迟由数据依赖链制造)。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 阶段1: 发起一条 Load (作为"长延迟"数据源, x6 数据页)
    ldr     x0, [x6]                  // x0 = [base] (后续 30+ 条依赖 x0)

    // 阶段2: 30+ 条依赖 x0 的指令 (积压 scheduler)
    add     x1, x0, #1
    add     x2, x0, #2
    eor     x3, x0, x1
    add     x4, x0, #4
    sub     x5, x0, x1
    and     x8, x0, x2
    orr     x9, x0, x3
    add     x10, x0, x1
    eor     x11, x0, x2
    add     x12, x0, x3
    sub     x13, x0, x4
    and     x14, x0, x1
    orr     x15, x0, x2
    add     x16, x0, x3
    eor     x17, x0, x4
    add     x18, x0, x5
    sub     x19, x0, x8
    and     x20, x0, x9
    orr     x21, x0, x10
    add     x22, x0, x11
    eor     x23, x0, x12
    add     x24, x0, x13
    sub     x25, x0, x14
    and     x26, x0, x15

    // 阶段3: 穿插 flag-setting 耗尽 flag rename (~31 entries)
    adds    x1, x0, x4
    subs    x2, x0, x5
    adds    x3, x0, x8
    subs    x4, x0, x9
    adds    x5, x0, x10
    subs    x8, x0, x11
    adds    x9, x0, x12

    // 数据返回时: 所有 30+ 条 + flag 计算同时唤醒 → 极高 di/dt
    // 验证锚点 (在唤醒风暴后执行)
    add     x27, x1, x2
    madd    x28, x3, x4, x27

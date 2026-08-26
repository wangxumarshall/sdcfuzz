// SPDX-License-Identifier: Apache-2.0
// v3_prf_mispredict.S — V3: PRF 耗尽 + 分支误预测回滚
//
// 攻击向量（plan V3，对应设计概念"误预测回滚 / PRF 耗尽"）:
//   V110 PRF-based rename + Move Elimination + ~31 flag rename。耗尽 PRF 映射表
//   后触发分支误预测，CPU 回滚 squash 的推测指令并恢复 PRF 映射表到检查点。
//   回滚路径是重命名逻辑最复杂的状态机，SDC 缺陷最易藏匿处。
//
// 实测验证（2026/08/26）: b.eq 分支种子有效，退出序列按 PC 边界捕获，
//   故可原样保留分支语义。执行须在代码地址范围内终结。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 阶段1: 写入所有 31 个通用寄存器, 耗尽整数 PRF 映射
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1
    LOAD_ALT_10    x2
    LOAD_CARRY32   x3
    LOAD_MAX_POS   x4
    mov     x5,  x0
    mov     x6,  x1
    mov     x7,  x2
    mov     x8,  x3
    mov     x9,  x4
    mov     x10, x0
    mov     x11, x1
    mov     x12, x2
    mov     x13, x3
    mov     x14, x4
    mov     x15, x0
    mov     x16, x1
    mov     x17, x2
    mov     x18, x3
    mov     x19, x4
    mov     x20, x0
    mov     x21, x1
    mov     x22, x2
    mov     x23, x3
    mov     x24, x4
    mov     x25, x0
    mov     x26, x1
    mov     x27, x2
    mov     x28, x3
    // x29/x30 不动 (FP/LR), 避免破坏栈帧与退出序列

    // 阶段2: 写入向量寄存器, 耗尽向量 PRF 映射
    fmov    d0,  x0
    fmov    d1,  x1
    fmov    d2,  x2
    fmov    d3,  x3
    fmov    d4,  x4
    fmov    d5,  x0
    fmov    d6,  x1
    fmov    d7,  x2

    // 阶段3: Flag-setting 指令, 耗尽 Flag Rename (~31 entries)
    adds    x0,  x1,  x2       // 写 NZCV flags
    subs    x3,  x4,  x5      // 写 NZCV flags
    adds    x6,  x7,  x8
    subs    x9,  x10, x11
    adds    x12, x13, x14
    subs    x15, x16, x17

    // 阶段4: 制造分支误预测 (数据依赖条件分支, BPU 首见必误预测)
    // cmp 结果取决于前面运算的值; BPU 预测 taken 但实际 not-taken (或反之)
    // CPU 必须回滚所有推测执行的 PRF 分配
    cmp     x0, x3
    b.eq    .Ltaken_path

    // 非跳转路径 (验证锚点, PRF 映射表刚被回滚恢复 → SDC 最易发生窗口)
    add     x9,  x1, x2
    madd    x10, x4, x5, x6
    // fall through 到退出序列

.Ltaken_path:
    add     x11, x7, x8       // 跳转路径也有验证锚点
    add     x12, x9, x10

// SPDX-License-Identifier: Apache-2.0
// v2_alu_complex_saturation.S — V2: 整数乘法器饱和 + ALU 端口竞争
//
// 攻击向量（plan V2，对应设计概念"IEX 防下限 + 进位链压力"）:
//   V110 后端 3×Simple ALU + 1×Complex(mul/div,4-cyc)。用大量无依赖 MUL/MADD
//   填满 Complex 端口 + 3 ALU 满载，调度器(~33-entry)背压致 ROB 近满，
//   任何时序扰动可能导致 retire 读错 PRF 条目 → SDC。
//
// 操作数空间压力（weak 因素②老化）: 操作数字典全谱——全1/交替01/交替10/
//   进位边界/最大正，不同操作数激活 ALU/乘法器内部不同 Gate 子集，最大化翻转率。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    // 操作数构造 (字典全谱)
    LOAD_ALL_ONES  x10
    LOAD_ALT_01    x11
    LOAD_ALT_10    x12
    LOAD_CARRY32   x13
    LOAD_MAX_POS   x14

    // 4-wide 发射: 3 条 ALU + 1 条 MUL, 同时进入后端, 消除依赖
    add     x0,  x10, x11       // ALU port 0 (全1+01 → 进位)
    eor     x1,  x12, x13       // ALU port 1 (10^carry32 → 翻转)
    orr     x2,  x14, x10       // ALU port 2 (maxpos|全1)
    mul     x3,  x10, x11       // Complex port (4-cyc, 全1×01)

    add     x4,  x11, x12       // ALU port 0
    sub     x5,  x12, x13       // ALU port 1
    and     x6,  x13, x14       // ALU port 2
    madd    x7,  x14, x10, x11  // Complex port (4-cyc)

    add     x8,  x10, x12       // ALU port 0
    eor     x9,  x11, x13       // ALU port 1
    orn     x0,  x14, x12       // ALU port 2
    msub    x1,  x10, x11, x12  // Complex port (4-cyc)

    // 再两轮, 让调度器队列积压到接近 33-entry 极限
    add     x2,  x13, x14
    bic     x3,  x10, x11
    adds    x4,  x12, x13       // 设置 flags (消耗 flag rename ~31 entries)
    smull   x5,  w6,  w7        // Complex port, 64-bit 结果 (注: w6/w7=0, 结果0, 但走 Complex 路径)
    // 用已构造的非零源重做 smull 以走真实乘法器路径:
    smull   x5,  w10, w11       // 32×32→64 有符号 (全1×01)

    add     x6,  x14, x10
    eor     x7,  x11, x12
    subs    x8,  x13, x14       // 又一个 flag-setting (进一步消耗 flag rename)
    umull   x9,  w10, w11       // Complex port (全1×01 无符号)

    // 验证锚点 (调度器/ROB 满载压力下执行)
    add     x10, x11, x12
    madd    x11, x13, x14, x10

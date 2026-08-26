// SPDX-License-Identifier: Apache-2.0
// v6_crypto_toggle.S — V6: 密码学硬核启停时序冲击
//
// 攻击向量（plan V6，对应设计概念"独立供电域启停时序"）:
//   鲲鹏920 原生 AES/SHA1/SHA2/CRC32 硬件指令 (cpuinfo 实测确认)。
//   快速交替激活/休眠专用硬件单元, 独立供电域与主核心供电域电压耦合
//   产生时序干扰, SDC 易在切换窗口发生。
//
// 操作数: 向量寄存器注入全 1/交替位 (最大化 AES/SHA 内部翻转)。

    .include "asm_common.S.inc"
    .arch armv8-a+crypto+crc
    .text
    .globl _start
_start:
    // 构造向量操作数 (全 1 + 交替, 用于 AES/SHA 内部)
    LOAD_ALL_ONES  x0
    fmov    d0, x0
    dup     v0.16b, v0.b[0]    // v0 = 全 0xFF ×16
    LOAD_ALT_01    x1
    fmov    d1, x1
    dup     v1.16b, v1.b[0]    // v1 = 0x55 ×16
    LOAD_ALT_10    x2
    fmov    d2, x2
    dup     v2.16b, v2.b[0]    // v2 = 0xAA ×16

    // ---- 密码学硬核激活 (第1轮) ----
    aese    v0.16b, v1.16b     // AES 加密单轮
    aesmc   v0.16b, v0.16b     // AES Mix Columns
    sha256h q3, q4, v2.4s      // SHA-256 Hash (q3/q4 初值0, 输入v2)
    crc32cx w5, w6, x0         // CRC32C (w6=0 初值, x0 数据)

    // ---- 立即切换到纯整数 (密码学硬核休眠) ----
    add     x10, x1, x2
    mul     x11, x1, x2
    eor     x12, x0, x1
    sub     x13, x2, x0

    // ---- 再次激活密码学硬核 (第2轮) ----
    aese    v3.16b, v4.16b     // v3/v4 用全1 复制
    aesmc   v3.16b, v3.16b
    sha256h q5, q6, v0.4s
    crc32cw w14, w15, w2       // w15=0, 数据=w2(32位)

    // ---- 再次休眠, 验证锚点 ----
    add     x16, x17, x18      // 验证锚点 (x17/x18=0 初值)
    madd    x19, x20, x21, x22 // 验证锚点 (走 Complex 端口)

    // 第3-4轮 (重复模式加深启停冲击)
    aese    v5.16b, v6.16b
    aesmc   v5.16b, v5.16b
    sha1c   q7, s8, v0.4s      // SHA-1 (s8 标量)
    crc32cx w23, w24, x0

    add     x25, x26, x27
    eor     x28, x0, x1

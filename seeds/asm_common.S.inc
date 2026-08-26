// SPDX-License-Identifier: Apache-2.0
// asm_common.S.inc — SDC 检测用例公共汇编宏
//
// 设计概念落地：操作数空间变异的工程化载体。这些宏把"构造一个 64-bit
// 极端操作数"从多条 movz/movk 序列封装成单行调用，使各模板可被操作数
// 变异引擎 (operand_mutator.py) 系统性展开为笛卡尔积变体。
//
// AArch64 调用约定提示（snap_tool --raw 注入的初值）：
//   x6  = data1_range.base (0x7'0000'0000, 4MB, 初值全 0)
//   x7  = data2_range.base (0x1007'0000'0000, 4MB, 初值全 0)
//   sp  = 0x200'1000 (栈顶)
//   其余寄存器 = 0；代码放 code_range，退出序列由 snap_tool 自动追加。
// 寻址约束：stp/ldp 仅 [Xn,#imm(8倍数)] 或 [Xn]，不接受 [Xn,Xm]。
//           跨边界访问须先 add 计算非对齐地址到寄存器，再 [reg]。

    .macro MOVK_ALL  rd, hi16, lo16
        // 构造 64-bit 常量 = (hi16 << 32) | lo16  （hi16/lo16 各 16 位）
        // 等价: rd = (hi16:hi16 << 32) | (lo16:lo16)？不——这里 hi16/lo16
        //   分别代表高 32 位和低 32 位的同一 16-bit 模式（用于 0xFFFF.../0x5555.../0xAAAA...）。
        // 对于需要异高低半的值，用 LOAD_IMM64 显式给 4 个 16-bit 段。
        movz    \rd, #\lo16, lsl #0
        movk    \rd, #\lo16, lsl #16
        movk    \rd, #\hi16, lsl #32
        movk    \rd, #\hi16, lsl #48
    .endm

    .macro LOAD_IMM64 rd, s0, s1, s2, s3
        // 构造任意 64-bit 立即数，4 个 16-bit 段 s0(lsl0)..s3(lsl48)
        movz    \rd, #\s0, lsl #0
        movk    \rd, #\s1, lsl #16
        movk    \rd, #\s2, lsl #32
        movk    \rd, #\s3, lsl #48
    .endm

    // 便捷别名 —— 整数种子表里的高频值
    .macro LOAD_ALL_ONES    rd
        MOVK_ALL \rd, 0xFFFF, 0xFFFF           // 0xFFFFFFFFFFFFFFFF
    .endm
    .macro LOAD_ALT_01      rd
        MOVK_ALL \rd, 0x5555, 0x5555           // 0x5555555555555555
    .endm
    .macro LOAD_ALT_10      rd
        MOVK_ALL \rd, 0xAAAA, 0xAAAA           // 0xAAAAAAAAAAAAAAAA
    .endm
    .macro LOAD_BYTE_ALT    rd
        MOVK_ALL \rd, 0x00FF, 0x00FF           // 0x00FF00FF00FF00FF
    .endm
    .macro LOAD_HALF_ALT    rd
        MOVK_ALL \rd, 0xFFFF, 0x0000           // 0x0000FFFF0000FFFF (半字游走)
    .endm
    .macro LOAD_CARRY32     rd
        MOVK_ALL \rd, 0x0000, 0xFFFF           // 0x00000000FFFFFFFF (32 位进位边界)
    .endm
    .macro LOAD_CARRY48     rd
        LOAD_IMM64 \rd, 0xFFFF, 0xFFFF, 0xFFFF, 0x0000  // 0x0000FFFFFFFFFFFF
    .endm
    .macro LOAD_MAX_POS     rd
        MOVK_ALL \rd, 0x7FFF, 0xFFFF           // 0x7FFFFFFFFFFFFFFF (最大正)
    .endm
    .macro LOAD_MIN_NEG     rd
        LOAD_IMM64 \rd, 0x0000, 0x0000, 0x0000, 0x8000  // 0x8000000000000000 (最小负)
    .endm

    // FSU 种子：通过整数寄存器搬入浮点/SIMD 寄存器（数据页初值 0，须代码内构造）
    .macro LOAD_SUBNORMAL_MIN  xd, xt
        mov     \xt, #1                          // 0x0000000000000001 (最小正 subnormal)
        fmov    \xd, \xt
    .endm
    .macro LOAD_QNAN          xd, xt
        LOAD_IMM64 \xt, 0x0000, 0x0000, 0x7FF8, 0x0000  // 0x7FF8000000000000 Quiet NaN
        fmov    \xd, \xt
    .endm
    .macro LOAD_POS_INF       xd, xt
        LOAD_IMM64 \xt, 0x0000, 0x0000, 0x7FF0, 0x0000  // +Inf
        fmov    \xd, \xt
    .endm
    .macro LOAD_NEG_ZERO      xd, xt
        LOAD_IMM64 \xt, 0x0000, 0x0000, 0x0000, 0x8000  // -0.0
        fmov    \xd, \xt
    .endm
    .macro LOAD_MAX_FINITE    xd, xt
        LOAD_IMM64 \xt, 0xFFFF, 0xFFFF, 0xFEFF, 0x7FEF  // 0x7FEFFFFFFFFFFFFF 最大有限
        fmov    \xd, \xt
    .endm

    // 对齐填充：把关键指令精确放置到 Cache Line 边界 (IFU 模板用)
    .macro NOP_FILL  count
        .rept \count
        nop
        .endr
    .endm

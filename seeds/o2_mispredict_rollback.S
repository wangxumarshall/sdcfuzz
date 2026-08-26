// SPDX-License-Identifier: Apache-2.0
// o2_mispredict_rollback.S — O2: 分支预测欺骗 + PRF 回滚
//
// 模板（plan O2，对应设计概念"分支误预测欺骗诱导全管线 Flush + PRF 回滚"）:
//   训练 BPU 预测跳转, 最后时刻篡改条件使其不跳转, 诱导误预测。
//   CPU 在错误路径推测执行的 PRF 分配须回滚 → 重命名逻辑最复杂状态机。
//   回滚后验证锚点是 SDC 检测关键。
//   实测: b.ne 循环 + 条件分支有效, 退出序列按 PC 边界捕获。

    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    LOAD_ALL_ONES  x0
    LOAD_ALT_01    x1

    // 阶段1: 训练循环 (让 BPU 学到 "这个分支总是 taken")
    // 用计数器循环 N 次, BPU 学到 b.ne 总跳转
    mov     x2, #20                  // 循环 20 次 (足够训练 BPU)
.Ltrain_loop:
    subs    x2, x2, #1               // x2 递减, 设 Z flag
    b.ne    .Ltrain_loop             // 循环: BPU 学到总是跳转

    // 阶段2: 最后一次 x2=0, subs 设 Z=1, b.ne 不跳转
    // 但 BPU 仍预测 taken → 误预测 → 错误路径推测指令须回滚
    // 在错误路径上放置高功耗指令 (回滚时 PRF 映射被撤销)
    // 注: 这些指令在 not-taken 路径, 不实际执行, 但被推测执行后回滚
    add     x3, x0, x1               // 错误路径推测指令
    madd    x4, x0, x1, x3
    eor     x5, x0, x1

    // 回滚完成后, 从这里继续 (验证锚点: PRF 映射表刚被回滚恢复)
    // SDC 最易发生窗口 (避免覆盖 x6 基址)
    add     x8, x0, x1               // 验证锚点1 (PRF 回滚后)
    madd    x9, x0, x1, x8           // 验证锚点2 (Complex 端口)
    eor     x10, x0, x1              // 验证锚点3

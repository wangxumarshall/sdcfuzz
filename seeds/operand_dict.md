# SDC 操作数变异字典 (Operand Mutation Dictionary)

> 设计概念落地：从"指令集空间"转向"操作数/执行上下文空间"。本字典为操作数空间变异引擎 (`tools/sdc_mutator/operand_mutator.py`) 提供硬核种子，对每条关键指令做操作数维度的深度变异，把覆盖率空间从"指令种类"扩展到"操作数组合"。

## 一、整数操作数种子 (IEX/ALU)

| 种子类别 | 值 (64-bit) | movz/movk 编码 | 电路级目标 |
|---------|-------------|----------------|-----------|
| 全零 | `0x0000000000000000` | — (寄存器初值即为0) | 零路径（大量 Gate 不翻转，测试静态漏电 SDC） |
| 全一 | `0xFFFFFFFFFFFFFFFF` | movz#0xFFFF; movk×3 | 全进位链、全输出翻转 |
| 交替 01 | `0x5555555555555555` | movz#0x5555; movk×3 | **50% 翻转率**，最大化动态功耗 |
| 交替 10 | `0xAAAAAAAAAAAAAAAA` | movz#0xAAAA; movk×3 | 与 01 交替使用，**100% bit-toggle** |
| 单比特游走 | `0x1, 0x2, 0x4, ..., 0x8000000000000000` | movz#(1<<n) | 逐一测试每个 bit 位的进位路径 |
| 进位边界(32) | `0x00000000FFFFFFFF` | movz#0xFFFF; movk#0xFFFF,lsl#16 | 32→64 位进位传播边界 |
| 进位边界(48) | `0x0000FFFFFFFFFFFF` | movz#0xFFFF; movk×2 | 48 位进位链 |
| 字节交替 | `0x00FF00FF00FF00FF` | movz#0x00FF; movk×3 | 字节拼接逻辑（LSU forwarding 关键路径） |
| 半字游走 | `0x0000FFFF0000FFFF` | movz#0xFFFF; movk#0xFFFF,lsl#32 | 16-bit 运算单元边界 |
| 最大正 | `0x7FFFFFFFFFFFFFFF` | movz#0x7FFF; movk×3 | 有符号最大正数 |
| 最大正+1 | `0x7FFFFFFFFFFFFFFF` + 1 | — (配合 `adds` 检测溢出) | **有符号溢出**（NZCV flags 生成逻辑） |
| 最小负 | `0x8000000000000000` | movz#0x0000; movk#0x8000,lsl#48 | 符号位翻转测试 |
| 乘法极端 | `0xFFFFFFFF × 0xFFFFFFFF` | — (两个全一) | **乘法器最长延迟路径**（4-cycle Complex） |

## 二、浮点/SIMD 操作数种子 (FSU)

| 种子类别 | 值 (FP64) | 构造方式 | 电路级目标 |
|---------|-----------|----------|-----------|
| 正常数 1.0 | `0x3FF0000000000000` | `fmov d,#1.0` | 基线路径 |
| 正常数 2.0 | `0x4000000000000000` | `fmov d,#2.0` | 基线路径 |
| **Subnormal 最小正** | `0x0000000000000001` | `mov x,#1; fmov d,x` | **FSU 微码/慢路径**（极低覆盖盲区） |
| Subnormal 居中 | `0x0008000000000000` | `movz x; fmov d,x` | Subnormal 中段路径 |
| Quiet NaN | `0x7FF8000000000000` | `movz/movk x; fmov d,x` | NaN 传播逻辑 |
| Signaling NaN | `0x7FF0000000000001` | `movz/movk x; fmov d,x` | 异常陷阱路径 |
| +Infinity | `0x7FF0000000000000` | `fmov/mov` | 无穷大运算逻辑 |
| -Infinity | `0xFFF0000000000000` | `fmov/mov` | 负无穷 |
| 最大有限 | `0x7FEFFFFFFFFFFFFF` | `movz/movk×3; fmov d,x` | 接近溢出边界 |
| +0.0 | `0x0000000000000000` | `fmov d,#0.0` | 符号位 0 |
| -0.0 | `0x8000000000000000` | `movz/movk; fmov d,x` | **符号位处理**（IEEE 754 特殊规则） |
| FP16 max | `0x7BFF` (半精度位宽) | `fmov h,#...` | FP16 扩展路径（`fphp`） |
| FP16 min normal | `0x0400` | `fmov h,#...` | FP16 最小规格化 |

## 三、地址操作数种子 (LSU/MMU)

> 寻址约束（实测）：`stp/ldp` 只接受 `[Xn,#imm]`(imm 为 8 倍数) 或 `[Xn]`，**不接受** `[Xn,Xm]`。跨边界须先 `add x_addr, x6, #offset` 计算非对齐地址到寄存器，再 `stp/ldp ..., [x_addr]`。`ldr/str` 单寄存器形式可接受 `[Xn,Xm]`。

| 种子类别 | 地址偏移 (相对 x6=data1_base) | 构造方式 | 电路级目标 |
|---------|------------------------------|----------|-----------|
| 对齐访问 | offset = 0, 16, 32, 48 | `ldp x,[x6,#imm]` | 基线路径 |
| **跨 16B 边界** | offset = 14, 30, 46, 62 | `add x8,x6,#14; ldp x,[x8]` | **LSU split-access**（V110 +1-2cyc） |
| **跨 64B Cache Line** | offset = 60 | `add x8,x6,#60; stp/ldp [x8]` | **L1D/L2 跨行逻辑** |
| **跨 128B L3 Line** | offset = 124 | `add x8,x6,#124; ldp [x8]` | **L3 跨行**（实测 L3 line=128B） |
| **跨 4KB 页边界** | offset = 4088/4090 | `add x8,x6,#4088; ldp x,[x8]` | **MMU 跨页 + TLB 双查询** |
| L1D Set 冲突步长 | stride = 16384 (64B×256) | `add x8,x6,#16384; ldr [x8]` | **L1D 替换算法** |
| L2 Set 冲突步长 | stride = 65536 (64B×1024) | `add x8,x6,#65536; ldr [x8]` | **L2 替换算法** |
| L3 Set 冲突步长 | stride = 262144 (128B×2048) | `add x8,x6,#262144; ldr [x8]` | **L3 替换算法** |

## 四、操作数组合矩阵原则

对于每条关键指令，遍历操作数的笛卡尔积而非单次执行：

```
以 ADD x0, x1, x2 为例:
x1 ∈ 整数种子表 (10+ 种)  ×  x2 ∈ 整数种子表 (10+ 种)  =  100+ 组合
传统 STL: ADD 1 次 (覆盖率 +1 条指令)
操作数空间 STL: ADD 100 次 (覆盖率 +数百个 Gate 子集)
```

变异引擎对每个模板的"可变异操作数槽"做笛卡尔积替换，生成 N 个变体 `.S`，编译为 `.bin`。

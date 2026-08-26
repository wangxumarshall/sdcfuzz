# 鲲鹏 920 (TaiShan V110) SDC 高效检测用例生成方案

> **目标**：在华为鲲鹏 920 处理器（Implementer 0x48, Part 0xd01, TaiShan V110 微架构）上，基于 Silifuzz + Centipede 框架，系统性地挖掘出能够高概率触发 **SDC（静默数据损坏）** 的机器码用例。

> **设计原则**：每一条策略均直接来源于 TaiShan V110 的已知微架构参数（流水线宽度、执行端口数量、延迟周期、缓存层级、调度器深度），拒绝空泛臆测。

---

## 第一部分：SDC 的物理根因与 TaiShan V110 的攻击面

### 1.1 SDC 的物理本质

SDC（Silent Data Corruption）指的是 CPU 在执行指令时产生了**错误的计算结果**，但该错误**未被任何硬件校验机制（ECC、Parity、Machine Check）捕获**，因此静默地传播到了软件层面。

SDC 的物理根因可归结为以下三类：

| 根因类别 | 物理机制 | 在 TaiShan V110 中的暴露点 |
|---------|---------|--------------------------|
| **瞬态电压骤降 (Voltage Droop / di/dt)** | CPU 功能单元瞬间从低功耗切换到满载，导致供电网络（PDN）的电感效应来不及响应，核心电压瞬间跌落至时序裕量（Timing Margin）以下，锁存器（Latch）采样到错误值 | 双 FSU 端口（128-bit NEON FMA）从空闲到满载的瞬态切换；7nm 工艺下阈值电压更低，时序裕量更薄 |
| **乱序执行状态机缺陷 (OoO Logic Bug)** | 重排序缓冲区（ROB）、物理寄存器堆（PRF）、调度器（Scheduler）在极端组合条件下的硬件设计缺陷，如寄存器重命名映射表在分支误预测回滚时的竞态条件 | PRF-based 重命名 + ~33-entry 调度器 + ~31-entry Flag Rename + Move Elimination 的交互；4-wide 发射 + 3 ALU + 1 Complex 端口的调度竞争 |
| **缓存一致性协议竞态 (Coherence Race)** | 多核/多 Die 环境下，Snoop 协议状态机在极端并发下的时序竞态，导致脏数据（Dirty Data）未能正确传播 | 3-DIE Chiplet + Bufferless 双环 NoC + HCCS Hydra 协议；L3 Partition 模式下 HHA（Home Agent）的动态分配逻辑 |

### 1.2 TaiShan V110 微架构攻击面地图

基于你提供的全景参数，以下是 **6 个精确攻击面**，每一个都对应 V110 流水线中的一个特定弱点：

```
┌─────────────────────────────────────────────────────────────┐
│                    TaiShan V110 核心                         │
│                                                             │
│  ┌──────────┐  ┌──────────────────────────────────────────┐ │
│  │ 前端 4-wide│  │ 后端执行引擎                              │ │
│  │          │  │                                          │ │
│  │ L1I 64KB │  │ ┌─────────┐ ┌─────────┐ ┌─────────────┐ │ │
│  │ 4-way    │  │ │ ALU×3   │ │ Complex │ │ FSU×2       │ │ │
│  │          │  │ │ (simple)│ │ (mul/div│ │ (128b NEON) │ │ │
│  │ BPU:     │  │ │         │ │ 4-cyc)  │ │ FMA 7-cyc   │ │ │
│  │ 64-BTB   │  │ └────┬────┘ └────┬────┘ └──────┬──────┘ │ │
│  │ 31-RAS   │  │      │          │              │        │ │
│  └─────┬────┘  │ ┌────┴──────────┴──────────────┴──────┐ │ │
│        │       │ │     Scheduler (~33 entries each)     │ │ │
│        │       │ │     PRF-based Rename                 │ │ │
│        │       │ │     Flag Rename ~31 entries          │ │ │
│        │       │ │     Move Elimination                 │ │ │
│        │       │ └──────────────────┬───────────────────┘ │ │
│        │       │ ┌──────────────────┴───────────────────┐ │ │
│        │       │ │ LSU: 2×AGU, L1D 64KB 4-way          │ │ │
│        │       │ │ Load-to-use 4-cyc, StFwd 6-7 cyc    │ │ │
│        │       │ │ Cross-16B penalty +1-2 cyc           │ │ │
│        │       │ └─────────────────────────────────────┘ │ │
│        │       └──────────────────────────────────────────┘ │
│        │                                                     │
│  ┌─────┴──────────────────────────────────────────────────┐ │
│  │ L2: 512KB private, 10-cyc │ L3: 32MB/Die, 36-cyc part │ │
│  └────────────────────────────┴───────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │ Bufferless双环NoC (<15ns intra-die)  │
         ├─────────── Die 间 HCCS ──────────────┤
         │ Hydra协议, 400GB/s, 跨Die >36-cyc    │
```

**攻击向量编号及其对应的微架构弱点：**

| 编号 | 攻击向量 | 利用的微架构参数 |
|------|---------|---------------|
| **V1** | FSU 功耗振荡器 (Vdroop) | 双 FSU×128-bit, FMA 7-cyc, 从 NOP 到满载的 di/dt |
| **V2** | 整数乘法器饱和 + ALU 竞争 | 仅 1 个 Complex 端口 (mul/div 4-cyc) vs 3 个 simple ALU |
| **V3** | PRF 耗尽 + 误预测回滚 | PRF-based rename, ~33-entry scheduler, 31-entry flag rename |
| **V4** | LSU 跨边界访存压榨 | 2×AGU, cross-16B +1-2 cyc penalty, StFwd 6-7 cyc |
| **V5** | L3 Partition + 跨 Cluster 一致性 | 4 NUMA nodes (距离 10/12/20/22/24), Bufferless NoC |
| **V6** | 密码学硬核启停时序冲击 | AES/SHA/CRC32 硬件单元的独立供电域频繁激活/休眠 |

---

## 第二部分：6 个攻击向量的详细设计与可执行汇编代码

### V1：FSU 功耗振荡器 (Vdroop Oscillator)

**原理**：TaiShan V110 的双 FSU 流水线支持 2 端口的 128-bit FP32 FMA（`FMLA v.4s`），单条 FMLA 延迟为 7 周期。当双 FSU 同时满载时，瞬态电流（di/dt）远超标量整数运算。如果在极短时间内反复进行"完全空闲 → 双FSU满载 → 完全空闲"的切换，供电网络的电感效应会导致核心电压产生阻尼振荡（Voltage Ringing），在振荡谷底处时序裕量最小，SDC 概率最高。

**关键参数依据**：
- 双 FSU 端口, 128-bit NEON, FP32 FMA 7-cycle latency
- FADD 4-cycle, FMADD 整体 7-cycle
- 4-wide 前端每周期最多发射 4 条指令

**汇编种子代码** (`v1_vdroop_oscillator.S`)：

```asm
// === V1: FSU Vdroop Oscillator ===
// 策略: NOP窗口(低功耗) -> FMLA爆发(高功耗) -> NOP窗口, 循环
// 所有FMLA无数据依赖, 可同时发射到2个FSU端口

// ---- 低功耗窗口 (让电压恢复到标称值) ----
nop
nop
nop
nop
nop
nop
nop
nop

// ---- 高功耗爆发 (双FSU满载, 无依赖链, 4-wide可连续发射) ----
// 每对相邻FMLA使用不同寄存器, 消除WAW/RAW依赖
// V110双FSU可同时执行2条128-bit FMA
fmla v0.4s, v16.4s, v17.4s    // FSU port 0
fmla v1.4s, v18.4s, v19.4s    // FSU port 1
fmla v2.4s, v20.4s, v21.4s    // FSU port 0 (下一周期)
fmla v3.4s, v22.4s, v23.4s    // FSU port 1 (下一周期)
fmla v4.4s, v24.4s, v25.4s
fmla v5.4s, v26.4s, v27.4s
fmla v6.4s, v28.4s, v29.4s
fmla v7.4s, v30.4s, v31.4s
fmla v8.4s, v16.4s, v17.4s
fmla v9.4s, v18.4s, v19.4s
fmla v10.4s, v20.4s, v21.4s
fmla v11.4s, v22.4s, v23.4s
fmla v12.4s, v24.4s, v25.4s
fmla v13.4s, v26.4s, v27.4s
fmla v14.4s, v28.4s, v29.4s
fmla v15.4s, v30.4s, v31.4s

// ---- 低功耗窗口 (电压跌落的尾巴, SDC最易发生处) ----
// 在此处插入"验证指令": 简单加法, 其结果作为SDC检测锚点
add x0, x1, x2          // 验证点: 此时核心电压可能仍在振荡谷底
eor x3, x4, x5          // 验证点: 位运算对时序更敏感
madd x6, x7, x8, x9     // 验证点: 整数乘加, 走Complex端口(4-cyc)

nop
nop
nop
nop
```

**SDC 检测逻辑**：Silifuzz 在 `simple_fix_tool` 阶段会在真机上执行上述代码，记录 `x0`, `x3`, `x6` 等寄存器的终态值。后续 `reading_runner` 每次重复执行时，如果这些寄存器值与首次记录的不同，即为 SDC。NOP 窗口后的"验证指令"正好落在电压振荡的谷底窗口期，是 SDC 最易发生的位置。

---

### V2：整数乘法器饱和 + ALU 端口竞争

**原理**：V110 后端只有 **1 个 Complex 端口**（处理乘法/除法，4-cycle latency），而有 **3 个 Simple ALU 端口**。如果用大量无依赖的 `MUL`/`MADD` 填满 Complex 端口，同时让 3 个 ALU 也满载，调度器（~33 entries）将面临极端的资源竞争。当调度器满载时，背压（back-pressure）会导致前端停顿（stall），此时 ROB 接近满载，任何微小的时序扰动都可能导致指令提交（retire）时读取到错误的 PRF 条目。

**关键参数依据**：
- 3× Simple ALU + 1× Complex (mul/div, 4-cycle)
- 每个 Scheduler ~33 entries
- 4-wide 发射

**汇编种子代码** (`v2_alu_saturation.S`)：

```asm
// === V2: ALU + Complex Port Saturation ===
// 策略: 同时打满 3 个 ALU 和 1 个 Complex 端口
// 使用不同目标寄存器消除依赖, 让调度器(33-entry)和ROB达到最大占用

// 4-wide发射: 3条ALU + 1条MUL, 同时进入后端
add  x0,  x10, x11       // ALU port 0
eor  x1,  x12, x13       // ALU port 1
orr  x2,  x14, x15       // ALU port 2
mul  x3,  x16, x17       // Complex port (4-cycle latency)

add  x4,  x18, x19       // ALU port 0
sub  x5,  x20, x21       // ALU port 1
and  x6,  x22, x23       // ALU port 2
madd x7,  x24, x25, x26  // Complex port (4-cycle)

add  x8,  x27, x28       // ALU port 0
eor  x9,  x29, x30       // ALU port 1
orn  x10, x11, x12       // ALU port 2
msub x13, x14, x15, x16  // Complex port (4-cycle)

// 再来一轮, 让调度器队列积压到接近33-entry极限
add  x17, x18, x19
bic  x20, x21, x22
adds x23, x24, x25       // 设置flags (消耗flag rename条目, ~31 entries)
smull x26, w27, w28       // Complex port, 64-bit结果

add  x29, x30, x0
eor  x1,  x2,  x3
subs x4,  x5,  x6        // 又一个flag-setting (进一步消耗flag rename)
umull x7,  w8,  w9        // Complex port

// 验证锚点 (在调度器/ROB满载压力下执行)
add  x10, x11, x12
madd x13, x14, x15, x16
```

---

### V3：PRF 耗尽 + 分支误预测回滚

**原理**：TaiShan V110 使用 PRF-based 寄存器重命名，支持 Move Elimination。PRF 的总条目数虽未公开但必然有限（通常为逻辑寄存器数量的 2-3 倍）。如果我们用大量写入不同逻辑寄存器的指令耗尽 PRF 映射表，然后紧接着触发一次**分支误预测**，CPU 必须回滚（squash）推测执行的所有指令并恢复 PRF 映射表到检查点状态。这个回滚路径是重命名逻辑中最复杂的状态机，也是 SDC 设计缺陷最容易藏匿的地方。

**关键参数依据**：
- PRF-based renaming + Move Elimination
- 31 个通用寄存器 (x0-x30) + 32 个向量寄存器 (v0-v31)
- Flag Rename ~31 entries
- BPU: 64-entry BTB, 分支密集场景有 +1 cycle 惩罚

**汇编种子代码** (`v3_prf_exhaust_mispredict.S`)：

```asm
// === V3: PRF Exhaustion + Branch Mispredict Rollback ===
// 阶段1: 写入所有31个通用寄存器, 耗尽整数PRF映射
movz x0,  #0x1234
movz x1,  #0x2345
movz x2,  #0x3456
movz x3,  #0x4567
movz x4,  #0x5678
movz x5,  #0x6789
movz x6,  #0x789A
movz x7,  #0x89AB
movz x8,  #0x9ABC
movz x9,  #0xABCD
movz x10, #0xBCDE
movz x11, #0xCDEF
movz x12, #0xDEF0
movz x13, #0xEF01
movz x14, #0xF012
movz x15, #0x0123
movz x16, #0x1111
movz x17, #0x2222
movz x18, #0x3333
movz x19, #0x4444
movz x20, #0x5555
movz x21, #0x6666
movz x22, #0x7777
movz x23, #0x8888
movz x24, #0x9999
movz x25, #0xAAAA
movz x26, #0xBBBB
movz x27, #0xCCCC
movz x28, #0xDDDD
movz x29, #0xEEEE
movz x30, #0xFFFF

// 阶段2: 写入向量寄存器, 耗尽向量PRF映射
fmov d0,  x0
fmov d1,  x1
fmov d2,  x2
fmov d3,  x3
fmov d4,  x4
fmov d5,  x5
fmov d6,  x6
fmov d7,  x7

// 阶段3: Flag-setting指令, 耗尽Flag Rename (~31 entries)
adds x0,  x1,  x2      // 写 NZCV flags
subs x3,  x4,  x5      // 写 NZCV flags
adds x6,  x7,  x8
subs x9,  x10, x11
adds x12, x13, x14
subs x15, x16, x17

// 阶段4: 制造分支误预测
// 使用一个数据依赖的条件分支, 让BPU无法准确预测
// cmp的结果取决于前面运算的值, BPU第一次见到此分支必然误预测
cmp x0, x3
b.eq .Ltaken_path       // 如果BPU预测为taken, 但实际为not-taken (或反之)
                         // CPU必须回滚所有推测执行的PRF分配

// 非跳转路径 (验证锚点, 在PRF回滚后执行)
add x0, x1, x2          // 此时PRF映射表刚刚被回滚恢复
madd x3, x4, x5, x6     // SDC最易发生的窗口

.Ltaken_path:
add x7, x8, x9          // 跳转路径也有验证锚点
```

---

### V4：LSU 跨边界访存压榨

**原理**：V110 的 LSU 拥有 2 个 AGU（地址生成单元），L1D 命中的 load-to-use 延迟为 4 周期，但**跨越 16B 地址边界的访问会产生 +1-2 周期的额外延迟**，Store Forwarding 延迟为 6-7 周期（跨 16B 边界同样 +1-2 周期）。这意味着 LSU 内部有专门处理跨边界访问的分拆逻辑（split-access logic），这种逻辑在连续高频触发时，是 SDC 缺陷最容易藏匿的位置之一。

**关键参数依据**：
- 2×AGU, L1D 64KB 4-way, 64B cache line
- Load-to-use: 4-cycle (aligned), +1-2 cycle (cross-16B)
- Store Forwarding: 6-7 cycle (aligned), +1-2 cycle (cross-16B)
- L1D 支持 2×128-bit/cycle (2 load 或 1 load + 1 store)

**汇编种子代码** (`v4_lsu_cross_boundary.S`)：

```asm
// === V4: LSU Cross-Boundary Stress ===
// 前置: x0 指向一个已映射的数据页面, 地址故意设为 page_base + 14
// 使得 LDP/STP 的 16B 对恰好跨越 16B 边界

// 模式A: 跨16B边界的Load Pair (触发LSU split-access逻辑)
ldp x1, x2, [x0, #0]     // 地址 = base+14, 跨越 16B 边界 (14+16=30)
ldp x3, x4, [x0, #16]    // 地址 = base+30, 跨越 16B 边界 (30+16=46)
ldp x5, x6, [x0, #32]    // 地址 = base+46, 跨越
ldp x7, x8, [x0, #48]

// 模式B: 跨16B边界的Store Pair + 紧接着的Load (测试Store Forwarding)
stp x1, x2, [x0, #64]    // 跨边界写入
ldp x9, x10, [x0, #64]   // 立即读回 (触发跨边界 Store Forwarding, 6-7+1-2 cyc)
// SDC检测: x9应该等于x1, x10应该等于x2

// 模式C: 128-bit向量跨边界 (最大压力)
str q0, [x0, #14]         // 128-bit store 跨越 16B 边界
ldr q1, [x0, #14]         // 128-bit load 跨越 16B 边界
// SDC检测: q1 应该等于 q0

// 模式D: 交错的跨边界 load 和 store (压满2个AGU)
ldp x11, x12, [x0, #0]
stp x13, x14, [x0, #80]
ldp x15, x16, [x0, #16]
stp x17, x18, [x0, #96]
```

---

### V5：跨 NUMA / 跨 Die 缓存一致性压榨

**原理**：根据服务器实测的 NUMA 距离矩阵（Node 0-1 距离 12, Node 0-2 距离 20, Node 0-3 距离 22, Node 1-3 距离 24），Node 0 和 Node 1 属于同一 Compute Die（距离 12），Node 2 和 Node 3 属于另一个 Die（也是距离 12）。跨 Die 访问距离为 20-24，必须穿越 Bufferless 双环 NoC + HCCS Hydra 链路。

当 Silifuzz Orchestrator 在 Node 0 的核心上执行用例，而该用例访问的数据内存页（data1/data2 映射区域）被操作系统分配到了 Node 2 或 Node 3 上时，每次 L3 缺失后的 DRAM 访问都需要经过完整的跨 Die 一致性协议。在高压下，这条路径上的 HHA（Home Agent）状态机和 Snoop Filter 是一致性竞态错误的高发区。

**关键参数依据（实测）**：
```
NUMA距离矩阵 (实测):
      Node0  Node1  Node2  Node3
Node0:  10     12     20     22
Node1:  12     10     22     24
Node2:  20     22     10     12
Node3:  22     24     12     10
```
- 128 核, 2 Socket, 每 Socket 64 核, 4 NUMA nodes
- Node 0 (CPU 0-31), Node 1 (CPU 32-63), Node 2 (CPU 64-95), Node 3 (CPU 96-127)

**执行策略**（无需修改汇编，通过操作系统调度实现）：

```bash
# 方案A: 最大跨Die延迟 - 在Node0执行, 内存绑定Node3 (距离24最远)
# 需要先安装 numactl: sudo dnf install -y numactl
numactl --cpunodebind=0 --membind=3 \
  silifuzz_orchestrator_main --duration=24h \
    --runner=/usr/local/bin/reading_runner_main_nolibc \
    --shard_list_file=./output/shard_list \
    --corpus_metadata_file=./output/corpus_metadata

# 方案B: 交替跨Die - 在Node1执行, 内存绑定Node2 (距离22)
numactl --cpunodebind=1 --membind=2 \
  silifuzz_orchestrator_main --duration=24h \
    --runner=/usr/local/bin/reading_runner_main_nolibc \
    --shard_list_file=./output/shard_list \
    --corpus_metadata_file=./output/corpus_metadata

# 方案C: 内存交错 (interleave) - 让每个cache line在不同Node间交替
numactl --cpunodebind=0 --interleave=all \
  silifuzz_orchestrator_main --duration=24h \
    --runner=/usr/local/bin/reading_runner_main_nolibc \
    --shard_list_file=./output/shard_list \
    --corpus_metadata_file=./output/corpus_metadata
```

---

### V6：密码学硬核启停时序冲击

**原理**：鲲鹏 920 原生支持 AES、SHA1/SHA2、CRC32 硬件加速指令（`cpuinfo` 中确认：`aes pmull sha1 sha2 crc32`）。这些指令由 CPU 内部专用的硬件加速单元处理，通常有独立的供电域。在快速交替激活和休眠这些硬件单元时，独立供电域与主核心供电域之间的电压耦合会产生额外的时序干扰。

**关键参数依据**：
- CPU Features (实测): `aes pmull sha1 sha2 crc32 atomics fphp asimdhp asimdrdm jscvt fcma dcpop asimddp asimdfhm`

**汇编种子代码** (`v6_crypto_toggle.S`)：

```asm
// === V6: Crypto Unit Power Toggle ===
// 策略: 在纯整数运算和密码学硬件指令之间快速切换
// 制造密码学硬核供电域的频繁启停

// ---- 密码学硬核激活 ----
aese   v0.16b, v1.16b       // AES加密单轮
aesmc  v0.16b, v0.16b       // AES Mix Columns
sha256h  q2, q3, v4.4s      // SHA-256 Hash
crc32cx  w5, w6, x7         // CRC32C

// ---- 立即切换到纯整数 (密码学硬核休眠) ----
add x0, x1, x2
mul x3, x4, x5
eor x6, x7, x8
sub x9, x10, x11

// ---- 再次激活密码学硬核 ----
aese   v8.16b, v9.16b
aesmc  v8.16b, v8.16b
sha256h  q10, q11, v12.4s
crc32cx  w13, w14, x15

// ---- 再次休眠, 验证锚点 ----
add x16, x17, x18           // 验证锚点
madd x19, x20, x21, x22     // 验证锚点

// 重复以上模式 4-8 次
aese   v16.16b, v17.16b
aesmc  v16.16b, v16.16b
sha1c  q18, s19, v20.4s     // SHA-1
crc32cw w21, w22, w23

add x24, x25, x26
eor x27, x28, x29
```

---

## 第三部分：Silifuzz + Centipede 集成实施方案

### 3.1 将攻击向量转化为 Centipede 种子

上述 6 个汇编模板不是直接运行的，而是作为 Centipede 模糊测试引擎的**初始种子（Seeds）**。Centipede 会基于这些种子进行自动化变异（位翻转、指令插入、寄存器替换等），在 Unicorn 模拟器中验证指令合法性后，生成大量变种。

**步骤 1：将汇编模板编译为原始机器码**

```bash
cd ~/wangxu/silifuzz

# 为每个攻击向量编译原始机器码种子
mkdir -p seeds

# 示例: 编译 V1 Vdroop Oscillator
cat > /tmp/v1.S << 'EOF'
.text
.globl _start
_start:
nop; nop; nop; nop; nop; nop; nop; nop
fmla v0.4s, v16.4s, v17.4s
fmla v1.4s, v18.4s, v19.4s
fmla v2.4s, v20.4s, v21.4s
fmla v3.4s, v22.4s, v23.4s
fmla v4.4s, v24.4s, v25.4s
fmla v5.4s, v26.4s, v27.4s
fmla v6.4s, v28.4s, v29.4s
fmla v7.4s, v30.4s, v31.4s
nop; nop; nop; nop
add x0, x1, x2
eor x3, x4, x5
madd x6, x7, x8, x9
nop; nop; nop; nop
EOF

aarch64-linux-gnu-as -o /tmp/v1.o /tmp/v1.S 2>/dev/null || \
  as -o /tmp/v1.o /tmp/v1.S
aarch64-linux-gnu-objcopy -O binary -j .text /tmp/v1.o seeds/v1_vdroop.bin 2>/dev/null || \
  objcopy -O binary -j .text /tmp/v1.o seeds/v1_vdroop.bin

# 对 V2-V6 重复相同流程...
```

**步骤 2：使用种子启动 Centipede Fuzzing**

```bash
# 启动带种子的 Centipede, 使用字典增强变异
bazel-bin/external/fuzztest+/centipede/centipede \
  --binary=bazel-bin/proxies/unicorn_aarch64 \
  --workdir=/tmp/centipede_wd_kunpeng \
  --seed_corpus_dir=seeds/ \
  -j=10 --num_runs=50000 --jobs=32
```

**步骤 3：将 Fuzzing 结果转换为可执行语料**

```bash
bazel-bin/tools/simple_fix_tool_main \
  --num_output_shards=10 \
  --output_path_prefix=~/wangxu/silifuzz/output/kunpeng-corpus \
  --runner=/usr/local/bin/reading_runner_main_nolibc \
  /tmp/centipede_wd_kunpeng/corpus.*
```

### 3.2 环境毒化下的真机验证

在生成语料后，使用以下脚本在物理机上进行高效 SDC 扫描：

```bash
#!/bin/bash
# kunpeng_sdc_sweep.sh
# 在多种NUMA配置下并行验证SDC语料

set -e

RUNNER=/usr/local/bin/reading_runner_main_nolibc
SHARD_LIST=~/wangxu/silifuzz/output/shard_list
METADATA=~/wangxu/silifuzz/output/corpus_metadata
DURATION=8h

echo "=== 鲲鹏920 SDC 多维度扫描 ==="

# 维度1: 正常执行 (基线)
echo "[1/4] 基线扫描 (本地Node)"
taskset -c 0-31 silifuzz_orchestrator_main --duration=$DURATION \
  --runner=$RUNNER --shard_list_file=$SHARD_LIST \
  --corpus_metadata_file=$METADATA &

# 维度2: 跨Die最远距离 (Node0执行, Node3内存)
echo "[2/4] 跨Die扫描 (Node0->Node3, distance=22)"
numactl --cpunodebind=0 --membind=3 \
  silifuzz_orchestrator_main --duration=$DURATION \
  --runner=$RUNNER --shard_list_file=$SHARD_LIST \
  --corpus_metadata_file=$METADATA &

# 维度3: 内存交错模式 (最大NoC压力)
echo "[3/4] 内存交错扫描 (interleave=all)"
numactl --cpunodebind=1 --interleave=all \
  silifuzz_orchestrator_main --duration=$DURATION \
  --runner=$RUNNER --shard_list_file=$SHARD_LIST \
  --corpus_metadata_file=$METADATA &

# 维度4: 背景功耗噪声 (功耗病毒)
echo "[4/4] 背景噪声扫描 (stress-ng on remaining cores)"
# 在 Node2/Node3 上运行内存带宽压力, 制造NoC拥塞
stress-ng --vm 16 --vm-bytes 256M --vm-method all \
  --cpu 32 --cpu-method matrixprod \
  --taskset 64-127 --timeout $DURATION &

numactl --cpunodebind=0 --membind=2 \
  silifuzz_orchestrator_main --duration=$DURATION \
  --runner=$RUNNER --shard_list_file=$SHARD_LIST \
  --corpus_metadata_file=$METADATA &

wait
echo "=== 扫描完成 ==="
```

---

## 第四部分：演化反馈闭环 (Evolutionary Feedback Loop)

### 4.1 捕获-放大循环

当 `silifuzz_orchestrator_main` 检测到 SDC 事件（即某个 Snapshot 的实际终态与记录终态不符）时，它会在日志中报告该异常 Snapshot 的标识。此时应当：

1. **提取触发 SDC 的 Snapshot** 的原始指令序列
2. **将其转为 Centipede 种子**，喂回到 `seeds/` 目录
3. **重新启动 Centipede**，基于此"已证明有杀伤力的种子"进行局部变异
4. 重复上述 Fuzzing → Fix → 验证 循环

```bash
# 伪代码: SDC事件驱动的演化循环
while true; do
  # 运行验证 (8小时)
  silifuzz_orchestrator_main --duration=8h ... 2>&1 | tee scan.log
  
  # 检查是否发现SDC
  if grep -q "SDC\|mismatch\|SIGABRT" scan.log; then
    echo "发现SDC事件! 提取种子并放大..."
    # 提取触发SDC的corpus shard中的原始指令
    # 将其加入seeds/目录
    # 重新运行Centipede变异
    bazel-bin/external/fuzztest+/centipede/centipede \
      --binary=bazel-bin/proxies/unicorn_aarch64 \
      --workdir=/tmp/centipede_wd_amplify \
      --seed_corpus_dir=seeds/ \
      -j=10 --num_runs=100000
    # 重新Fix
    bazel-bin/tools/simple_fix_tool_main \
      --num_output_shards=10 \
      --output_path_prefix=~/wangxu/silifuzz/output/kunpeng-corpus \
      --runner=/usr/local/bin/reading_runner_main_nolibc \
      /tmp/centipede_wd_amplify/corpus.*
  fi
done
```

### 4.2 效率估算

| 参数 | 值 | 依据 |
|------|---|------|
| 单次 Centipede Fuzzing | ~10,000 runs, ~3,202 合法 Snapshots | 前次实测结果 |
| 单个 Snapshot 执行时间 | ~1-10 μs (取决于指令数) | `max_inst_executed = 0x1000` |
| Orchestrator 吞吐 (128核) | ~10M+ Snapshots/秒 | 128 核并行, 每核 ~80K/s |
| 24小时扫描总量 | ~864B 次 Snapshot 执行 | 10M/s × 86400s |
| SDC 典型概率 (有毒化) | 10⁻⁸ ~ 10⁻¹⁰ / 执行 | 业界经验值 |
| 预期 24h 检出 SDC 数 | 8 ~ 86,400 次 | 取决于芯片健康状况 |

---

## 第五部分：方案总结

| 层次 | 策略 | 利用的 V110 参数 | 预期 SDC 贡献度 |
|------|------|-----------------|---------------|
| **指令级** | V1: FSU Vdroop 振荡器 | 双FSU, FMLA 7-cyc, NOP→满载 | ★★★★★ (最高) |
| **指令级** | V2: ALU+Complex 饱和 | 3ALU+1Complex, 33-entry sched | ★★★★ |
| **指令级** | V3: PRF 耗尽+误预测 | PRF rename, 31 flag, move elim | ★★★★ |
| **指令级** | V4: LSU 跨边界 | 2AGU, cross-16B +1-2cyc | ★★★ |
| **系统级** | V5: 跨NUMA 一致性 | 4-node, distance 10-24, HCCS | ★★★★ |
| **指令级** | V6: 密码硬核启停 | AES/SHA/CRC32 独立单元 | ★★★ |
| **环境级** | 功耗毒化 + 带宽风暴 | 128核+187GB/s DDR4, NoC | ★★★★★ (放大器) |

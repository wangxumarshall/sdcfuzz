# 鲲鹏 920 (TaiShan V110) SDC 高效检测用例生成方案

> **目标**：在鲲鹏 920（TaiShan V110, ARMv8.2-A, Implementer 0x48, Part 0xd01）上系统性挖掘能高概率触发 SDC 的检测用例
> **方法论**：Bottom-Up（微架构/电路脆弱性）⊗ Top-Down（业务负载模型）深度融合

---

## 前言：为什么现有 STL 覆盖率上限低？

当前 ARM CPU 的 SDC 检测用例在电路级的覆盖率现状低: FSU（浮点/SIMD） 80%, IEX（整数执行）70%, IFU（取指单元）66% , OoO（乱序执行）56%,  LSU（Load/Store）54% , L2C（L2 Cache）40%, MMU（内存管理）20%。其根因在于现有SDC检测工具**仅在"指令集空间"做均匀遍历，而未深入"操作数/执行上下文空间"做压力权重覆盖**。具体而言：
- **EDA 工具仿真覆盖率**衡量的是"结构覆盖率"——即某条 Gate/Wire 是否被信号激活过。
- **真实电路注错覆盖率**衡量的是"功能检出率"——即某个 Gate 发生位翻转后，是否能被测试用例**检测到**。
- 两者是**完全不同的维度**。一条 Gate 即便被激活了（结构覆盖率=1），如果操作数未能触发其最脆弱的时序路径，也无法检出该 Gate 的瞬态翻转（功能检出率=0）。

> [!IMPORTANT]
> **核心洞察**：`add x0, x1, x2` 这条指令，在结构覆盖率上只算"1个指令"；但如果 x1=0xFFFFFFFFFFFFFFFF, x2=0x1（全进位链），vs x1=0x0, x2=0x0（零路径），两者激活的内部 Gate 路径完全不同。**操作数空间的深度变异，才是提升功能检出率的关键杠杆。**

---

## 第零部分：设计概念锚定（weak 三因素 + 两范式 + 三维压测空间）

本方案是设计概念 `kunpeng920_sdc_design_concept.md` 的工程化落地，核心由四要素引导：

### 三因素致因模型（"weak"从何而来）

| 因素 | 物理本质 | 检测难度 | 破局路径 |
|------|----------|----------|----------|
| **① 设计期校验冗余不足** | 因成本/面积/功耗妥协，部分逻辑路径无 ECC/Parity 保护（ALU 计算路径、TLB CAM 匹配、乱序控制状态机） | 难——缺陷已固化在硅上，只能靠压测逼出 | Bottom-Up：针对无保护路径设计最长组合逻辑延迟的操作数，逼出时序违例 |
| **② 老化/工艺退化** | HCI/NBTI/EM 导致晶体管阈值漂移，时序裕量随时间变薄 | 难——无现成老化模型，需长周期高压暴露 | Bottom-Up：用极端翻转率/进位链逼出时序违例 |
| **③ 业务负载模型** | 特定业务持续激发特定模块（DB→LSU，HPC→FSU，虚拟化→MMU/CSU） | 相对可控——可从真实负载画像反推 | Top-Down：抽象业务模型，做压力权重分配 |

### 两大范式转移

```
范式转移 1:  指令集空间 ──→ 操作数/执行上下文空间
             (遍历指令类型)    (对每条指令, 遍历操作数的极端值组合)

范式转移 2:  均匀覆盖 ──→ 压力权重覆盖
             (每模块等权)    (对弱模块施加 3-5 倍权重的测试密度)
```

### 三维 SDC 压测空间

1. **微架构与电路脆弱性维度 (Bottom-Up)**：针对缺乏 ECC/Parity 保护的逻辑、高扇出网络、易时序违例的深层流水线定向打击（对应因素 ①②）。
2. **执行上下文与指令空间维度 (Core)**：通过操作数极端变异、指令乱序重排、复杂数据依赖，最大化电路翻转率（Toggle Rate），局部制造极端 `di/dt`，逼出边缘失效。
3. **业务负载特征维度 (Top-Down)**：抽象数据库（LSU/L2C）、虚拟化（MMU/CSU）、HPC（FSU/IEX）业务模型，按部署场景做权重分配（对应因素 ③）。

**破局命题**：只有 Down-Top 与 Top-Down 融合，才能既知道"哪里脆弱"，又知道"现实里它会被怎么打"——从而把压力精确施加到最该打的地方。这是本方案区别于"纯追求电路覆盖率"的根本所在。

---

## 第一部分：方法论——三维 SDC 压测空间

### 1.1 SDC 的三因素致因模型

造成芯片某个部分 weak（脆弱）的因素有三种，我们的用例生成必须与这三种因素**充分耦合**：

| 因素 | 描述 | 检测策略 |
|------|------|---------|
| **(1) 设计冗余不足** | 因成本约束，部分逻辑路径缺乏 ECC/Parity 保护（如 ALU 计算路径、TLB CAM 匹配逻辑） | 针对无保护路径设计**最长组合逻辑延迟**的操作数，逼出时序违例 |
| **(2) 老化/工艺退化** | HCI（热载流子注入）、NBTI（负偏压温度不稳定性）、EM（电迁移）导致晶体管阈值漂移 | 设计**高翻转率 (Toggle Rate)** 操作数序列，加速并暴露老化失效 |
| **(3) 业务负载模型** | 特定业务场景高频使用某些模块（数据库→LSU，HPC→FSU，虚拟化→MMU/CSU） | 基于业务画像对模块施加**差异化压力权重** |

### 1.2 两大范式转移

```
范式转移 1:  指令集空间 ──→ 操作数/执行上下文空间
             (遍历指令类型)    (对每条指令, 遍历操作数的极端值组合)

范式转移 2:  均匀覆盖 ──→ 压力权重覆盖
             (每模块等权)    (对弱模块施加 3-5 倍权重的测试密度)
```

### 1.3 EDA 结构覆盖率 vs 功能检出率：为什么需要两者融合？

```
┌──────────────────────────────────────────────────────────────────┐
│                     EDA 结构覆盖率                                │
│  "这条 Gate 被激活过吗？"                                        │
│  ✅ 能告诉我们：哪些 Gate/Wire 从未被触达 (Dead Zone)             │
│  ❌ 不能告诉我们：触达后，瞬态翻转是否能被捕获                     │
│                                                                  │
│  EDA 的价值: 定位"未覆盖的 Dead Zone", 即覆盖率的下限             │
└───────────────────────────────┬──────────────────────────────────┘
                                │ 融合
┌───────────────────────────────▼──────────────────────────────────┐
│                     功能检出率 (Fault Coverage)                    │
│  "这条 Gate 翻转后, 错误能传播到输出吗？"                         │
│  依赖于:                                                         │
│    ① 操作数是否激活了该 Gate 的最敏感路径                          │
│    ② 错误是否被后续逻辑掩蔽 (Logical Masking)                     │
│    ③ 错误是否被时序窗口掩蔽 (Timing Masking)                      │
│    ④ 错误是否传播到可观测输出 (Observability)                      │
│                                                                  │
│  提升手段: 操作数极端化 + 高翻转率 + 减少逻辑掩蔽                  │
└──────────────────────────────────────────────────────────────────┘
```

> [!TIP]
> **实操建议**：从 EDA 工具获取每个模块的"未覆盖 Gate 清单"，然后反向推导需要什么**操作数组合**才能激活这些 Gate。这就是"从设计端打开，看看哪些模块更加脆弱"的工程化落地路径。

---

## 第二部分：操作数空间深度变异引擎设计

### 2.1 操作数变异字典 (Operand Mutation Dictionary)

基于系统化的面向电路脆弱性的操作数种子库，并支持随机数生成器。

#### 整数操作数种子 (IEX/ALU)

| 种子类别 | 值 (64-bit) | 电路级目标 |
|---------|-------------|-----------|
| 全零 | `0x0000000000000000` | 零路径（大量 Gate 不翻转，测试静态漏电SDC） |
| 全一 | `0xFFFFFFFFFFFFFFFF` | 全进位链、全输出翻转 |
| 交替 01 | `0x5555555555555555` | **50% 翻转率**，最大化动态功耗 |
| 交替 10 | `0xAAAAAAAAAAAAAAAA` | 与 01 交替使用，**100% bit-toggle** |
| 单比特游走 | `0x1`, `0x2`, `0x4`, ..., `0x8000000000000000` | 逐一测试每个 bit 位的进位路径 |
| 进位边界 | `0x00000000FFFFFFFF` (32-bit 进位溢出) | 32→64 位进位传播边界 |
| 字节边界 | `0x00FF00FF00FF00FF` | 字节拼接逻辑（LSU forwarding 关键路径） |
| 半字游走 | `0x0000FFFF0000FFFF` | 16-bit 运算单元边界 |
| 最大正 + 1 | `0x7FFFFFFFFFFFFFFF` + 1 | **有符号溢出**（影响 NZCV flags 生成逻辑） |
| 乘法极端 | `0xFFFFFFFF × 0xFFFFFFFF` | **乘法器最长延迟路径**（4-cycle Complex 端口） |

#### 浮点/SIMD 操作数种子 (FSU)

| 种子类别 | 值 | 电路级目标 |
|---------|---|-----------|
| 正常数 | `1.0`, `2.0` | 基线路径 |
| **Subnormal（非规格化数）** | `±2⁻¹⁰²⁶` ~ `±2⁻¹⁰⁷⁴` (FP64) | **触发 FSU 内部微码/慢路径**（极低覆盖率区域） |
| NaN（非数） | `0x7FF8000000000000` (Quiet NaN) | NaN 传播逻辑（常被忽略的 Gate 路径） |
| Infinity | `0x7FF0000000000000` (±∞) | 无穷大运算逻辑 |
| 最大有限 | `0x7FEFFFFFFFFFFFFF` | 接近溢出边界 |
| 符号位翻转 | `+0.0` 与 `-0.0` 交替 | **符号位处理逻辑**（IEEE 754 特殊规则） |
| FP16 极端值 | `0x7BFF` (FP16 max), `0x0400` (FP16 min normal) | FP16 扩展路径（ARMv8.2 `fphp` 特性） |

#### 地址操作数种子 (LSU/MMU)

| 种子类别 | 地址偏移 | 电路级目标 |
|---------|---------|-----------|
| 对齐访问 | offset = 0, 16, 32, 48 | 基线路径 |
| **跨 16B 边界** | offset = 14, 30, 46, 62 | **LSU split-access 逻辑**（V110 +1-2cyc 惩罚处） |
| **跨 64B Cache Line** | offset = 60 (L1D/L2 line = 64B) | **L1D/L2 跨行逻辑** |
| **跨 128B L3 Line** | offset = 124 | **L3 跨行逻辑**（实测 L3 line = 128B！） |
| **跨 4KB 页边界** | offset = 4094 | **MMU 跨页逻辑 + TLB 双查询** |
| 同 Set 冲突 | stride = 64B × 256 (L1D sets) = 16384 | **L1D 替换算法逻辑** |
| L2 Set 冲突 | stride = 64B × 1024 (L2 sets) = 65536 | **L2 替换算法逻辑** |
| L3 Set 冲突 | stride = 128B × 2048 (L3 sets) = 262144 | **L3 替换算法逻辑** |

### 2.2 操作数组合矩阵 (Combinatorial Operand Matrix)

对于每条关键指令，不再只测试"这条指令是否执行过"，而是测试**操作数的笛卡尔积**：

```
以 ADD x0, x1, x2 为例:

x1 ∈ {0x0, 0xFFFF..., 0x5555..., 0xAAAA..., 0x7FFF..., 0x8000..., ...}  (10种)
x2 ∈ {0x0, 0xFFFF..., 0x5555..., 0xAAAA..., 0x7FFF..., 0x8000..., ...}  (10种)

→ 10 × 10 = 100 种操作数组合, 每种激活不同的 Gate 子集

传统 STL: 仅测试 ADD 1次 (覆盖率 +1 条指令)
操作数空间 STL: 测试 ADD 100次 (覆盖率 +数百个 Gate)
```

---

## 第三部分：各薄弱模块专项覆盖率提升方案

### 3.1 MMU — 从 20% 提升至 60%+

**当前薄弱根因**：
- MMU 的核心电路是 **TLB（CAM 内容寻址存储器）** 和 **Page Table Walker (PTW) 状态机**
- 常规测试的 TLB 命中率 > 99%，CAM 的并发比较器几乎从不被激活
- PTW 的多级页表遍历状态机（4级: PGD→PUD→PMD→PTE）极少被完整触发
- 虚拟化场景下的 Stage 2 翻译（IPA→PA）几乎未被测试

**专项用例设计**：

#### M1: TLB Thrashing（TLB 颠簸）
```asm
// 目标: 强制每次访存都 TLB Miss, 高频激活 PTW 状态机
// TaiShan V110: dTLB 32-entry fully-assoc, L2 TLB 1024-entry
// 策略: 访问 > 1024 个不同的 4KB 页面, 确保 L2 TLB 也被刷爆

// x0 = base address (已映射的大块内存)
// 步长 = 4096 (每次跨越一个完整页面)
ldr x1, [x0]              // 页面 0 → TLB Miss → PTW 全4级遍历
ldr x2, [x0, #4096]       // 页面 1 → TLB Miss
ldr x3, [x0, #8192]       // 页面 2 → TLB Miss
ldr x4, [x0, #12288]      // 页面 3 → TLB Miss
// ... 展开至 1100+ 条 (超过 L2 TLB 1024-entry)
// 变异: 每条 LDR 的目标寄存器不同, 消除数据依赖, 让 OoO 尝试并行发起多个 PTW
```

#### M2: 混合页面粒度
```asm
// 目标: 测试 TLB 中不同粒度 Entry 的匹配逻辑和替换算法
// AArch64 支持 4KB, 2MB (PMD大页), 1GB (PUD大页)
// 设计: 在同一个测试中, 交替访问不同粒度映射的内存区域

// 假设: x0 指向 4KB 映射区域, x1 指向 2MB 大页映射区域
ldr x2, [x0]         // 4KB 页 → TLB entry 格式 A
ldr x3, [x1]         // 2MB 页 → TLB entry 格式 B (不同的 mask/tag 宽度)
ldr x4, [x0, #4096]  // 4KB 另一页
ldr x5, [x1, #2097152] // 2MB 另一大页
// 交替访问制造 TLB 格式混合, 压测 CAM 的异构匹配逻辑
```

#### M3: 跨页边界访存（MMU + LSU 联合压测）
```asm
// 目标: 单条访存指令跨越 4KB 页边界
// 这是 MMU 最复杂的处理路径: 一次访存需要 2 次 TLB 查询 + 2 次权限检查
// 再合并结果, 任何一步出错都是 SDC

// x0 = 某个 4KB 页的最后 8 字节 (page_base + 4088)
ldp x1, x2, [x0]     // Load Pair 16B: 前 8B 在页 N, 后 8B 在页 N+1
                       // MMU 必须同时查询两个页表项

// 变异操作数: 修改 x0 的偏移, 让跨界发生在不同字节位置
// offset = 4089, 4090, ..., 4095: 每个偏移触发不同的字节对齐组合
```

#### M4: ASID/VMID 高频切换
```asm
// 目标: 高频切换地址空间标识符, 压测 TLB 的 ASID 匹配逻辑和 Flush 状态机
// 在容器/虚拟化场景中, 上下文切换极其频繁

// 伪代码 (需要 EL1 权限):
// 1. 设置 ASID=0x01, 访问 page A
// 2. 切换 ASID=0x02, 访问 page B (TLB 中 ASID=0x01 的条目不应命中)
// 3. 切换回 ASID=0x01, 再次访问 page A (验证 TLB 未错误返回 ASID=0x02 的数据)
// SDC 风险: ASID 比较器的某个 bit 翻转, 导致跨地址空间的数据泄露/错误
```

---

### 3.2 L2C — 从 40% 提升至 70%+

**当前薄弱根因**：
- L2 Cache 的核心复杂逻辑在于 **一致性状态机** (MOESI/MESI)、**替换算法** 和 **Write-back 回写逻辑**
- 常规测试的 L2 命中率极高，状态转换稀少
- **实测参数**：L2 = 512KB, 8-way, 1024 sets, 64B line, 10-cycle latency

**专项用例设计**：

#### C1: L2 Set 冲突风暴 (Eviction Storm)
```asm
// 目标: 精确瞄准同一个 L2 Set, 塞入 > 8 条 Cache Line (8-way), 强制持续换出
// L2: 1024 sets, 64B line → 冲突步长 = 64 × 1024 = 65536 bytes
// 访问 9 个地址, 它们映射到同一 Set, 每次访问都触发一次 Eviction

// x0 = base address
ldr x1, [x0]                  // Set S, Way 0
ldr x2, [x0, #65536]          // Set S, Way 1
ldr x3, [x0, #131072]         // Set S, Way 2
ldr x4, [x0, #196608]         // Set S, Way 3
ldr x5, [x0, #262144]         // Set S, Way 4
ldr x6, [x0, #327680]         // Set S, Way 5
ldr x7, [x0, #393216]         // Set S, Way 6
ldr x8, [x0, #458752]         // Set S, Way 7 (满)
ldr x9, [x0, #524288]         // Set S, 第9条 → 触发 Eviction!
                                // 替换算法 + Write-back 逻辑被激活

// 操作数变异: 在每次 Load 之间插入 Store, 制造 Dirty Line → Eviction 时必须 Write-back
str x1, [x0]                  // 将 Way 0 标记为 Dirty
ldr x10, [x0, #589824]        // 第10条 → Dirty Eviction (Write-back + Replace)
```

#### C2: Store-to-Load Forwarding 字节拼接压测
```asm
// 目标: 压测 L2C 与 LSU 之间的 Store Buffer Forwarding 逻辑
// V110 Store Forwarding: 6-7 cycle (对齐), +1-2 cycle (跨16B)
// SDC 风险: Store Buffer 中的字节拼接逻辑 (宽存窄读) 出错

// 宽写入
str x0, [x1]           // 写 8 字节到地址 A

// 立即窄读出 (从同一地址的不同字节偏移)
ldrb w2, [x1]          // 读 1 字节 (byte 0) → 需从 Store Buffer 前递
ldrb w3, [x1, #1]      // 读 1 字节 (byte 1)
ldrb w4, [x1, #7]      // 读 1 字节 (byte 7)
ldrh w5, [x1, #2]      // 读 2 字节 (byte 2-3)
ldr  w6, [x1, #4]      // 读 4 字节 (byte 4-7)

// SDC 验证: w2 应该等于 x0 的最低字节, w3 应该等于次低字节, 以此类推
// 操作数变异: x0 = 0xFF00FF00FF00FF00 (交替字节, 最大化拼接路径差异)
```

#### C3: L3 128B Line 特异性压测
```asm
// 重要发现: L3 Cache Line = 128B (而非 64B)!
// 这意味着 L2→L3 的数据搬运粒度不同, 存在 64B→128B 的对齐转换逻辑
// 这是一个极少被测试到的路径

// 访问地址 A (在某 128B L3 line 的前半 64B)
ldr x1, [x0]
// 访问地址 A+64 (在同一 128B L3 line 的后半 64B)
ldr x2, [x0, #64]
// 此时 L1D/L2 看到 2 条 64B line, 但 L3 看到 1 条 128B line
// 当 L2 Evict 前半 64B 时, L3 需要正确处理 partial write-back
// SDC 风险: L3 控制器在 partial 操作时的状态机出错

// 跨 128B L3 Line 边界
ldr x3, [x0, #124]     // 在 128B line 的末尾
ldr x4, [x0, #128]     // 跨入下一 128B line
// 如果是 LDP (Load Pair, 16B):
ldp x5, x6, [x0, #120] // 跨越 128B L3 line 边界!
```

---

### 3.3 LSU — 从 54% 提升至 75%+

**当前薄弱根因**：
- LSU 内部的 Store Buffer、Load Queue、地址歧义检测（Memory Disambiguation）逻辑复杂
- **实测参数**：2×AGU, L1D hit 4-cyc, StFwd 6-7 cyc, cross-16B +1-2 cyc

**专项用例设计**：

#### L1: 地址歧义与乱序访存
```asm
// 目标: 制造 Store 地址未知时, Load 是否可以推测执行的歧义场景
// V110 的 Memory Disambiguation 预测器需要判断: 这个 Load 是否与前面某个 Store 冲突?

// 制造地址歧义: Store 的地址依赖于一个长延迟的计算
mul x10, x11, x12           // Complex 端口, 4-cycle (x10 的值未知)
str x1, [x10]               // Store 地址 = x10 (延迟可用)
ldr x2, [x0]                // Load 地址 = x0 (立即可用)
                              // 问题: x10 是否等于 x0? LSU 必须做推测判断
                              // 如果推测"不冲突"但实际冲突 → SDC!

// 操作数变异: 让 x10 的计算结果有时等于 x0, 有时不等于
// 这迫使 Memory Disambiguation 预测器在"冲突/不冲突"边界反复横跳
```

#### L2: 多端口 AGU 并发 + 跨边界
```asm
// 目标: 同时打满 2 个 AGU, 并让两个访存都跨 16B 边界
// V110 L1D 支持 2×128-bit/cycle (2 load 或 1 load+1 store)

// x0 = base + 14 (跨 16B 边界)
// x1 = base + 78 (跨另一个 16B 边界)
ldp x2, x3, [x0]       // AGU0: 跨 16B 边界的 Load Pair (split access)
ldp x4, x5, [x1]       // AGU1: 同时另一个跨边界 Load Pair
// 两个 AGU 同时处理 split access → LSU 内部的 split-merge 逻辑双份压力

// 操作数变异: 修改 x0, x1 的偏移量, 遍历所有可能的跨边界对齐方式
// offset ∈ {9, 10, 11, 12, 13, 14, 15} × 2 = 49 种组合
```

---

### 3.4 OoO (乱序执行) — 从 56% 提升至 72%+

**当前薄弱根因**：
- OoO 的核心控制逻辑（ROB、Scheduler、PRF Rename、Flag Rename）只有在**队列接近满载**时才会暴露边界 Bug
- **实测参数**：~33-entry scheduler (each), ~31-entry flag rename, PRF-based, 4-wide

**专项用例设计**：

#### O1: ROB + Scheduler 满载 + 唤醒风暴
```asm
// 目标: 用一条 L3 Miss 的 Load 阻塞管线, 积压数十条后续指令
// 当 L3 Miss 返回时, 所有阻塞指令"同时唤醒", 制造瞬间极高 di/dt

// 阶段1: 发起一条必定 L3 Miss 的 Load (触发 DRAM 访问, >100 cycle)
ldr x0, [x20]          // x20 指向一个被预先驱逐出所有 Cache 的地址

// 阶段2: 30+ 条依赖于 x0 的指令 (全部积压在 Scheduler 中)
add x1, x0, #1         // 依赖 x0, 无法执行, 停在 scheduler entry 1
add x2, x0, #2         // 依赖 x0, 停在 scheduler entry 2
eor x3, x0, x1         // 依赖 x0 和 x1
add x4, x0, #4
sub x5, x0, x1
and x6, x0, x2
orr x7, x0, x3
// ... 展开至 30+ 条, 填满 ~33-entry scheduler

// 阶段3: 穿插 flag-setting 指令, 同时填满 flag rename (~31 entries)
adds x8, x0, x4
subs x9, x0, x5
adds x10, x0, x6
subs x11, x0, x7
// ...

// 当 DRAM 数据返回时: 所有 30+ 条指令 + flag 计算同时唤醒
// → 瞬间 di/dt 极大, 时序裕量最小
// → SDC 最易发生的窗口
```

#### O2: 分支预测欺骗 + PRF 回滚
```asm
// 目标: 训练分支预测器, 然后故意制造误预测, 测试 PRF 回滚逻辑

// 阶段1: 训练 (让 BPU 学习到 "这个分支总是taken")
mov x0, #100
.Ltrain_loop:
    subs x0, x0, #1
    b.ne .Ltrain_loop    // 循环 100 次, BPU 学到: 这里总是跳转

// 阶段2: 在循环结束的最后一次 (x0=0), BPU 仍预测 taken
// 但实际 not-taken → CPU 在错误路径上已推测执行了若干条指令
// 所有推测指令的 PRF 分配必须回滚

// 在"错误路径"上 (推测执行的代码) 放置高功耗指令
// 当回滚发生时, 这些指令的 PRF 映射被撤销
// 回滚后立即执行的"验证锚点"是 SDC 检测关键
nop  // 回滚完成后, 从这里继续
add x1, x2, x3    // 验证锚点: PRF 映射表刚被回滚恢复
madd x4, x5, x6, x7  // 验证锚点
```

---

### 3.5 IEX (整数执行) — 从 70% 提升至 85%+

**核心策略：操作数空间的极端化**

#### E1: 加法器最长进位链
```asm
// 目标: 强制加法器的进位信号从 bit 0 传播到 bit 63 (最长组合逻辑路径)
// 这是加法器中延迟最大、最容易被时序违例击穿的路径

movz x1, #0xFFFF, lsl #0
movk x1, #0xFFFF, lsl #16
movk x1, #0xFFFF, lsl #32
movk x1, #0xFFFF, lsl #48    // x1 = 0xFFFFFFFFFFFFFFFF
mov  x2, #1                   // x2 = 1

adds x0, x1, x2               // 0xFFFF...FFFF + 1 = 0x0, C=1
                                // 进位从 bit0 传播到 bit63 + Carry flag
// SDC 验证: x0 必须 = 0, NZCV.C 必须 = 1

// 操作数变异: 测试不同长度的进位链
// x1 = 0x00000000FFFFFFFF, x2 = 1  → 32位进位链
// x1 = 0x0000FFFFFFFFFFFF, x2 = 1  → 48位进位链
```

#### E2: 乘法器极端操作数
```asm
// 目标: 压测 Complex 端口的乘法器 (4-cycle latency)
// 最长延迟路径: 两个最大值相乘

movz x1, #0xFFFF, lsl #0
movk x1, #0xFFFF, lsl #16    // x1 = 0xFFFFFFFF (32-bit max)
mov  x2, x1                   // x2 = 0xFFFFFFFF

umull x0, w1, w2               // 32×32→64 无符号乘法
// x0 = 0xFFFFFFFE00000001 (精确值)
// SDC 验证: 检查精确结果

smull x3, w1, w2               // 有符号乘法 (w1, w2 = -1 as signed)
// x3 = 1 (−1 × −1 = 1)
// SDC 验证: 检查符号处理逻辑
```

#### E3: 高翻转率交替操作数
```asm
// 目标: 连续指令使用交替的操作数, 最大化 ALU 内部 Gate 翻转率
// 0x5555... 和 0xAAAA... 交替 → 每个 bit 都翻转 → 最大 di/dt

mov x1, #0x5555555555555555
mov x2, #0xAAAAAAAAAAAAAAAA

add x3, x1, x2    // ALU 内部所有 bit 从 0→1 或 1→0
add x4, x2, x1    // 再次全翻转
sub x5, x1, x2    // 减法路径也全翻转
eor x6, x1, x2    // XOR: x6 = 0xFFFF... (全1)
eor x7, x2, x1    // XOR: 相同 (但 ALU 输入全翻转)
and x8, x1, x2    // AND: x8 = 0x0 (全0, 输出翻转)
orr x9, x1, x2    // OR: x9 = 0xFFFF... (全1, 输出翻转)
```

---

### 3.6 FSU (浮点/SIMD) — 从 80% 提升至 90%+

**核心策略：Subnormal/NaN 等 FSU 慢路径覆盖**

#### F1: Subnormal (非规格化数) 压测
```asm
// 目标: 触发 FSU 内部的 Subnormal 处理逻辑 (极少被测试到)
// IEEE 754 Subnormal: 指数全0, 尾数非0
// 大多数 FSU 实现对 Subnormal 使用微码或慢路径, 是 Gate 覆盖率盲区

fmov d0, #0.0
// 构造一个 Subnormal: 0x0000000000000001 (最小正 Subnormal FP64)
mov x1, #1
fmov d1, x1

fadd d2, d0, d1    // 0 + Subnormal → FSU 慢路径
fmul d3, d1, d1    // Subnormal × Subnormal → 可能下溢到 0
fdiv d4, d1, d0    // Subnormal / 0 → Infinity (特殊处理)

// NaN 传播测试
mov x2, #0x7FF8000000000000  // Quiet NaN
fmov d5, x2
fadd d6, d5, d1    // NaN + 任何数 = NaN (传播逻辑)
fcmp d5, d1        // NaN 比较 → 总是 Unordered (NZCV 特殊设置)
```

---

### 3.7 IFU (取指单元) — 从 66% 提升至 80%+

#### I1: 指令缓存边界压测
```asm
// 目标: 让指令本身跨越 L1I Cache Line 边界 (64B)
// V110 L1I: 64KB, 4-way, 256 sets, 64B line
// 策略: 将代码放置在 64B 对齐地址 - 4 的位置
// 使得一条 4B 指令的前半在 Line N, 后半在 Line N+1

// 配合 NOP 填充, 将关键指令精确放置在 Cache Line 边界
.balign 64             // 对齐到 64B
.rept 15               // 15 × 4B = 60B 的 NOP
    nop
.endr
// 此时 PC = base + 60, 下一条 4B 指令跨越 64B 边界
add x0, x1, x2        // 这条指令的 bytes [60, 63] 在 Line N
                        // 没有跨行 (4B 指令), 但可以用 LDP 跨行
```

#### I2: 分支密集场景
```asm
// 目标: 测试 BPU 在分支密集 (≤16B间隔) 时的 +1 cycle 惩罚路径
// V110: 分支间隔 ≤ 16B 时有额外 1 cycle 惩罚 (BPU 带宽瓶颈)

b .Lnext1              // 4B
.Lnext1:
b .Lnext2              // 4B (间隔 4B, ≤ 16B → BPU 惩罚)
.Lnext2:
b .Lnext3              // 4B
.Lnext3:
b .Lnext4              // 4B
.Lnext4:
// 连续 20+ 个短跳转, 持续触发 BPU 的密集分支处理逻辑
// 配合 BTB 64-entry, 制造 BTB 溢出
```

---

## 第四部分：Silifuzz + Centipede 集成与自动化闭环

> **工程实测（2026/08/26）**：本方案的所有路径已在鲲鹏 920 上验证跑通。
> - **直链种子→语料**：`seed.S → as/objcopy → seed.bin → snap_tool --raw --runner=... --out=x.pb make → snap_tool --target_platform=arm-neoverse-n1 generate_corpus *.pb --out=corpus → reading_runner_main_nolibc corpus` 返回 `code:1`(=OK)。
> - **分支种子有效**：`b.eq`/`b.ne`/前向 `b` 均通过 `make`+`runner`。退出序列在 PC 走出代码边界时捕获（非线性递增），故 V3/O2/I2 模板可原样保留。唯一约束：执行须在代码地址范围内终结。
> - **Centipede 引导变异入口**：`centipede --corpus_from_files=<seeds_dir>`（每文件一输入，正是 `.bin`）→ 变异器在操作数空间探索 → 输出 `corpus.*`（Centipede blob 格式）→ `simple_fix_tool_main corpus.*` → sharded Snap 语料（实测 726 输入→104 有效 snapshot）。
> - **内存布局**：`x6=data1_base(0x7'0000'0000,4MB)`、`x7=data2_base(0x1007'0000'0000,4MB)`、`sp=0x200'1000`，数据页初值 0；NUMA 拓扑实测与文档一致。
> - **寻址约束**：`stp/ldp` 只接受 `[Xn,#imm]`(imm 为 8 倍数) 或 `[Xn]`，**不接受** `[Xn,Xm]`；跨 16B/64B/128B 边界须先 `add x8,x6,#14` 计算非对齐地址到寄存器，再 `stp x0,x1,[x8]`（已验证往返捕获）。`ldr/str` 单寄存器形式可接受 `[Xn,Xm]`。
> - banned 指令：PAC/WFE/WFI/排他 store/MRS/MSR/UDF。18 模板的核心指令（FMLA/ALU/MUL/MADD/LDP/STP/AES/SHA/CRC32/LDR/STR/fadd/fmul）**全部通过**过滤。

> **工程实现产物清单（2026/08/26，feat/sdc-detection-cases-kunpeng920 分支）**：
> - `seeds/operand_dict.md` + `seeds/asm_common.S.inc`：操作数变异字典 + 可复用宏（MOVK_ALL/LOAD_SUBNORMAL_MIN/LOAD_QNAN 等）。
> - `seeds/*.S`：19 个微架构定向压力模板（V1-V6 + E1-E3 + F1 + M1/M3 + C1/C3 + L1/L2 + O1/O2 + I1/I2）。实测 **19/19** 全部 `fuzz_filter_tool exit 0` + `snap_tool make` 成功 + `runner replay code:1`。end-state 抽查精确：e1 `x0=0`(64位进位链)/`x5=0x100000000`(32位边界)；e2 `x0=0xFFFFFFFE00000001`(umull)/`x3=1`(smull)；v4 `x18=0`(跨边界 store→load 往返校验)。
> - `scripts/build_seeds.sh`：遍历 `seeds/*.S` 用 `as`/`objcopy` 产 `.bin`（主机原生 aarch64，无需交叉工具链；V6 需 `.arch armv8-a+crypto+crc`）。
> - `tools/sdc_mutator/operand_mutator.py`：操作数空间引导变异引擎。解析模板 `// MUT: <slot>` 标记，用 operand_dict 对可变异操作数槽做**笛卡尔积替换**生成 N 变体。实测 e1 生成 10 变体（全1/交替01-10/进位边界32-48/字节交替/半字/最大正/最小负/零），carry32 变体 `x0=0x100000000`（32位进位边界精确激活），10 变体全部 make+replay `code:1`。
> - `scripts/run_guided_mutation.sh`：两阶段——**阶段A 确定性笛卡尔积**（保覆盖下限）+ **阶段B Centipede `--corpus_from_files` 引导探索**（提检出上限），`-j=10` 防 MCE。
> - `scripts/build_sdc_corpus.sh`：阶段A `.bin`→`snap_tool make`→`generate_corpus` 出 SnapCorp（runner 可读）；阶段B Centipede blob→`simple_fix_tool` 出 sharded SnapCorp；合并 `sdc_shard_list`+`sdc_corpus_metadata`。实测阶段A 29 `.pb`→147KB corpus→orchestrator 30s 冒烟无 SIGSEGV/mismatch。
> - `scripts/ssh_lib.py` + `deploy_board.sh` + `distributed_scan.py` + `collect_results.py`：分布式扫描集群（详见 4.2）。
> - `scripts/sdc_evolve.sh`：演化反馈闭环（详见 4.3）。

> **分布式接近满负载扫描实测（2026/08/26）**：3 单板并行 20s 扫描（`--max_cpus=$(nproc)`），结果：
> | 单板 | 核数 | SDC命中 | SIGSEGV噪声 | SIGTERM(timeout) |
> |------|------|---------|-------------|------------------|
> | 0101 | 126 | 0 | 48 | 1 |
> | 0102 | 192 | 0 | 97 | 15 |
> | 0103 | 128 | 0 | 566 | 11 |
> 总 SDC=0（语料干净，真机健康）。SIGSEGV 噪声是满负载 fork/mmap 资源耗尽击中 snap 外路径（非 SDC，非假阳性，orchestrator 容错继续）。`collect_results.py` 精确区分 SDC 命中（`Snapshot [hash] failed, outcome` 非信号杀）与噪声，已修正满负载日志交织导致的假阳性（旧正则把 SIGSEGV 行误判为 SDC）。

### 4.1 操作数变异引擎与 Centipede 种子集成

将上述所有攻击向量的汇编代码编译为原始机器码，作为 Centipede 的初始种子。Centipede 基于这些种子进行自动化变异时，会在**操作数空间**中进一步探索。

```bash
#!/bin/bash
# build_seeds.sh - 编译所有攻击向量为 Centipede 种子
cd ~/wangxu/silifuzz
mkdir -p seeds

for src in v1_vdroop v2_alu_sat v3_prf_exhaust v4_lsu_cross \
           v6_crypto m1_tlb_thrash c1_l2_evict c2_stfwd \
           l1_disambig o1_rob_full o2_mispredict \
           e1_carry e2_mul e3_toggle f1_subnormal i1_icache i2_branch; do
  if [ -f "asm_seeds/${src}.S" ]; then
    as -o /tmp/${src}.o asm_seeds/${src}.S
    objcopy -O binary -j .text /tmp/${src}.o seeds/${src}.bin
    echo "Generated seed: seeds/${src}.bin"
  fi
done

echo "Total seeds: $(ls seeds/*.bin | wc -l)"
```

**两阶段语料生成（确定性 + 探索式）**：
- **阶段 A（确定性，保覆盖下限）**：操作数字典对每个模板的"可变异操作数槽"做笛卡尔积替换（如 `e1` 的被加数/加数 10×10=100 变体），编译为 `.bin`，直接经 `snap_tool --raw make` 转 Snapshot，`generate_corpus` 打包。覆盖率下限由此保证。
- **阶段 B（探索式，提检出上限）**：以全部模板 `.bin` 为 `centipede --corpus_from_files=seeds/bin` 种子，`-j=10 --num_runs=...` 做引导式探索（Centipede 变异器在模板骨架上进一步探索操作数/指令组合）。功能检出率上限由此提升。
- 两阶段语料合并后经 `simple_fix_tool_main` 打包为 sharded relocatable corpus。

```bash
# 阶段 B 示例: Centipede 引导变异
bazel-bin/external/fuzztest+/centipede/centipede \
  --binary=bazel-bin/proxies/unicorn_aarch64 \
  --workdir=/tmp/centipede_wd_kunpeng \
  --corpus_from_files=seeds/bin/ \
  -j=10 --num_runs=50000

# 合并打包
bazel-bin/tools/simple_fix_tool_main \
  --num_output_shards=10 \
  --output_path_prefix=~/wangxu/silifuzz/output/sdc-corpus \
  --runner=/usr/local/bin/reading_runner_main_nolibc \
  /tmp/centipede_wd_kunpeng/corpus.*
```

### 4.2 分布式接近满负载多维度扫描集群

用户已提供 4 台鲲鹏 920 单板，实测拓扑（2026/08/26）：

| 单板 | IP | 核数 | NUMA | SSH | 工具 | 角色 |
|------|-----|------|------|-----|------|------|
| 0101 | 172.168.177.97 | 126 | 待查 | ✅ | 需部署 | 扫描节点 |
| 0102 | 172.168.160.42 | 192 | 8 节点(双路×4,24c/节点) | ✅ | 需部署 | 最大算力 |
| 0103 | 172.168.59.158 | 128 | 4×32c | ✅(编译机) | 全有 | 编译+基准+扫描 |
| 0201 | 172.168.178.81 | ? | ? | ❌ 超时 | — | 不可达，排除 |

合计 3 台可达单板、~446 核可并行接近满负载扫描。

**部署方式（实测可行）**：`runner`+`orchestrator` 是 `statically linked` ELF aarch64，从 0103 拷贝预编译二进制到各单板 `/sdc_tools/`+`/sdc_corpus/` 即可跑，无需每台重新编译。`snap_tool`/`simple_fix_tool_main` 是动态链接 PIE（openEuler 24.03 同构，glibc 可用）。

**满负载 SIGSEGV 容错（关键实测）**：`--max_cpus=$(nproc)`（如 0101 的 126）时 10s 出 ~8 次 `Received signal SIGSEGV while outside of snap`，`--max_cpus=8` 时 0 次。这是 fork/mmap 资源耗尽击中 **snap 外路径**，**非 SDC、非假阳性**，orchestrator 自身容错继续运行。脚本须区分：`SIGSEGV-outside-snap` 计为噪声统计，`SNAPSHOT_FAILED`/`mismatch` 计为 SDC 命中。

```bash
# 1. 部署静态二进制 + SDC 语料到 0101/0102 (0103 本机已有)
bash scripts/deploy_board.sh --all

# 2. 3 单板并行接近满负载扫描 + stress-ng 环境毒化 (di/dt 带宽风暴放大器)
python3 scripts/distributed_scan.py --duration 8h
#   每板: orchestrator --max_cpus=$(nproc) + 后台 stress-ng --cpu 8 --cpu-method matrixprod
#   0103 走本地分支(语料在 output/), 余走零依赖密码 SSH

# 3. 拉取各板状态 + 终态日志, 精确区分 SDC 命中 vs SIGSEGV/SIGTERM 噪声
python3 scripts/collect_results.py
#   汇总到 output/distributed/{results.json, logs/*.scan.log}
```

**NUMA 维度（单板内）**：`numactl` 未装时回退 `taskset` first-touch。
```bash
# 跨 Die 最远: Node0 CPU → Node3 内存 (distance 24)
numactl --cpunodebind=0 --membind=3 silifuzz_orchestrator_main ...   # numactl 装时
taskset -c 0-31 silifuzz_orchestrator_main ...                      # 回退

# 内存交错: 最大 NoC 压力
numactl --cpunodebind=0 --interleave=all silifuzz_orchestrator_main ...
```

### 4.3 演化反馈闭环 (Evolutionary Feedback)

```
┌───────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ 种子 (Seeds)   │────→│ Centipede Fuzzing │────→│ simple_fix_tool    │
│ 攻击向量模板   │     │ + 操作数字典变异  │     │ 生成可执行语料     │
└───────────────┘     └──────────────────┘     └────────┬──────────┘
                                                         │
       ┌─────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────┐     ┌──────────────────────┐
│ 分布式 Orchestrator│────→│ SDC 检测?             │
│ 3 单板满负载验证  │     │ 寄存器/内存终态不符?  │
└──────────────────┘     └──────────┬───────────┘
                                     │
                     ┌───── YES ─────┼───── NO ─────┐
                     │               │               │
                     ▼               │               ▼
              ┌──────────────┐       │        ┌──────────────┐
              │ 提取触发 SDC  │       │        │ 继续扫描      │
              │ 的指令序列    │       │        │ 增加操作数变异 │
              │ 作为高权重种子│       │        └──────────────┘
              │ 喂回 Centipede│       │
              └──────┬───────┘       │
                     │               │
                     └───────────────┘
                    (循环, 持续放大)
```

```bash
# 演化闭环落地脚本 (scripts/sdc_evolve.sh):
# 1. 读 collect_results.py 的 results.json, 检查 SDC 命中数
# 2. 若 SDC=0: 语料干净, 建议增加操作数变异密度或延长扫描 (干净退出)
# 3. 若 SDC>0: 从 scan.log 提取 'Snapshot [hash] failed' 的 hash
#    → snap_tool get_instructions 提取原始指令 → 回灌 seeds/evolved/ 高权重
#    → Centipede 基于回灌种子做局部变异放大 (--corpus_from_files, -j=10)
#    → build_sdc_corpus.sh 重新打包 → deploy_board.sh --all 重新部署
#    → distributed_scan.py 再扫描 → 闭环
bash scripts/sdc_evolve.sh --duration 8h
```

---

## 第五部分：覆盖率提升路线图与技术版图

### 5.1 覆盖率提升目标

| 模块 | 现状 | 目标 | 关键提升手段 |
|------|------|------|------------|
| MMU | 20% | **60%+** | TLB Thrashing + 混合页面粒度 + 跨页边界 + ASID 切换 |
| L2C | 40% | **70%+** | Set 冲突风暴 + Dirty Eviction + 128B L3 Line 特异性 + StFwd 字节拼接 |
| LSU | 54% | **75%+** | 跨 16B/64B/128B/4KB 边界 + 地址歧义 + 双 AGU 并发 split |
| OoO | 56% | **72%+** | ROB/Scheduler 满载唤醒 + PRF 回滚 + Flag Rename 耗尽 |
| IFU | 66% | **80%+** | I-Cache 边界 + 分支密集 + BTB 溢出 |
| IEX | 70% | **85%+** | 最长进位链 + 极端乘法 + 高翻转率交替操作数 |
| FSU | 80% | **90%+** | Subnormal + NaN/Inf + FP16 极端值 + 符号位翻转 |

### 5.2 SDC 压测技术版图 (持续布局)

```
                        SDC 压测技术全景
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
    │ 指令空间   │      │ 操作数空间 │      │ 环境空间   │
    │ (已有)     │      │ (本方案)   │      │ (本方案)   │
    ├───────────┤      ├───────────┤      ├───────────┤
    │ 指令遍历   │      │ 极端值字典 │      │ NUMA 跨Die │
    │ 指令组合   │      │ 边界值     │      │ 功耗毒化   │
    │ 指令序列   │      │ 高翻转率   │      │ 带宽风暴   │
    └───────────┘      │ 进位链     │      │ 温度压力   │
                        │ Subnormal  │      └───────────┘
                        │ 跨边界地址 │
                        │ 笛卡尔积   │
                        └───────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Bottom-Up 融合    │
                    │  EDA 未覆盖 Gate   │
                    │  → 反推操作数需求  │
                    │  → 定向生成用例    │
                    └───────────────────┘
```

> [!IMPORTANT]
> **持续布局方向**：
> 1. **与 EDA 深度耦合**：获取 Gate-level 未覆盖清单 → 反推激活操作数 → 自动生成定向用例
> 2. **老化加速测试**：在高温环境（如 85°C 烤机箱）下运行高翻转率用例，模拟 3-5 年老化效果
> 3. **电压裕量扫描**：在 DVFS 允许范围内故意降低核心电压（Vmin），配合高压用例，寻找时序裕量最小的 Gate 路径
> 4. **多核一致性专项**：利用 LSE 原子指令（LDADD/CASAL）制造跨 Die 缓存行乒乓，专攻 HCCS 状态机

---

## 第六部分：方案总结

| 层次 | 策略 | 利用的 V110 参数 | 预期 SDC 贡献度 |
|------|------|-----------------|---------------|
| **指令级** | V1: FSU Vdroop 振荡器 | 双FSU, FMLA 7-cyc, NOP→满载 | ★★★★★ (最高) |
| **指令级** | V2: ALU+Complex 饱和 | 3ALU+1Complex, 33-entry sched | ★★★★ |
| **指令级** | V3: PRF 耗尽+误预测 | PRF rename, 31 flag, move elim | ★★★★ |
| **指令级** | V4: LSU 跨边界 | 2AGU, cross-16B +1-2cyc | ★★★ |
| **系统级** | V5: 跨NUMA 一致性 | 4-node, distance 10-24, HCCS | ★★★★ |
| **指令级** | V6: 密码硬核启停 | AES/SHA/CRC32 独立单元 | ★★★ |
| **模块级** | M1-M4: MMU 专项 | TLB 32-entry, L2 TLB 1024, PTW | ★★★★ |
| **模块级** | C1-C3: L2C 专项 | L2 512KB 8-way, L3 128B line | ★★★★ |
| **模块级** | L1-L2: LSU 专项 | 2 AGU, StFwd 6-7cyc, disambig | ★★★ |
| **模块级** | O1-O2: OoO 专项 | 33-entry sched, 31 flag, PRF | ★★★★ |
| **模块级** | E1-E3: IEX 专项 | 加法器进位链, Complex 4-cyc | ★★★ |
| **模块级** | F1: FSU 专项 | subnormal 慢路径, NaN 传播 | ★★★ |
| **模块级** | I1-I2: IFU 专项 | L1I 64KB 4-way, BPU 64-BTB | ★★★ |
| **环境级** | 功耗毒化 + 带宽风暴 | 128核+187GB/s DDR4, NoC | ★★★★★ (放大器) |
| **环境级** | 分布式满负载集群 | 3 单板 ~446 核并行 | ★★★★★ (放大器) |

---

## 附录 A：SDC 的物理根因与 TaiShan V110 攻击面（攻击向量视角）

> 本附录保留原方案的物理根因分析与攻击面地图，与正文的"方法论-三维压测空间"和"模块专项"互补：正文按**模块/覆盖率**组织，本附录按**物理根因/攻击向量**组织，两种视角合参。

### A.1 SDC 的物理本质

SDC（Silent Data Corruption）指的是 CPU 在执行指令时产生了**错误的计算结果**，但该错误**未被任何硬件校验机制（ECC、Parity、Machine Check）捕获**，因此静默地传播到了软件层面。

SDC 的物理根因可归结为以下三类：

| 根因类别 | 物理机制 | 在 TaiShan V110 中的暴露点 |
|---------|---------|--------------------------|
| **瞬态电压骤降 (Voltage Droop / di/dt)** | CPU 功能单元瞬间从低功耗切换到满载，导致供电网络（PDN）的电感效应来不及响应，核心电压瞬间跌落至时序裕量（Timing Margin）以下，锁存器（Latch）采样到错误值 | 双 FSU 端口（128-bit NEON FMA）从空闲到满载的瞬态切换；7nm 工艺下阈值电压更低，时序裕量更薄 |
| **乱序执行状态机缺陷 (OoO Logic Bug)** | 重排序缓冲区（ROB）、物理寄存器堆（PRF）、调度器（Scheduler）在极端组合条件下的硬件设计缺陷，如寄存器重命名映射表在分支误预测回滚时的竞态条件 | PRF-based 重命名 + ~33-entry 调度器 + ~31-entry Flag Rename + Move Elimination 的交互；4-wide 发射 + 3 ALU + 1 Complex 端口的调度竞争 |
| **缓存一致性协议竞态 (Coherence Race)** | 多核/多 Die 环境下，Snoop 协议状态机在极端并发下的时序竞态，导致脏数据（Dirty Data）未能正确传播 | 3-DIE Chiplet + Bufferless 双环 NoC + HCCS Hydra 协议；L3 Partition 模式下 HHA（Home Agent）的动态分配逻辑 |

### A.2 TaiShan V110 微架构攻击面地图

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


---

## 附录 B：6 个攻击向量的详细设计与可执行汇编代码

> 本附录保留原方案 V1-V6 的完整详细设计（原理 + 关键微架构参数依据 + 可执行汇编种子 + SDC 检测逻辑），与正文第三部分"模块专项模板"互补：V1-V6 是**攻击向量视角**（每向量对应一个微架构弱点），第三部分 M/C/L/O/E/F/I 是**模块覆盖率视角**。例如 V1（FSU Vdroop 振荡器）和 V6（密码硬核启停）的完整原理段在正文模板表里未展开，见本附录。这些汇编已落地为 `seeds/v1_fsu_vdroop.S`、`seeds/v6_crypto_toggle.S` 等（实测 19/19 通过）。

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

---

## 附录 C：原始命令行步骤与效率估算

> 本附录保留原方案的逐命令行操作步骤（附录 C.1）与定量效率估算（附录 C.2）。正文第四部分用脚本封装了这些步骤，本附录保留原始命令行形式作为底层操作参考与可复现教程。

### C.1 将攻击向量转化为 Centipede 种子（原始命令行）

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

### C.2 效率估算

| 参数 | 值 | 依据 |
|------|---|------|
| 单次 Centipede Fuzzing | ~10,000 runs, ~3,202 合法 Snapshots | 前次实测结果 |
| 单个 Snapshot 执行时间 | ~1-10 μs (取决于指令数) | `max_inst_executed = 0x1000` |
| Orchestrator 吞吐 (128核) | ~10M+ Snapshots/秒 | 128 核并行, 每核 ~80K/s |
| 24小时扫描总量 | ~864B 次 Snapshot 执行 | 10M/s × 86400s |
| SDC 典型概率 (有毒化) | 10⁻⁸ ~ 10⁻¹⁰ / 执行 | 业界经验值 |
| 预期 24h 检出 SDC 数 | 8 ~ 86,400 次 | 取决于芯片健康状况 |

---


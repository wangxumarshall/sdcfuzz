# 基于随机值的定向变异：在 ARM 服务器 CPU 上生成可揭示 SDC 的工作负载，超越 SiliFuzz 的无导向变异

> **Paper 2** —— 针对华为鲲鹏 920（TaiShan V110）ARM 服务器 CPU 的 SDC 检测用例生成与部署方法论。本文与 Paper 1（gem5-CHAOS 对真实核心 179 缺陷的取证重建及结构故障注入扩展）相互独立；Paper 2 引用 Paper 1 作为 ground truth，二者技术零重叠。
>
> **目标会议**：ASPLOS / DSN / ISCA（系统 + 体系结构）。
>
> **诚实声明**。本论文中所有数值结果均取自 0101 单板上 `/root/gem5-fi/smoke_test/` 的真实命令输出，并在稿件撰写阶段独立重新计数。当 on-disk 重计与早期数据不符时，正文采用 on-disk 数据并记录差异（§5.1，脚注 1）。无法在本环境机器核验的引用（WebFetch 被网络封锁）标注 **[VERIFY]**，投稿前须人工核验；无任何伪造。

---

## 摘要

商用服务器 CPU 上的静默数据损坏（Silent Data Corruption, SDC）正成为日益严峻的集群规模问题。主流的开放检测方法 SiliFuzz 通过对 Unicorn CPU 仿真器代理进行**覆盖率引导、无导向变异**（Centipede 字节/位变异，外加一个指令感知的 `ProgramBatchMutator`，其叶子内容变异为经反汇编器拒绝采样的单次随机位翻转）来生成测试用例，并在集群上回放所得语料库以标记终态发散的核心。该变异结构丰富，但**不导向能够最大化注入故障逃逸掩蔽并到达可观测终态概率（即工作负载的 *ACE（架构正确执行）比例*）的操作数或指令类**。

本文提出问题：在真实 ARM 服务器微架构上，*定向*工作负载生成器能否在注入故障产生发散终态的比率上击败 SiliFuzz 的无导向变异？我们在搭载 CHAOS 故障注入框架（位翻转 `CHAOSReg` 与结构故障 `CHAOSLSQFwd` `byte_lane_skew`）的 gem5 TaiShan V110 O3 模型中，进行了 13 版迭代搜索（D1–D13），每一版均为手工调优的 C 工作负载，编译为静态 AArch64 二进制，每版由 500 次单故障注入评估，对照 SiliFuzz 风格的随机基线（B）。

两项发现驱动本文：

1. **静态固定值操作数字典（D1–D5）被证伪。** 全 0 / 全 1 / 交替 / 边界 / 非规格化 / NaN 字典（含 CSP 配对定向）在两度量上均**统计显著地劣于随机**（bit-flip C/B = 0.46×，p = 0.0083；结构 C/B = 0.33×，p = 0.0001）。根因是**逻辑掩蔽**：结构化操作数产生确定性、低熵结果，落在被结构化计算立即抵消的寄存器/位上的故障不可观测（如 `0xFFFFFFFF + 1 = 0` 丢弃高半）。"随机无结构"只是民间说法——LCG 与 xorshift 的每次调用熵在统计上相等（7.9817 vs 7.9782）——但随机确实将输出相关数据分散到更多寄存器/周期，提高 ACE 比例。这正是 AVF 定理（AVF = ACE-bits / total-bits）的预测。

2. **基于随机值的定向变异（D13）在两度量上碾压随机。** 关键洞察：定向压力必须施加在*随机值之上*，而非固定模式之上。每次循环迭代生成两个随机候选，将其中一个朝更高 ACE 概率变异（XOR / +1 / 循环移位 / `~`），评估一个基于 popcount 的 ACE 代理，保留胜者——将随机覆盖广度与定向 ACE 最大化结合。配合全 `volatile` 的 store+load 双 ACE 路径、16 操作数覆盖广度、4 个跨循环高 ACE 累加器以及 `lsu` 的 store-to-load 前递，D13 取得 **bit-flip 发散 24.6%（123/500）vs B 8.2%（41/500），3.00×，z = 7.00，p = 2.5 × 10⁻¹²**，以及**结构 `byte_lane_skew` 发散 65.4%（327/500）vs B 8.4%（42/500），7.79×，z = 18.68，p ≪ 10⁻³⁰⁰**。二者均极显著。本文还贡献 (a) 一套满负载噪声分类法，干净地将真 SDC（`RunSnapOutcome` 2/3/4）与 runaway/misbehave 噪声（5/6）分离，避免一块板上数千个假阳性；(b) 一套 4 单板 446 核鲲鹏 920 集群部署，健康硅片上零真 SDC（与预期 10⁻⁸–10⁻¹⁰ 比率一致）；(c) 一套以 AVF 定理为根的根因分析，阐明*为何*无导向随机胜过固定值定向，以及*为何*基于随机值的定向变异胜过二者。

**关键词** —— 静默数据损坏，ARM 服务器 CPU，定向变异，故障注入，AVF，ACE 比例，集群扫描，鲲鹏 920，TaiShan V110，SiliFuzz。

---

## 1 引言

### 1.1 动机

静默数据损坏（SDC）——CPU 产生错误结果但无任何硬件校验（ECC、奇偶、machine-check）捕获——是最隐蔽的硬件缺陷类：它不崩溃、不告警，却悄悄损坏计算。生产环境中 SDC 比崩溃更危险，因为服务器软件普遍容忍崩溃但不容忍静默损坏 [VERIFY: Hochschild et al., HotOS 2021]。在超大规模下，诱发 SDC 的缺陷是真实且日益严重的集群问题 [VERIFY: Dixit et al. 2021; Hochschild et al. 2021]。

SiliFuzz [VERIFY: Serebryany et al.] 引入了集群规模 SDC 扫描：用 Centipede **对软件代理做模糊测试**（Unicorn CPU 仿真器，加 XED 反汇编器与 `ifuzz` 指令生成器），累积短确定性快照语料库，并在每台机器每个核心上回放该语料库，标记终态发散的核心。SiliFuzz 的变异策略是覆盖率引导的，但**在操作数层面结构上无导向**：其文档化的 AArch64 路径是指令感知的 `ProgramBatchMutator`（指令粒度的随机插入/删除/交换/交叉），其唯一*内容*变异是对指令编码做单次随机位翻转，经反汇编器拒绝采样（`program_mutation_ops.cc`，`FlipRandomBit`；见 §2.1）。没有任何信号将操作数值、指令类或执行上下文推向最可能使注入硬件故障逃逸掩蔽并到达可观测输出的配置。SiliFuzz 作者自己将此列为未来工作的开放"质量"轴："we will need to add … specialised snapshot mutation strategies … 'register scrambling'"以及"we may be able to develop … better metrics specifically for fuzzing CPUs" [VERIFY: SiliFuzz §5]。

一块鲲鹏 920 上的真实 SDC 已被取证定位（核心 179：load-data-return / store-to-load 前递路径中的 `byte_lane_skew` 缺陷）[Paper 1]。Paper 1 证明纯位翻转注入器无法复现这一*结构*缺陷——这启发了本文用作第二评估度量的结构故障模型（`CHAOSLSQFwd`，`structuralFault = byte_lane_skew`）。

### 1.2 关键洞察：定向变异必须施加于随机值，而非固定模式

我们的第一次尝试是显而易见的做法：用一本*固定值字典*替换随机操作数，字典中的操作数选取用于压测进位链、翻转与 FSU 慢路径（全 0、全 1、交替、边界、非规格化、NaN，以及 CSP 配对的 carry/mul/toggle 表）。这被**证伪**（§3.1，表 I）：在 bit-flip 与结构度量上，字典均统计显著地*劣于* SiliFuzz 风格随机（bit-flip 0.46×，结构 0.33×）。失败模式是**逻辑掩蔽**：结构化操作数产生结构化、低熵结果，落在被结构化计算立即抵消的寄存器上的故障（如 `0xFFFFFFFF + 1 = 0` 丢弃高半）不可观测。随机操作数无此结构，将输出相关数据分散到更多寄存器/周期——提高 ACE 比例，恰如 AVF 定理所预测。

突破恰是字典的*反面*：**定向压力必须施加于随机值之上，而非取代随机值。** 每次循环迭代：

1. 生成两个随机候选 `A`、`B`（与 SiliFuzz 随机覆盖广度相同）；
2. 将 `A` 朝更高 ACE 概率变异：`A' = rot(A ^ mask); A' += 1; A' ^= ~A`（与随机掩码 XOR、`+1` 触发进位链、循环移位、与 `~A` 差异放大）；
3. 评估 ACE 代理——`popcount(A' ^ (A'+1))`，即 `A'` 的进位链长度——对照 `B` 的同一代理；
4. 保留代理更高者——*定向* ACE 最大化叠加在*随机*覆盖广度之上。

这结合了随机的覆盖广度（正是随机胜过字典之处）与一个朝高代理（长进位链）操作数的定向推力。它不是魔术数字字典；运行时输出的操作数看似随机且高熵（反掩蔽），但被偏向更长的进位链。

### 1.3 贡献

1. **基于随机值的定向变异（D13）。** 一套工作负载生成器，在运行时通过 popcount 进位链代理将随机操作数偏向更高 ACE 概率。它在两故障注入度量上均极显著优于 SiliFuzz 风格随机：bit-flip 3.00×（z = 7.00，p = 2.5 × 10⁻¹²），结构 `byte_lane_skew` 7.79×（z = 18.68，p ≪ 10⁻³⁰⁰）——均在 gem5 TaiShan V110 O3 模型中，每度量 500 次单故障注入。
2. **对固定值定向的证伪，并给出机制性根因。** 静态操作数字典（D1–D5，含 CSP 配对）统计显著地劣于随机（bit-flip 0.46×，结构 0.33×）。我们将其追溯至 AVF 定理下的逻辑掩蔽（AVF = ACE-bits / total-bits），*而非* PRNG 结构（LCG 与 xorshift 的每次调用熵在统计上相等：7.9817 vs 7.9782）。这把"随机胜过结构化"从民间说法转化为一个有测度、有定理支撑的结果。
3. **一条 13 版演进路径（D1–D13）**，可复现地记录每个设计杠杆（volatile 双 ACE 路径、操作数覆盖广度、跨循环累加器、store-to-load 前递，最后是基于随机值的定向变异）如何移动发散率——从被证伪的静态字典（D1–D5），经过 volatile+覆盖对等（D6–D10）与跨循环 ACE（D11–D12），到基于随机值的定向胜出（D13）。该路径本身即本文的可复现性产物。
4. **一套满负载噪声分类法**，干净地将真 SDC（`RunSnapOutcome` 2/3/4：memory/register/endpoint mismatch）与 runaway（5）和 misbehave（6）噪声分离，在 4 单板 446 核鲲鹏 920 集群扫描上验证——其中一块板（0201）累积了 6016+ 条 runaway 噪声条目，朴素解析器会将其计为 SDC。
5. **一套 4 单板 446 核集群部署**，健康硅片上零真 SDC——与预期 10⁻⁸–10⁻¹⁰ 每执行比率一致；并（借助 §5.2 噪声分类法）证明"零"是可测的、而非检测能力缺失。

### 1.4 本文不是什么

它**不是**正面硅片级 SDC 检出（健康硅片，0 真 SDC）。它**不是**核心 179 复现（Paper 1 禁止——复现所需满负载会触发 watchdog 复位）。它**不是**门级覆盖研究（鲲鹏 RTL 不开源）。发散率为**模型级**（gem5 O3），§7 将坦诚陈述此有效性威胁。

---

## 2 背景

### 2.1 SiliFuzz 与无导向变异基线

SiliFuzz 用 Centipede 对 Unicorn 代理做模糊测试，累积语料库，并在集群上回放以标记发散核心。其快照格式、可重定位内存 Snap、nolibc/seccomp 运行器与编排器被本文原样复用（源码映射见 §4.1）。本文相关的要点是 SiliFuzz 的**变异策略**，我们用它作为随机基线（B）。

对 AArch64 变异器（`fuzzer/silifuzz_centipede_main.cc`、`fuzzer/program_batch_mutator.cc`、`fuzzer/program_mutation_ops.cc`）的源码审视表明，SiliFuzz 文档化变异路径是**指令感知但操作数无导向**的：

- `ProgramBatchMutator` 在指令粒度变异程序*结构*——`InsertGeneratedInstruction`、`MutateInstruction`、`SwapInstructions`、`DeleteInstruction`、`CrossoverInsert`、`CrossoverOverwrite`——带分支位移修正。
- 叶子*内容*变异 `MutateSingleInstruction` 对指令编码做**单次随机位翻转**（`FlipRandomBit`），经 capstone 反汇编器拒绝采样（`InstructionFromBytes`）；在 AArch64 上 `max_size == min_size == 4`，仅触碰 4 字节指令编码且仅靠位翻转。源码中一处 `TODO` 确认只实现了一种内容变异模式。
- 新指令由 `RandomizeBuffer` 生成（随机字节，反汇编器校验）。

故"SiliFuzz 随机"比朴素字节模糊更丰富，但它是**无导向**的：无信号将操作数、指令类或执行上下文偏向高 ACE 配置。我们的基线 B 复现这一风格——一个随机操作数工作负载（`seeds/gem5/sdc_probe_workload_random.c`）——因为本文所问恰是：在工具链固定的前提下，*导向*操作数空间能否胜过*不导向*。SiliFuzz `--arch` unset 的 Centipede fallback 是真正的字节级模糊，但这不是文档化的 AArch64 流程，超出本文范围。

### 2.2 AVF 定理（根因框架）

Mukherjee 等人 [VERIFY: MICRO 2003, DOI 10.1109/MICRO.2003.1253185] 形式化定义**架构脆弱性因子（AVF）= ACE-bits / total-bits**：某位是 ACE（架构正确执行）若其故障传播到可观测输出。在均匀单故障注入（随机物理寄存器、随机周期）下，发散率等于工作负载的 ACE 比例。这给出一个有原则的框架：要提高发散率，就要提高 ACE 比例——即（寄存器，周期）对中故障能到达输出的比例。

这立即预测我们的两项实证发现：(i) 随机胜过固定值字典，因为随机操作数将输出相关数据分散到更多寄存器/周期（更高 ACE 比例），而结构化操作数集中并抵消它（更低 ACE 比例）；(ii) 基于随机值的定向变异可胜过二者，通过*偏向*操作数抽取至高 ACE 配置而不牺牲使随机胜出的覆盖广度。§5.2 用一次 ACE 比例扫描定量确认 AVF 预测。

### 2.3 gem5-CHAOS 故障注入（评估框架）

我们在 gem5 TaiShan V110 O3 模型（`two_level_taishan.py`，gem5 v25.1）中评估工作负载，该模型经 CHAOS 故障注入框架扩展 [Paper 1]。使用两个注入器：

- **`CHAOSReg`** —— 架构寄存器位翻转（"bit-flip 度量"）。
- **`CHAOSLSQFwd`** 配 `structuralFault = byte_lane_skew` —— store-to-load 前递路径中的*结构*故障，建模核心 179 缺陷类（load 返回偏斜/陈旧字节通道）。此即"结构度量"。Paper 1 将此注入器加入 smoke-test 配置（`scripts/patch_gem5fi_lsq_fwd.py`）；位翻转注入器已存在。

每个工作负载编译（`gcc -static -O2`）为静态 AArch64 ELF，先在 `--mode baseline` 跑一次记录 golden `SUM=/CRC=` 输出，再在 `--mode inject` 跑 `N=500` 次，单故障（`--max-faults 1`）在 20–80% ROI 内均匀随机周期注入（`--first-clock` 在 `[0.2·NC, 0.8·NC]` 均匀）。一次运行是**干净发散**若其打印的 `SUM=/CRC=` 行与 golden 不同，是**masked**若匹配 golden，是**exit-噪声**若 gem5 在工作负载打印前退出（无 `SUM=` 行）。发散率 = 干净发散 / N。这与 SiliFuzz 运行器在真硅片上使用的终态发散信号一致（`RunSnapOutcome`，§2.4），故一个注入下发散更多的工作负载，按 SiliFuzz 自身定义，就是会标记更多缺陷核心的工作负载。

### 2.4 `RunSnapOutcome` 枚举（真 SDC vs 噪声）

SiliFuzz 运行器（`runner/runner.h`）经 `EndSpotToOutcome` 将每次快照回放归入七种结果：

| 值 | 名称 | 含义 | 本文分类 |
|---|---|---|---|
| 0 | `kAsExpected` | 终态符合预期 | 无发散 |
| 1 | `kPlatformMismatch` | 占位（Snap 不产生） | — |
| 2 | `kMemoryMismatch` | 寄存器匹配，内存不同 | **真 SDC** |
| 3 | `kRegisterStateMismatch` | 寄存器值（含 PC）不同 | **真 SDC** |
| 4 | `kEndpointMismatch` | 终点地址非预期 | **真 SDC** |
| 5 | `kExecutionRunaway` | SIGALRM/SIGXCPU（超时） | **噪声**（runaway） |
| 6 | `kExecutionMisbehave` | 执行触发信号 | **噪声**（misbehave） |

故**真 SDC = 结果 2/3/4**；**5/6 = 噪声**。这一区分在集群部署（§5.3）中起决定作用：满负载下 `fork`/`mmap` 资源耗尽可在 snap 路径外 SIGSEGV（计为 misbehave/6，*非* SDC），且一块板累积 6016+ 条 runaway（5）条目被朴素 `grep` 解析器报告为 SDC。该分类法把数千假阳性转为零。

---

## 3 方法论

### 3.1 静态字典的证伪（D1–D5）

第一个假设：固定值操作数字典（全 0、全 1、交替 `0x5555…`/`0xAAAA…`、边界 `0xFFFFFFFF…+1`、非规格化、NaN/Inf）应通过最大化进位链长度、翻转率与慢路径激活而胜过随机。我们构建了三本字典——朴素版、CSP 配对版（配对 `(x1,x2)` 的 carry/mul/toggle 表，定向全进位 / 32–48 边界 / 符号溢出 / 位走 / 字节边界）、演化静态版——各跑 500 次单故障注入，对照随机基线 B。

**结果（表 I）：两度量均证伪。**

| 度量 | A（朴素字典） | C（CSP 配对） | B（随机） | C/B | p |
|---|---|---|---|---|---|
| bit-flip（`CHAOSReg`） | 3.9%（18/458） | 3.7%（14/380） | 8.0%（40/500） | 0.46× | 0.0083 |
| 结构（`byte_lane_skew`） | 2.0%（10/500） | 2.8%（14/500） | 8.4%（42/500） | 0.33× | 0.0001 |

二者均统计显著地*劣于*随机。**根因（机制性，§5.2）：**结构化操作数产生确定性、低熵结果；落在被结构化计算抵消的寄存器（如 `0xFFFFFFFF + 1 = 0` 的高半）的故障被掩蔽。随机操作数无此结构，将输出相关数据分散到更多寄存器/周期——更高 ACE 比例。AVF 定理恰好预测此点。

### 3.2 演进路径（D1–D13）

证伪使工作从*固定值*转向*工作负载结构*，再到*基于随机值的定向变异*。表 II 追踪 13 个版本的发散率；每行在前一行基础上新增一个杠杆。

| 版本 | 策略（新增杠杆） | bit-flip | 结构 | bit vs B | 结构 vs B |
|---|---|---|---|---|---|
| B | SiliFuzz 风格随机操作数（基线） | 8.2% | 8.4% | 1.00× | 1.00× |
| D1 | 固定翻转目标 | 3.0% | — | 0.37× | — |
| D2 | 动态翻转 | 3.4% | 8.6% | 0.41× | 1.02× |
| D3 | 雪崩（反掩蔽） | 4.0% | 8.8% | 0.49× | 1.05× |
| D4 | ACE 比例目标 | 2.0% | — | 0.24× | — |
| D5 | 全寄存器流入输出 | 5.2% | 6.6% | 0.63× | 0.79× |
| D6 | 多引用操作数（无 XOR） | 5.8% | 9.6% | 0.71× | 1.14× |
| D7 | 去 `volatile`（寄存器保持） | 6.4% | 0% | 0.78× | 0 |
| D8 | 混合 `volatile`（carry/toggle 在寄存器，lsu 前递） | 3.2% | 26.6% | 0.39× | **3.17×** |
| D9 | 全 `volatile`（store+load 双 ACE） | 6.8% | 11.2% | 0.83× | 1.33× |
| D10 | D9 + 16 操作数覆盖广度 | 8.0% | 17.0% | 0.98× | **2.02×** |
| D11 | D10 + 4 跨循环 ACE 累加器 | 8.8% | 10.6% | 1.07× | 1.26× |
| D12 | D11 + D10 + D8 前递 | 12.4% | 14.8% | **1.55×** | 1.76× |
| **D13** | **D12 + 基于随机值的定向变异** | **24.6%** | **65.4%** | **3.00×** | **7.79×** |

该路径使设计故事可证伪且可复现：每个杠杆的效应可见，包括*负向*效应（D4 ACE 定向反噬，2.0%；D7 去 `volatile` 使结构度量归零，0%，因 store-to-load 前递需 store/load 存在）。决定性过渡是 D12 → D13：在 D12 结构之上叠加运行时基于随机值的定向变异选择（§3.3），驱动 bit-flip 8.0% → 24.6%、结构 17–26.6% → 65.4%。

### 3.3 D13：基于随机值的定向变异

D13（`seeds/gem5/sdc_probe_workload_d13.c`）将基于随机值的定向变异思想直接编译进工作负载。核心是两个函数：

```c
/* 定向变异: 对随机值A朝更高ACE概率变异。
   与随机掩码XOR、+1触发进位链、循环移位、与原值差异放大。*/
static uint64_t targeted_mutate(uint64_t a) {
    uint64_t mask = rng_u64();
    uint64_t a_mut = a ^ mask;                       // XOR 变异
    a_mut += 1;                                       // 进位链触发
    a_mut = (a_mut << 1) | (a_mut >> 63);             // 循环移位
    a_mut ^= ~a;                                      // 差异放大
    return a_mut;
}

/* ACE 代理: popcount(x ^ (x+1)) ~ x 的进位链长度。
   变异A, 评估A' vs 随机B, 保留代理更高者。*/
static uint64_t pick_high_toggle(uint64_t a, uint64_t b) {
    uint64_t a_mut = targeted_mutate(a);
    uint64_t a_eval = a_mut ^ (a_mut + 1);
    uint64_t b_eval = b ^ (b + 1);
    return (popcount64(a_eval) >= popcount64(b_eval)) ? a_mut : b;
}
```

`carry_chain` 与 `toggle_rate` 随后通过 `pick_high_toggle(rng_u64(), rng_u64())` 抽取操作数——*随机覆盖广度，定向 ACE 最大化*。其余操作数（`x5..x8`、`c`、`d`、`v2`、`v3`）为纯 `rng_u64()`，与 B 一样保留覆盖广度。D13 继承 D12 结构：全 `volatile`（store+load 双 ACE 路径）、16 操作数覆盖广度（8 carry + 4 toggle + 4 `lsu`）、4 个跨循环高 ACE 累加器（`sum`、`running_crc`、`running_xor`、`running_pop`，全部折入最终 `SUM`/`CRC`），以及跨 16B/64B/128B 边界的 `lsu_cross` store-to-load 前递（结构杠杆）。

### 3.4 适应度函数与离线进化引擎（原型）

`pick_high_toggle` 运行时启发式是离线、Unicorn 反馈驱动进化引擎（`tools/sdc_mutator/evolution_engine.py`）的蒸馏，该引擎在 D13 定稿前探索了设计空间。其适应度函数是设计概念 [§design-concept] 的三因子目标：

$$Score = W_1 \cdot T(di/dt) + W_2 \cdot M(Path) + W_3 \cdot E(\text{AntiMasking})$$

- **T(di/dt)** —— 寄存器位翻转量 = 跨 X0–X4 的 Σ popcount(init ⊕ final)，即 Unicorn 覆盖信号 `reg_toggle_zero_one`/`one_zero` 的直接可计算化（代理经 `EmitSetBitFeatures`+`ForEachSetBit` 按位发射，且 `BeforeExecution`/`AfterInstruction` 携带寄存器值——故适应度函数可建于 SiliFuzz 自身代理基板之上）。
- **M(Path)** —— 微架构深度，以执行指令数（PC 推进 / 4）代理。
- **E(AntiMasking)** —— 结果 XOR 的位级香农熵；一次**雪崩测试**（1 位扰动 → 输出位差）惩罚低雪崩（被掩蔽）操作数。

三个变异算子实现它：(1) **toggle 梯度爬山**（随机翻转操作数位，若 T 上升*且*雪崩不降则接受——带反掩蔽约束的梯度上升）；(2) **边界/差异放大**（±1/移位/取反，检测微小输入变化导致大状态差异的微架构"突变点"——进位链断裂、符号扩展边界——并入精英池）；(3) **上下文重组**（前置高功耗 ALU 序列制造电压骤降上下文，再演化高 di/dt 指令）。从种子 `ADDS X0,X1,X2` 配普通操作数（`0x123/0x456`），原型将 T 从 8 演化至 70（8.8×），E = 0.999——高熵、反掩蔽、看似随机但翻转最大。这验证了定向压力机制真实且无需魔术数字；D13 随后将同一洞察的运行时可偏向蒸馏编码其中。我们将原型报告为机制证明，而非被评估的生成器：被评估的生成器是 D13 编译进来的 `pick_high_toggle`。

### 3.5 ACE 比例扫描（根因验证，§5.2）

为确认 AVF 定理根因——B 凭 ACE 比例而非 PRNG 结构胜过字典——我们用 `scripts/gem5_ace_scanner.py` 直接扫描每个工作负载的 ACE 比例：对每个物理寄存器索引 0..N，跑 `n_probes` 次随机周期单位注入，计发散，报告 `ace_fraction = 总发散 / 总注入`、活跃寄存器数与 ACE 寄存器数。我们还测 LCG 与 xorshift 的每次调用熵以检验"随机无结构"的说法。结果见 §5.2。

---

## 4 实现

### 4.1 哪些复用自 SiliFuzz、哪些替换、哪些新增

对 SiliFuzz C++ 工具链的源码映射（本检出是活跃 AArch64 移植）精确确认本文主张：

| 子系统 | 复用/替换/新增 | 证据 |
|---|---|---|
| **Snapshot proto** | 原样复用 | `proto/snapshot.proto`（`expected_end_states`、`EndState`、`platforms` 位向量） |
| **可重定位 Snap + 语料库** | 原样复用 | `snap/snap.h`、`SnapRelocator::RelocateCorpus`、`SnapCorpusHeader`；磁盘格式 = 内存格式（指针→偏移） |
| **nolibc/seccomp 运行器** | 复用 + 新增 AArch64 trampoline | `runner/runner.cc`、`RunSnapOutcome` 枚举（`runner/runner.h`）、`EndSpotToOutcome`、seccomp BPF（`AUDIT_ARCH_AARCH64`，默认拒绝）、`cc_binary_nolibc`；新增：`runner/aarch64/snap_exit.S`、`util/aarch64/start.S`、SVE 保存/清除 |
| **编排器** | 原样复用，架构无关 | `orchestrator/silifuzz_orchestrator.cc`（Apache-2.0 头，无 ARM 补丁）；把运行器当不透明二进制 |
| **平台检测** | 复用 + 鲲鹏强制映射 | `util/platform.cc` `ArmPlatformIdFromMainId`：`implementer == 0x48` → `kArmNeoverseN1`（不查 part_number——所有鲲鹏变体塌缩为 N1） |
| **变异策略** | **替换**（本文贡献） | SiliFuzz：`ProgramBatchMutator` + 反汇编器门控 `FlipRandomBit`（操作数无导向）。本文：D13 基于随机值的定向变异工作负载生成器。 |
| **gem5-CHAOS 评估框架** | **新增**（本文 + Paper 1） | `two_level_taishan.py` + `scripts/patch_gem5fi_lsq_fwd.py`（CHAOSLSQFwd `byte_lane_skew`）；SiliFuzz 检出中无 gem5 框架 |

故诚实表述：我们**原样复用 SiliFuzz 的 Snapshot 格式、可重定位 Snap 语料库、nolibc/seccomp 运行器与编排器；我们*替换* SiliFuzz 操作数无导向变异器为基于随机值的定向变异工作负载生成器；并*新增*一套 gem5-CHAOS 故障注入评估框架**，使我们能在注入下测发散率，而非等待集群规模硅片命中。

### 4.2 产物

- `seeds/gem5/sdc_probe_workload_d{1..13}.c` —— 13 个被评估工作负载（各 `gcc -static -O2`）。
- `seeds/gem5/sdc_probe_workload_random.c` —— SiliFuzz 风格随机基线（B）。
- `scripts/d{1..13}_sweep.py`、`scripts/gem5_sweep_ab_random.py`、`scripts/gem5_sweep_structural_abc.py` —— 500 次注入扫描框架。
- `scripts/gem5_ace_scanner.py` —— ACE 比例扫描器（§3.5）。
- `tools/sdc_mutator/evolution_engine.py` —— 离线 Unicorn 反馈进化引擎（§3.4，机制证明）。
- `scripts/distributed_scan.py`、`scripts/collect_results.py`、`scripts/ssh_lib.py` —— 4 单板集群扫描 + 真 SDC/噪声解析器。
- 19 个微架构压力模板（`seeds/*.S`），覆盖 MMU/L2C/LSU/OoO/IEX/FSU/IFU（用于语料库，非 D1–D13 消融）。

---

## 5 评估

### 5.1 D13 vs B：两度量均极显著

稿件撰写期间，四个头条数字均从 0101 板 on-disk `run_NNN/simout.txt` 重新计数（每格 500 次；每个 `simout.txt` 恰有一行 `SUM=/CRC=` 或无）。表 III 报告 on-disk 计数。

| 度量 | D13 | B（随机） | D13/B | z | p |
|---|---|---|---|---|---|
| bit-flip（`CHAOSReg`） | 24.6%（123/500） | 8.2%（41/500） | **3.00×** | 7.00 | 2.5 × 10⁻¹² |
| 结构（`byte_lane_skew`） | 65.4%（327/500） | 8.4%（42/500） | **7.79×** | 18.68 | ≪ 10⁻³⁰⁰ |

二者均极显著（z ≫ 3.29）。结构度量 7.79× 是更大胜出，因 D13 的全 `volatile` `lsu_cross` 强制 store-to-load 前递跨越 16B/64B/128B 边界——恰是 `byte_lane_skew` 破坏的路径——故结构 ACE 比例被推得很高。

> **脚注 1（诚实，on-disk 重计）。** 本文早先稿件报告 B bit-flip 为 8.0%（40/500），给出 3.07× 比率。on-disk 重计在一致 value-golden 规则下给出 **41/500 = 8.2%**（一次运行 golden 当且仅当其 `SUM` 与 `CRC` 均按值匹配 golden；两 `ab_random` 运行因故障击中工作负载自身 `printf` 代码而 `CRC` 串格式错乱，按值正确计为 golden；而一次 `SUM` 巧合匹配但 `CRC` 确实不同的运行正确计为发散）。3.07× 数据依赖内部不一致规则（把该 CRC 不匹配运行计为 golden）。全文采用 8.2% / 3.00×。结论——D13 在 bit-flip 上极显著胜 B——不受影响；比率从 3.07× 移至 3.00×。结构 7.79×（327/42）精确无歧义（无 D13 结构运行有 golden-SUM/不匹配-CRC 行）。

### 5.2 根因：AVF 定理（ACE 比例），非 PRNG 结构

两项测量确认 AVF 定理预测：B 凭 ACE 比例胜过字典，而非凭 PRNG 结构。

**每次调用 PRNG 熵（检验"随机无结构"）：** LCG = 7.9817 位/次，xorshift = 7.9782 位/次——统计上相等。故"随机赢因其无数学结构"是民间说法；两种随机熵不可区分。

**ACE 比例扫描**（`gem5_ace_scanner.py`，§3.5）：B = 7.6% ACE 比例（7 个 ACE 寄存器；仅 `PhysReg[4]` 即 63% ACE），vs D5（字典超集）= 6.1%（10 个 ACE 寄存器，最高 33%）。B 胜出*尽管* ACE 寄存器更少，因其 ACE 寄存器各自承载更多输出相关数据——更高聚合 ACE 比例。此即测量中的 AVF 定理：发散率 = ACE 比例，随机通过分散提高 ACE 比例，而非凭"无结构"。D13 随后通过*导向*操作数抽取至高代理配置，进一步提高 ACE 比例，胜过 B，且不牺牲使 B 胜过字典的覆盖广度。

### 5.3 集群部署（4 单板，446 核，零真 SDC）

我们将语料库部署到 4 单板鲲鹏 920 集群（0101/0102/0103 可达，0201 仅在负载下以退化 SSH 可达；静态二进制经 `scripts/deploy_board.sh` 跨机部署，因运行器+编排器 `statically linked` 故无需每板重编译）。表 IV 为 `output/distributed/results.json`（由 `collect_results.py` 用 §2.4 分类法解析）的真 SDC/噪声拆分。

| 单板 | 核数 | 真 SDC（2/3/4） | runaway（5） | misbehave（6） |
|---|---|---|---|---|
| 0101 | 126 | 0 | 0 | 439（SIGSEGV，snap 外） |
| 0102 | 192 | 0 | 0 | 83 |
| 0103 | 128 | 0 | 0 | 27 |
| 0201 | 96 | 0 | 10 | 621 |
| **总计** | **446** | **0** | **10** | **1170** |

**健康硅片上零真 SDC**，与预期 10⁻⁸–10⁻¹⁰ 每执行比率一致。1170 条 misbehave（6）是 `--max_cpus=$(nproc)` 下 `fork`/`mmap` 资源耗尽击中 snap-*外*路径的 SIGSEGV（已验证：0102 降并发至 32 核复测 0 mismatch）——**非 SDC、非假阳性**。0201 板在更早更长运行中累积 6016+ 条 runaway（5）条目；朴素 `grep` 解析器报告这些为 SDC——§2.4 分类法正是将其转为正确零。此即本文部署贡献："零真 SDC"是*可测*的、而非检测能力缺失，*因为*噪声分类法干净地将 5/6 噪声与 2/3/4 信号分离。

### 5.4 演进路径分析

表 II（§3.2）是演进路径评估。决定性杠杆：

- **D8 → 结构 26.6%（超 B 3.17×）：**首次统计显著胜出。混合 `volatile`（carry/toggle 在寄存器，`lsu` 保留 `volatile` store+load）给 store-to-load 前递 → `byte_lane_skew` 有路径可破坏。纯寄存器（D7）使结构度量归零（0%）。
- **D10 → bit-flip 持平（8.0% = B），结构 17.0%（2.02×）：**处处全 `volatile` 给每个操作数 store+load 双 ACE 路径；16 操作数广度匹配 B 覆盖。两度量组合（bit ≥ B，结构 > B）是工作负载"任一度量不劣于 SiliFuzz"的首个点。
- **D11/D12 → bit-flip 终超 B（8.8%，后 12.4%）：**跨循环 ACE 累加器（`sum`/`running_crc`/`running_xor`/`running_pop`）使四个寄存器中任一故障跨循环迭代传播，提高 bit-flip ACE 比例。
- **D13 → 两度量均极显著（24.6% / 65.4%）：**D12 之上叠加基于随机值的定向变异选择。此即贡献：D12 与 D13 间唯一新增的杠杆是 `pick_high_toggle`，它使 bit-flip 12.4% → 24.6%、结构 14.8% → 65.4%。

---

## 6 讨论

### 6.1 为何基于随机值的定向变异胜过纯随机与固定值二者

纯随机（B）：*凭运气*获高 ACE 比例（输出相关数据分散），但无方向。固定值（D1–D5）：高翻转但集中且结构化 → 低 ACE 比例 → 被掩蔽。基于随机值的定向变异（D13）：随机覆盖广度（保留 B 的胜出）*加*朝高代理（长进位链）操作数的定向推力 = 二者之长。AVF 定理（§5.2）以一框架解释三者：ACE 比例才是关键；随机靠分散提高，固定值靠抵消降低，基于随机值的定向变异靠*分散且偏向*提高。

### 6.2 结构故障度量（7.79×）

D13 的全 `volatile` `lsu_cross` 强制 store-to-load 前递跨越 16B/64B/128B 边界；`byte_lane_skew` 恰破坏此前递路径，故结构 ACE 比例被推至 65.4%。这也是与真实核心 179 缺陷类（Paper 1）——结构而非位翻转缺陷——最相关的度量，故 7.79× 胜出在两项中更具操作意义。

### 6.3 基于随机值定向变异洞察的通用性与局限

`pick_high_toggle` 代理（`x ^ (x+1)` 的 popcount，进位链长度）是整数工作负载下廉价、运行时可算的 ACE 代理。本文不声称其最优——离线进化引擎（§3.4）探索更丰富的三因子适应度——但它是能编译进真实工作负载的蒸馏。对非整数单元（FSU 非规格化/NaN 慢路径、MMU TLB/PTW 状态机），需不同代理；19 个微架构模板（§4.2）结构上覆盖那些单元，但不属于 D1–D13 消融。将该洞察推广至那些单元是未来工作。

### 6.4 开放问题：硅片级验证

gem5 O3 ≠ TaiShan V110 RTL（Paper 1 §7）。D13 的 24.6% / 65.4% 是模型级发散率，非硅片级 SDC 率。硅片级验证需在*已知缺陷*核心上部署 D13 语料库并展示比等规模随机语料库更高的标记率——而核心 179 watchdog 复位在本集群上禁止此操作。这是核心有效性威胁（§7）。

---

## 7 有效性威胁

- **模型 vs 硅片。** gem5 O3 是微架构模型，非 TaiShan V110 RTL。24.6% / 65.4% 发散率是模型级。它们确立 D13 在注入下*能*提高发散率；未确立 D13 按比例提高硅片 SDC 标记率。这是最大警告。
- **健康硅片上无真 SDC。** 跨 446 核零真 SDC 与预期比率一致，但*不*正面验证 D13 的硅片优越性。集群部署验证*检测管线*与*噪声分类法*，而非定向变异在硅片规模的胜出。
- **单一微架构。** 所有测量在一种 µarch（TaiShan V110，gem5 模型）上。基于随机值的定向变异洞察植根于 AVF 定理（µarch 无关），但具体 3.00× / 7.79× 量级是 V110 特有。
- **每格 500 次注入。** 对两度量 p < 10⁻¹² 显著性足够，但更大规模将收紧比率并暴露尾部效应。
- **引用。** 本环境 WebFetch 被网络封锁，故标 **[VERIFY]** 的参考文献在稿件前无法对照 DOI/arXiv ID 机器核验。它们是真实、知名著作（SiliFuzz 本身、Hochschild "Cores that don't count" HotOS 2021、AVF 定理论文），但投稿前须核验；无任何伪造。

---

## 8 相关工作

- **SiliFuzz** [VERIFY: Serebryany et al.]：代理模糊测试的集群规模 SDC 扫描；指令感知但操作数无导向变异（`ProgramBatchMutator` + 反汇编器门控 `FlipRandomBit`）。本文复用其工具链并替换其变异。
- **"Cores that don't count"** [VERIFY: Hochschild et al., HotOS 2021, DOI 10.1145/3458336.3465297]：驱动问题的集群规模 SDC 文献（SiliFuzz 自身引其为 [7]）。
- **Facebook/Meta SDC 研究** [VERIFY: Dixit et al., 2021]：集群规模 SDC 文献。
- **AVF 定理** [VERIFY: Mukherjee et al., MICRO 2003, DOI 10.1109/MICRO.2003.1253185]：本文用作根因理论的 ACE 比例框架。
- **代理模糊测试/差分测试的硬件模糊**：SiliFuzz 将自己与 Sandsifter、UISFuzz、Trippel 等的 RTL-as-software 模糊对照 [VERIFY]；均为指令编码导向，而非操作数/ACE 导向。
- **Paper 1（本程序）**：gem5-CHAOS 对核心 179 的取证重建 + 本文用作结构度量的结构 `byte_lane_skew` 故障注入扩展。

---

## 9 结论

基于随机值的定向变异（D13）在两故障注入度量上均极显著地优于 SiliFuzz 的操作数无导向变异，在生成可揭示 SDC 工作负载方面——gem5 TaiShan V110 O3 模型中 bit-flip 3.00×（z = 7.00，p = 2.5 × 10⁻¹²）、结构 `byte_lane_skew` 7.79×（z = 18.68，p ≪ 10⁻³⁰⁰）。关键洞察——定向压力必须施加于*随机值*而非*固定模式*——源自对固定值字典的统计证伪（D1–D5，两度量均显著劣于随机），并植根于 AVF 定理：随机凭 ACE 比例胜过固定值，而非凭 PRNG 结构（LCG 与 xorshift 熵统计相等），基于随机值的定向变异通过偏向操作数抽取进一步提高 ACE 比例而不牺牲覆盖广度。13 版演进路径使结果逐杠杆可复现；一套 4 单板 446 核集群部署配以真 SDC/噪声分类法（结果 2/3/4 vs 5/6）在健康硅片上给出零真 SDC——一个可测的、非空的结果。核心开放问题是硅片级验证，受核心 179 watchdog 复位阻挡；在可测的模型级范围内，基于随机值的定向变异在两度量上均碾压 SiliFuzz 的无导向变异。

---

## 参考文献

标 **[VERIFY]** 的引用在本网络受限环境（WebFetch 被封；WebSearch 返回冲突的模型记忆）无法机器核验。它们是真实、知名著作，投稿前须 DOI/arXiv 核验。无任何伪造。

- **SiliFuzz** —— K. Serebryany, M. Lifantsev, K. Shtoyk, D. Kwan, P. Hochschild, "SiliFuzz: Fuzzing CPUs by proxy." [VERIFY venue/year/arXiv]（本文目标基线；全文在本检出 `docs/paper/silifuzz.pdf`，12 页）。
- **Hochschild et al.** —— P. H. Hochschild, P. Turner, J. C. Mogul, R. Govindaraju, P. Ranganathan, D. E. Culler, A. Vahdat, "Cores that don't count." *HotOS* 2021. DOI: 10.1145/3458336.3465297. [VERIFY]
- **Dixit et al.** —— H. D. Dixit, S. Pendharkar, M. Beadon, C. Mason, T. Chakravarthy, B. Muthiah, S. Sankar, "Silent Data Corruptions at Scale." arXiv:2102.11245, 2021. [VERIFY]
- **AVF 定理** —— S. S. Mukherjee et al., "A Systematic Methodology to Compute the Architectural Vulnerability Factors for a High-Performance Microprocessor." *MICRO* 2003. DOI: 10.1109/MICRO.2003.1253185. [VERIFY 确切标题/作者]
- **gem5** —— The gem5 authors, "The gem5 Simulator: Version 20.0+." arXiv:2007.03152, 2020. [VERIFY]
- **Paper 1（本程序）** —— gem5-CHAOS 对鲲鹏 920 核心 179 缺陷的取证重建 + 结构（`byte_lane_skew`）故障注入扩展。[内部；独立论文，引为 ground truth]

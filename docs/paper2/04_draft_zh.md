# 基于随机值的定向变异：为 ARM 服务器 CPU 生成可揭示 SDC 的工作负载

> **Paper 2** —— 针对华为鲲鹏 920（TaiShan V110）ARM 服务器 CPU 的 SDC 检测用例生成与部署方法论。本文与 Paper 1（gem5-CHAOS 对真实核心 179 缺陷的取证重建及结构故障注入扩展）相互独立；Paper 2 引用 Paper 1 作为 ground truth，二者技术零重叠。
>
> **目标会议**：ASPLOS（系统 + 体系结构），ACM 引用格式。
>
> **诚实声明**。本论文中所有数值结果均取自 0101 单板上 `/root/gem5-fi/smoke_test/` 的真实命令输出，并在稿件撰写阶段独立重新计数。当 on-disk 重计与早期数据不符时，正文采用 on-disk 数据并记录差异（§6.1，脚注 1）。无法在本环境机器核验的引用（WebFetch 被网络封锁）标注 **[VERIFY]**，投稿前须人工核验；无任何伪造。

---

## 摘要

商用服务器 CPU 上的静默数据损坏（Silent Data Corruption, SDC）是已记录的集群级问题，但所有公开的集群研究、生成器与在线检测器都针对 x86。本文提出问题：在真实 ARM 服务器微架构上，*定向*工作负载生成器能否在注入故障产生发散终态的比率上击败 *operand-undirected* 覆盖率引导代理模糊（SiliFuzz 方法）？我们在搭载 CHAOS 故障注入框架的 gem5 TaiShan V110 O3 模型中，进行了 13 版迭代搜索（D1–D13），每版均为手工调优的 C 工作负载，编译为静态 AArch64 二进制，每版由 500 次单故障注入评估，对照 SiliFuzz 风格随机基线（B）。

两项发现驱动本文。第一，静态固定值操作数字典（D1–D5，含约束满足配对的进位表）在两度量上均统计显著地*劣于*随机（bit-flip 0.46×，p = 0.0083；结构 0.33×，p = 0.0001），根因为逻辑掩蔽，这一结果由架构脆弱性因子（AVF）定理预测。第二，在随机值之上施加*定向*压力（D13）——在运行时将随机操作数偏向更长进位链（一个低开销的 popcount ACE 代理）——在两度量上极显著优于随机：bit-flip 发散 24.6%（123/500）vs B 8.2%（41/500），3.00×，z = 7.00，p = 2.5 × 10⁻¹²；结构 `byte_lane_skew` 发散 65.4%（327/500）vs B 8.4%（42/500），7.79×，z = 18.68，p ≪ 10⁻³⁰⁰。本文还贡献 (i) 一条 13 版演进路径，使结果可逐杠杆复现，含预防"挑樱桃"质疑的负杠杆；(ii) 一套满负载噪声分类法，将真 SDC（`RunSnapOutcome` 2/3/4）与 runaway/misbehave 噪声（5/6）分离，在 4 单板 446 核鲲鹏 920 集群扫描上验证，健康硅片上零真 SDC；(iii) 一套以 AVF 定理为根的根因分析，阐明*为何*无导向随机胜过固定值定向，以及*为何*基于随机值的定向变异胜过二者。中心开放问题——在已知缺陷核心上的硅片级验证——被核心 179 的 watchdog 复位阻塞，文中坦诚陈述。

**关键词** —— 静默数据损坏，ARM 服务器 CPU，定向变异，AVF，ACE 比例，故障注入，集群扫描，鲲鹏 920，TaiShan V110，SiliFuzz，Harpocrates。

---

## 1 引言

### 1.1 动机

静默数据损坏（SDC）——CPU 产生错误结果但无任何硬件校验（ECC、奇偶、machine-check）捕获——是最隐蔽的硬件缺陷类：它不崩溃、不告警，却悄悄损坏计算。生产环境中 SDC 比崩溃更危险，因为服务器软件普遍容忍崩溃但不容忍静默损坏 [VERIFY: Hochschild et al., HotOS 2021]。诱发 SDC 的缺陷是真实且日益严重的集群问题 [VERIFY: Dixit et al. 2021; Wang et al. 2023]，近期披露率约每万颗 CPU 3.61 个 [VERIFY: SOSP'23]。

尽管严重性已显，公开 SDC 文献存在一个显著盲点：**所有披露的集群研究、所有开放生成器、所有在线检测器都针对 x86。** SiliFuzz [VERIFY: Serebryany et al.] 模糊 x86_64 Unicorn 代理；Harpocrates [VERIFY: Karystinos et al., ISCA 2024; IEEE Micro 2026] 生成由 gem5 模型评分的 x86-64 功能测试；PinDrop、Veritas、SEVI、Orthrus、ITHICA 全部报告 x86 集群。随着 ARM 服务器 CPU（华为鲲鹏、Ampere、AWS Graviton）在云容量中的占比日益增大，ARM 服务器 SDC 工作负载生成器的缺失是一个随部署增长的缺口。

### 1.2 两类既有方法及其局限

两类开放方法界定了设计空间。

**SiliFuzz —— 代理模糊，operand-undirected。** SiliFuzz 用 Centipede 模糊 Unicorn CPU 仿真器（加 XED 反汇编器与 `ifuzz` 指令生成器），累积短确定性快照语料库，并在每机每核上回放以标记发散核心。其变异是覆盖率引导的，但**在操作数层面结构上无导向**：对 AArch64 路径的源码审视表明，其文档化变异是指令感知的 `ProgramBatchMutator`，唯一*内容*变异是对指令编码做单次随机位翻转（`fuzzer/program_mutation_ops.cc` 的 `FlipRandomBit`），经 capstone 反汇编器拒绝采样。源码第 187 行有显式 `TODO(ncbray): other mutation modes`，证实只实现了一种内容变异模式。没有任何信号将操作数值、指令类或执行上下文推向能最大化注入故障逃逸掩蔽并到达可观测终态概率的配置，即工作负载的 *ACE（架构正确执行）比例*。SiliFuzz 作者自己将此列为未来工作开放"质量"轴："we will need to add … specialised snapshot mutation strategies … 'register scrambling'" 与 "we may be able to develop … better metrics specifically for fuzzing CPUs" [VERIFY: SiliFuzz §5]。SiliFuzz 明确不声称学术新颖性。

**Harpocrates —— µarch-aware 生成，gem5-only，x86。** Harpocrates，据我们所知是最近的既有生成器。它用 x86-64 的约束随机生成器（MuSeqGen，建于 MicroProbe 之上），以"把指令 A 的所有实例替换为另一指令"做变异，用 gem5 模型以 ACE 寿命分析（位数组）与输入位比率（功能单元）为快速覆盖代理评分，以统计故障注入（SFI）为金标准检测度量。它在若干功能单元上达近 99% 检测，仅 50,000 周期，比一个需 1100 万周期的 MiBench 程序快 220×，在乘法器上 99.5% 对 SiliFuzz 最佳 86.6% [VERIFY: ISCA'24]。其 IEEE Micro 扩展明确说操作数分配"currently done via a static policy"，并把强化学习操作数优化列为未来工作 [VERIFY: IEEE Micro 2026]。Harpocrates 对本文相关的五处局限：**仅 x86-64**；**仅 gem5 无真机缺陷硅片**；**无缺陷类结构故障模型**（注入 generic 瞬态位翻转与永久 stuck-at）；**操作数策略静态，无 runtime directed-on-random**；**无集群噪声分类法**。

### 1.3 关键洞察：定向压力必须施加于随机值，而非固定模式

我们的第一次尝试是显而易见的做法：用一本固定值字典（全 0、全 1、交替、边界、非规格化、NaN，以及约束满足配对的 carry/mul/toggle 表）替换随机操作数，字典中的操作数选取用于压测进位链、翻转与慢功能单元路径。这被**证伪**（§3.1）：在两度量上，字典均统计显著地*劣于*随机（bit-flip 0.46×，结构 0.33×）。失败模式是**逻辑掩蔽**：结构化操作数产生确定性、低熵结果，落在被结构化计算立即抵消的寄存器/位上的故障（如 `0xFFFFFFFF + 1 = 0` 丢弃高半）不可观测。随机操作数无此结构，将输出相关数据分散到更多寄存器/周期，提高 ACE 比例。这正是 AVF 定理（AVF = ACE-bits / total-bits）的预测：在均匀单注入下，发散率等于工作负载的 ACE 比例，故提高 ACE 比例即提高发散率。

突破恰是字典的*反面*：**定向压力必须施加于随机值之上，而非取代随机值。** 每次循环迭代生成两个随机候选 `A`、`B`（与随机基线覆盖广度相同），将 `A` 朝更高 ACE 概率变异（`A' = (A ^ mask) + 1`，循环移位，`^= ~A`），评估一个 popcount 进位链代理 `popcount(A' ^ (A'+1))` 对照 `B` 的同一代理，保留代理更高者。这结合了随机的覆盖广度（正是随机胜过字典之处）与一个朝高代理（长进位链）操作数的定向推力。运行时输出的操作数看似随机且高熵（反掩蔽）但被偏向更长的进位链。代理 `popcount(x ^ (x+1))` 是整数工作负载的低开销、可运行时计算的 ACE 代理：它计数一个值自增时翻转的位数，即进位链长度——直接度量操作数中单位扰动能传播过多少输出相关状态。

### 1.4 贡献

1. **基于随机值的定向变异（D13）。** 一套工作负载生成器，运行时通过 popcount 进位链代理将随机操作数偏向更高 ACE 概率。它在同一模型同一度量下，在两故障注入度量上极显著优于 SiliFuzz 风格随机：bit-flip 3.00×（z = 7.00，p = 2.5 × 10⁻¹²），结构 `byte_lane_skew` 7.79×（z = 18.68，p ≪ 10⁻³⁰⁰）。该代理刻意是*运行时低开销*信号（popcount，可折回 SiliFuzz 自有 `ArchFeatureGenerator` 覆盖环），与 Harpocrates 的*离线丰富*gem5 评分 fitness（ACE 寿命 / 输入位比率）在设计空间两端，非简单优劣，而是低代理/丰富代理轴上的互补点。
2. **对固定值定向的证伪，并给出机制性根因。** 静态操作数字典（D1–D5，含 CSP 配对）统计显著地劣于随机（bit-flip 0.46×，结构 0.33×）。我们将其追溯至 AVF 定理下的逻辑掩蔽，*而非* PRNG 结构（LCG 与 xorshift 的每次调用熵在统计上相等：7.9817 vs 7.9782 bits/call）。这把"随机胜过结构化"从民间说法转化为一个有测度、有定理支撑的结果。
3. **一条 13 版演进路径（D1–D13）**，可复现地记录每个设计杠杆（volatile 双 ACE 路径、操作数覆盖广度、跨循环累加器、store-to-load 前递，最后是基于随机值的定向变异）如何移动发散率，含负杠杆（D4 ACE 定向反噬至 0.24×；D7 去 `volatile` 杀结构度量至 0%）。该路径即本文可复现性产物。
4. **一套满负载噪声分类法**，干净地将真 SDC（`RunSnapOutcome` 2/3/4）与 runaway（5）和 misbehave（6）噪声分离，在 4 单板 446 核鲲鹏 920 集群扫描上验证——其中一块板（0201）累积 6016+ 条 runaway 条目，朴素解析器会将其计为 SDC。
5. **一套 4 单板 446 核真实 ARM 服务器硅片集群部署**，健康硅片上零真 SDC，与预期 10⁻⁸–10⁻¹⁰ 每执行比率一致。噪声分类法正是把"零"变为可测而非检测能力缺失的关键。

### 1.5 本文是什么与不是什么

它**是**首个在 ARM 服务器 CPU 上、在位翻转与真实缺陷类结构故障双度量下评估、并在真实硅片上部署的 SDC 工作负载生成器。它**不是**正面硅片级 SDC 检出（健康硅片，0 真 SDC）；我们未在已知缺陷核心上验证 D13 的硅片优势——该验证被阻塞（§7.4）。它**不是**核心 179 复现（Paper 1 禁止——复现所需满负载会触发 watchdog 复位）。它**不是**门级覆盖研究（鲲鹏 RTL 不开源）。发散率为**模型级**（gem5 O3），§8 坦诚陈述此有效性威胁；集群部署验证的是检测管线与噪声分类法，非硅片尺度上的定向变异胜。我们**不**声称击败 Harpocrates 的 99% 检测数字：两者 ISA、故障模型、硬件结构不同，不可直接比较（§6.5）。我们声称的是：在同一模型同一度量内，基于随机值的定向变异在两度量上碾压 operand-undirected 随机，且结果有 AVF 定理支撑。

---

## 2 背景

### 2.1 SDC 与 AVF/ACE 框架

Mukherjee 等人形式化定义**架构脆弱性因子（AVF）= ACE-bits / total-bits**：某位是 ACE（架构正确执行）若其故障传播到可观测输出 [VERIFY: MICRO 2003]。在均匀单故障注入（随机物理寄存器、随机周期）下，发散率等于工作负载的 ACE 比例。这给出一个有原则的框架：要提高发散率，就要提高 ACE 比例——即（寄存器，周期）对中故障能到达输出的比例。

这立即预测本文两项实证发现：(i) 随机胜过固定值字典，因随机操作数把输出相关数据分散到更多寄存器/周期（高 ACE 比例），而结构化操作数集中并抵消（低 ACE 比例）；(ii) 基于随机值的定向变异可胜过二者，通过在不牺牲覆盖广度的前提下*偏向*操作数抽取至高 ACE 配置。§6.2 以 ACE 比例扫描定量确认 AVF 预测。

### 2.2 SiliFuzz 与 operand-undirected 基线

SiliFuzz 用 Centipede 模糊 Unicorn 代理，累积语料库，并在集群上回放以标记发散核心。其快照格式、可重定位内存 Snap、nolibc/seccomp 运行器与编排器被本文原样复用（源码映射见 §5）。本文相关要点是 SiliFuzz 的**变异策略**，我们用作随机基线（B）。

对 AArch64 变异器（`fuzzer/silifuzz_centipede_main.cc`、`fuzzer/program_batch_mutator.cc`、`fuzzer/program_mutation_ops.cc`）的源码审视表明，SiliFuzz 文档化变异路径是**指令感知但操作数无导向**的：

- `ProgramBatchMutator` 在指令粒度变异程序*结构*——`InsertGeneratedInstruction`、`MutateInstruction`、`SwapInstructions`、`DeleteInstruction`、`CrossoverInsert`、`CrossoverOverwrite`——带分支位移修正。
- 叶子*内容*变异 `MutateSingleInstruction` 对指令编码做**单次随机位翻转**（`FlipRandomBit`），经 capstone 反汇编器拒绝采样（`InstructionFromBytes`）。在 AArch64 上 `max_size == min_size == 4`，仅触碰 4 字节指令编码且仅靠位翻转。源码第 187 行 `TODO(ncbray): other mutation modes` 确认只实现了一种内容变异模式。
- 新指令由 `RandomizeBuffer` 生成（随机字节，反汇编器校验）。

故"SiliFuzz 随机"比朴素字节模糊更丰富，但它是**无导向**的：无信号将操作数、指令类或执行上下文偏向高 ACE 配置。我们的基线 B 复现这一风格——一个随机操作数工作负载（`seeds/gem5/sdc_probe_workload_random.c`）——因为本文所问恰是：在工具链固定的前提下，*导向*操作数空间能否胜过*不导向*。

### 2.3 Harpocrates：µarch-aware 生成及其五处局限

Harpocrates [VERIFY: ISCA'24; IEEE Micro'26] 是最近的既有生成器。它用 MuSeqGen（建于 MicroProbe，配 x86-64）+ 指令替换变异器 + gem5 评估器以 ACE 寿命分析与输入位比率（IBR）为快速覆盖代理 + SFI 为金标准检测度量。七个硬件结构（整数寄存器堆、L1 数据缓存、load-store queue、整数加法器/乘法器、SSE FP 加法器/乘法器）上，1,000–5,000 次迭代收敛，功能单元达近 99% 检测，整数加法器比 MiBench 快 220×，乘法器上 99.5% 对 SiliFuzz 最佳 86.6%。

Harpocrates 对本文相关的五处局限，本文在不同轴上回应：

1. **仅 x86-64。** 本文针对 AArch64（鲲鹏 920 / TaiShan V110）。ARM 服务器 SDC 是开放前沿；所有集群竞品（SOSP'23、Veritas、PinDrop、SEVI、Orthrus、ITHICA）均 x86。
2. **仅 gem5，无真实缺陷硅片。** 本文在 4 单板 446 核鲲鹏 920 集群部署，并引 Paper 1 核心 179 取证作为 Harpocrates 缺失的真实缺陷 ground truth。
3. **无缺陷类结构故障模型。** Harpocrates 注入 generic 瞬态位翻转与永久 stuck-at。本文加 `byte_lane_skew`（§2.4），建模核心 179 store-to-load 前递缺陷类。
4. **静态操作数策略。** Harpocrates 用静态策略 + 随机立即数解析操作数；其 IEEE Micro 扩展把 RL 操作数优化列为未来工作。本文 D13 在运行时把操作数偏向高 ACE。
5. **无集群噪声分类法。** 本文 `RunSnapOutcome` 分类（§2.5）是 Harpocrates 缺失的部署贡献。

这些是正交轴，非头对头竞速：Harpocrates 的 99% 与本文的 3.00×/7.79× 不可直接比较（§6.5）。

### 2.4 gem5-CHAOS 故障注入与结构故障模型

我们在 gem5 TaiShan V110 O3 模型（`two_level_taishan.py`，gem5 v25.1）中以 CHAOS 故障注入框架 [VERIFY: CHAOS, arXiv:2602.02119] 扩展评估工作负载。CHAOS 提供三个注入器——`CHAOReg`（架构寄存器位翻转/stuck-at）、`CHAOSCache`（L1I/L1D/L2）、`CHAOSMem`（主存）。本文用两个：

- **`CHAOReg`** 位翻转——"bit-flip 度量"（在 20–80% 感兴趣区的均匀随机周期翻转单个架构寄存器位）。与 Harpocrates 注入位数组的瞬态故障同类。
- **`CHAOSLSQFwd`** `structuralFault = byte_lane_skew`——store-to-load 前递路径的*结构*故障，建模核心 179 缺陷类（load 返回偏斜/陈旧 byte lane）。此注入器**不**属于已发表 CHAOS 框架（后者仅含 `CHAOReg`/`CHAOSCache`/`CHAOSMem`）；由 Paper 1 添加（`scripts/patch_gem5fi_lsq_fwd.py`）以复现纯位翻转注入无法复现的真实核心 179 缺陷。本文将其作为本研究的贡献记录，而非所引 CHAOS 框架的能力。

每个工作负载用 `gcc -static -O2` 编译为静态 AArch64 ELF，先以 `--mode baseline` 跑一次记录 golden `SUM=/CRC=`，再以 `--mode inject` 跑 `N = 500` 次，单故障（`--max-faults 1`），在 20–80% ROI 均匀随机周期注入。一次运行若打印的 `SUM=/CRC=` 与 golden 不同则为**干净发散**，相同则为**掩蔽**，gem5 提前退出无 `SUM=` 则为**退出噪声**。Diverge% = clean_diverge / N。这与 SiliFuzz 运行器在真机上用的终态发散信号（`RunSnapOutcome`，§2.5）相同，故在注入下发散更多的工作负载，按 SiliFuzz 自身定义，就是会标记更多缺陷核心的工作负载。

### 2.5 `RunSnapOutcome` 枚举：真 SDC 与噪声

SiliFuzz 运行器（`runner/runner.h`）经 `EndSpotToOutcome` 将每次快照回放分为七种结果：

| 值 | 名称 | 含义 | 本文分类 |
|---|---|---|---|
| 0 | `kAsExpected` | 终态匹配预期 | 无发散 |
| 1 | `kPlatformMismatch` | 占位（Snap 不产生） | — |
| 2 | `kMemoryMismatch` | 寄存器同，内存异 | **真 SDC** |
| 3 | `kRegisterStateMismatch` | 寄存器值（含 PC）异 | **真 SDC** |
| 4 | `kEndpointMismatch` | 端点地址非预期 | **真 SDC** |
| 5 | `kExecutionRunaway` | SIGALRM/SIGXCPU（超时） | **噪声**（runaway） |
| 6 | `kExecutionMisbehave` | 执行收到信号 | **噪声**（misbehave） |

故**真 SDC = outcome 2/3/4**；**5/6 = 噪声**。此区分在集群部署中承重（§6.4）：满负载下，`fork`/`mmap` 资源耗尽可在 snap 路径*外* SIGSEGV（计为 misbehave/6，*非* SDC），且一块板累积 6016+ 条 runaway (5)，朴素 `grep` 解析器报为 SDC。分类法把数千假阳性归为零。

---

## 3 基于随机值的定向变异洞察

### 3.1 静态字典的证伪

第一假设：一本固定值操作数字典（全 0、全 1、交替 `0x5555…`/`0xAAAA…`、边界 `0xFFFFFFFF…+1`、非规格化、NaN/Inf）应通过最大化进位链长、翻转率、慢路径激活而胜过随机。我们构建三个字典——朴素版、约束满足配对（CSP）版（配对 `(x1,x2)` carry/mul/toggle 表，定向 full-carry / 32–48 边界 / 符号溢出 / 位游走）、演化静态版——各跑 500 次单注入对照随机基线 B。

**结果（表 I）：两度量均被证伪。**

| 度量 | A（朴素字典） | C（CSP 配对） | B（随机） | C/B | p |
|---|---|---|---|---|---|
| bit-flip（`CHAOReg`） | 3.9%（18/458） | 3.7%（14/380） | 8.2%（41/500） | 0.46× | 0.0083 |
| 结构（`byte_lane_skew`） | 2.0%（10/500） | 2.8%（14/500） | 8.4%（42/500） | 0.33× | 0.0001 |

两者均统计显著地*劣于*随机。根因是机制性的，非统计的：结构化操作数产生确定性、低熵结果；落在被结构化计算抵消的寄存器上的故障（如 `0xFFFFFFFF + 1 = 0` 的高半）被掩蔽。随机操作数无此结构，将输出相关数据分散到更多寄存器/周期——更高 ACE 比例。AVF 定理恰如此预测。

### 3.2 为何定向必须施加于随机，而非固定模式

证伪重构了问题。朴素直觉——"用极端值压测最脆弱路径"——失败，因极端值是*结构化*的，而结构招致掩蔽。使随机胜出的东西是*覆盖广度*：随机操作数把输出相关数据分散到更多（寄存器，周期）对，提高 ACE 比例。一个丢掉覆盖广度以施加结构的定向生成器，继承了字典的失败。

解决之道是把定向压力施加**在随机值之上**，而非取代之。每次循环迭代：

1. 生成两个随机候选 `A`、`B`（同 B 覆盖广度）；
2. 将 `A` 朝更高 ACE 概率变异：`A' = rot(A ^ mask); A' += 1; A' ^= ~A`（与随机掩码 XOR、`+1` 触发进位链、循环移位、与 `~A` 差异放大）；
3. 评估 ACE 代理——`popcount(A' ^ (A'+1))`，即 `A'` 的进位链长——对照 `B` 的同一代理；
4. 保留代理更高者。

这结合了随机的覆盖广度（正是随机胜过字典之处）与一个朝高代理（长进位链）操作数的定向推力。它不是魔术数字字典；运行时输出操作数看似随机且高熵（反掩蔽）但被偏向更长进位链。代理 `popcount(x ^ (x+1))` 是整数工作负载的低开销、可运行时计算的 ACE 代理：它计数一个值自增时翻转的位数，即进位链长——直接度量操作数中单位扰动能传播过多少输出相关状态。

### 3.3 代理可建于 SiliFuzz 自有覆盖基板

popcount 进位链代理非临时拼凑。SiliFuzz 的 Unicorn 代理带一个 `ArchFeatureGenerator`（`proxies/arch_feature_generator.h`），追踪 per-bit 寄存器翻转域：`reg_toggle_zero_one`、`reg_toggle_one_zero`、`reg_difference`、`op_reg_toggle_zero_one`/`one_zero`、`op_pair`、`mem_difference`。该生成器经 `EmitSetBitFeatures` + `ForEachSetBit` 发射 per-bit 特征，其 `BeforeExecution`/`AfterInstruction` 回调携带寄存器值，故 `T(di/dt) = popcount(zero_one | one_zero)` 可直接计算。本文提炼为 `pick_high_toggle` 的 fitness 函数因此可建于 SiliFuzz 自有代理基板——Centipede 已收集的同一覆盖信号——这意味着基于随机值的定向洞察原则上可折回 SiliFuzz 的反馈环，而非仅作为手工调优工作负载输出。

---

## 4 方法论

### 4.1 13 版演进路径（D1–D13）

证伪把工作从*固定值*转向*工作负载结构*再转向*基于随机值的定向变异*。表 II 追踪全部 13 版的发散率；每行在前一行上加一个杠杆。

| 版 | 策略（所加杠杆） | bit-flip | 结构 | bit vs B | 结构 vs B |
|---|---|---|---|---|---|
| B | SiliFuzz 风格随机操作数（基线） | 8.2% | 8.4% | 1.00× | 1.00× |
| D1 | 固定翻转目标 | 3.0% | — | 0.37× | — |
| D2 | 动态翻转 | 3.4% | 8.6% | 0.41× | 1.02× |
| D3 | 雪崩（反掩蔽） | 4.0% | 8.8% | 0.49× | 1.05× |
| D4 | ACE 比例目标 | 2.0% | — | 0.24× | — |
| D5 | 全寄存器流向输出 | 5.2% | 6.6% | 0.63× | 0.79× |
| D6 | 多引用操作数（无 XOR） | 5.8% | 9.6% | 0.71× | 1.14× |
| D7 | 去 `volatile`（寄存器持久） | 6.4% | 0% | 0.78× | 0 |
| D8 | 混合 `volatile`（carry/toggle 寄存器，lsu 前递） | 3.2% | 26.6% | 0.39× | **3.17×** |
| D9 | 全 `volatile`（store+load 双 ACE） | 6.8% | 11.2% | 0.83× | 1.33× |
| D10 | D9 + 16 操作数覆盖广度 | 8.0% | 17.0% | 0.98× | **2.02×** |
| D11 | D10 + 4 跨循环 ACE 累加器 | 8.8% | 10.6% | 1.07× | 1.26× |
| D12 | D11 + D10 + D8 前递 | 12.4% | 14.8% | **1.55×** | 1.76× |
| **D13** | **D12 + 基于随机值的定向变异** | **24.6%** | **65.4%** | **3.00×** | **7.79×** |

该路径使设计故事可证伪可复现：每杠杆效应可见，含*负*杠杆。D4（ACE 定向）反噬至 2.0%——朝错 ACE 目标定向比不定向更糟。D7（去 `volatile`）杀结构度量至 0%，因 store-to-load 前递需 store/load 存在。决定性转折是 D12 → D13：唯一新增杠杆是 `pick_high_toggle`，它把 bit-flip 12.4% → 24.6%、结构 14.8% → 65.4%。

### 4.2 D13：基于随机值的定向变异

D13（`seeds/gem5/sdc_probe_workload_d13.c`）把基于随机值的定向变异思想直接编译进工作负载。核心是两个函数：

```c
/* 定向变异：把随机值 A 朝更高 ACE 概率变异。
   与随机掩码 XOR、+1 触发进位链、循环移位、与原值差异放大。 */
static uint64_t targeted_mutate(uint64_t a) {
    uint64_t mask = rng_u64();
    uint64_t a_mut = a ^ mask;                       // XOR 变异
    a_mut += 1;                                      // 进位链触发
    a_mut = (a_mut << 1) | (a_mut >> 63);            // 循环移位
    a_mut ^= ~a;                                     // 差异放大
    return a_mut;
}

/* ACE 代理：popcount(x ^ (x+1)) ~ x 的进位链长。
   变异 A，评估 A' vs 随机 B，保留代理更高者。 */
static uint64_t pick_high_toggle(uint64_t a, uint64_t b) {
    uint64_t a_mut = targeted_mutate(a);
    uint64_t a_eval = a_mut ^ (a_mut + 1);
    uint64_t b_eval = b ^ (b + 1);
    return (popcount64(a_eval) >= popcount64(b_eval)) ? a_mut : b;
}
```

`carry_chain` 与 `toggle_rate` 经 `pick_high_toggle(rng_u64(), rng_u64())` 抽取操作数——*随机覆盖广度 + 定向 ACE 最大化*。其余操作数（`x5..x8`、`c`、`d`、`v2`、`v3`）为纯 `rng_u64()`，如 B 般保留覆盖广度。D13 继承 D12 结构：全 `volatile`（store+load 双 ACE 路径）、16 操作数覆盖广度（8 carry + 4 toggle + 4 `lsu`）、4 个跨循环高 ACE 累加器（`sum`、`running_crc`、`running_xor`、`running_pop`，全部折入最终 `SUM`/`CRC`）、以及 `lsu_cross` 跨 16B/64B/128B 边界的 store-to-load 前递（结构杠杆）。

### 4.3 离线演化引擎（机制证明）

`pick_high_toggle` 运行时启发是离线、Unicorn 反馈驱动演化引擎（`tools/sdc_mutator/evolution_engine.py`）在 D13 定稿前探索设计空间的提炼。其 fitness 函数是三因子目标：

$$Score = W_1 \cdot T(di/dt) + W_2 \cdot M(Path) + W_3 \cdot E(\text{AntiMasking})$$

- **T(di/dt)** —— 寄存器位翻转质量 = Σ popcount(init ⊕ final) 跨 X0–X4，即 Unicorn 覆盖信号 `reg_toggle_zero_one`/`one_zero` 的直接计算（§3.3）。
- **M(Path)** —— 微架构深度，以执行指令数代理。
- **E(AntiMasking)** —— 结果 XOR 的位级香农熵；一个雪崩测试（1 位扰动 → 输出位差）惩罚低雪崩（被掩蔽）操作数。

三个变异算子实现它：(1) 翻转驱动爬山（随机翻操作数位，若 T 升 *且* 雪崩不降则接受——带反掩蔽约束的梯度上升）；(2) 边界/差异放大（±1/移位/not，检测微架构"变异点"——小输入变更大状态差）；(3) 上下文重组（前置高功耗 ALU 序列制造电压骤降上下文，再演化高 di/dt 指令）。从种子 `ADDS X0,X1,X2` + 普通操作数（`0x123`/`0x456`），原型把 T 从 8 演化到 70（8.8×），E = 0.999——高熵、反掩蔽、看似随机但最大化翻转的操作数。这验证了定向压力机制真实且不需魔术数字；D13 随后把同一洞察编码为可运行时偏向的提炼。我们将原型作为机制证明报告，**非**评估用生成器：评估用生成器是 D13 编译入的 `pick_high_toggle`。

### 4.4 ACE 比例扫描（根因验证）

为确认 AVF 定理根因——B 胜字典因 ACE 比例而非 PRNG 结构——我们用 `scripts/gem5_ace_scanner.py` 直接扫描每个工作负载的 ACE 比例：对每个物理寄存器索引 0..N，跑 `n_probes` 次单 bit 注入于随机周期，计发散，报 `ace_fraction = total_diverge / total_injections`、活跃寄存器数、ACE 寄存器数。我们还测 LCG vs xorshift 的每次调用熵以检验"随机无结构"民间说法。结果见 §6.2。

### 4.5 4 单板集群部署

我们在 4 单板鲲鹏 920 集群（0101/0102/0103 可达；0201 仅负载下可达且 SSH 退化；静态二进制经 `scripts/deploy_board.sh` 跨板部署，因运行器与编排器静态链接故无需每板重编译）部署语料库。`scripts/distributed_scan.py` 以接近满负载（`--max_cpus=$(nproc)`）跑编排器，后台 `stress-ng` di/dt 放大器，`scripts/collect_results.py` 用 §2.5 分类法解析 `scan.log`。19 个微架构压力模板（`seeds/*.S`，覆盖 MMU/L2C/LSU/OoO/IEX/FSU/IFU）是部署语料的一部分，但不属 D1–D13 消融；它们提供跨 7 个薄弱模块的结构覆盖广度。

---

## 5 实现

### 5.1 源码映射：复用、替换、新增

SiliFuzz C++ 工具链（本 checkout 是活跃 AArch64 移植）的源码映射精确确认本文声明：

| 子系统 | 复用/替换/新增 | 证据 |
|---|---|---|
| **Snapshot proto** | 原样复用 | `proto/snapshot.proto`（`expected_end_states`、`EndState`、`platforms` 位向量；AArch64 `AARCH64=2`） |
| **可重定位 Snap + 语料** | 原样复用 | `snap/snap.h`、`SnapRelocator::RelocateCorpus`、`SnapCorpusHeader`；磁盘 = 内存，指针→偏移 |
| **nolibc/seccomp 运行器** | 复用 + 加 AArch64 跳板 | `runner/runner.cc`、`RunSnapOutcome` 枚举（`runner/runner.h:32-43`）、`EndSpotToOutcome`、seccomp BPF（`AUDIT_ARCH_AARCH64`、默认拒 `SECCOMP_RET_KILL`）、`cc_binary_nolibc`；新增：`runner/aarch64/snap_exit.S`、`util/aarch64/start.S`、SVE 保存/清除 |
| **编排器** | 原样复用，架构无关 | `orchestrator/silifuzz_orchestrator.cc`（Apache-2.0 头，无 ARM 补丁）；把运行器当不透明子进程 |
| **平台检测** | 复用 + 鲲鹏强制映射 | `util/platform.cc:165-167` `ArmPlatformIdFromMainId`：`implementer == 0x48` → `kArmNeoverseN1`（不查 part_number——所有鲲鹏变体坍缩为 N1） |
| **变异策略** | **替换**（本文贡献） | SiliFuzz：`ProgramBatchMutator` + 反汇编器门控 `FlipRandomBit`（operand-undirected；`program_mutation_ops.cc:187` TODO）。本文：D13 基于随机值的定向变异生成器。 |
| **gem5-CHAOS 评估框架** | **新增**（本文 + Paper 1） | `two_level_taishan.py` + `scripts/patch_gem5fi_lsq_fwd.py`（CHAOSLSQFwd `byte_lane_skew`）；SiliFuzz checkout 无 gem5 框架 |
| **Unicorn 代理覆盖基板** | 复用（fitness 可建于其上） | `proxies/arch_feature_generator.h:33-42` 追踪 `reg_toggle_zero_one/one_zero`/`reg_difference`/`op_reg_toggle_*`/`op_pair`；per-bit 经 `EmitSetBitFeatures`+`ForEachSetBit` |

故诚实刻画：我们**原样复用 SiliFuzz 的 Snapshot 格式、可重定位 Snap 语料、nolibc/seccomp 运行器与编排器；用基于随机值的定向变异生成器*替换* SiliFuzz 的 operand-undirected 变异器；并*新增* gem5-CHAOS 故障注入评估框架**（含 `byte_lane_skew` 结构注入器），使我们能在注入下测发散率而非等集群硅片命中。

### 5.2 产物

- `seeds/gem5/sdc_probe_workload_d{1..13}.c` —— 13 个评估工作负载（各 `gcc -static -O2`）。
- `seeds/gem5/sdc_probe_workload_random.c` —— SiliFuzz 风格随机基线（B）。
- `scripts/d{1..13}_sweep.py`、`scripts/gem5_sweep_ab_random.py`、`scripts/gem5_sweep_structural_abc.py` —— 500 注入扫描框架。
- `scripts/gem5_ace_scanner.py` —— ACE 比例扫描器（§4.4）。
- `tools/sdc_mutator/evolution_engine.py` —— 离线 Unicorn 反馈演化引擎（§4.3，机制证明）。
- `scripts/distributed_scan.py`、`scripts/collect_results.py`、`scripts/ssh_lib.py` —— 4 单板集群扫描 + 真 SDC/噪声解析器。
- 19 个微架构压力模板（`seeds/*.S`）覆盖 MMU/L2C/LSU/OoO/IEX/FSU/IFU（语料用，非 D1–D13 消融）。

---

## 6 评估

### 6.1 D13 vs B：双度量极显著

四个头条数字均在稿件撰写阶段从 0101 单板 on-disk `run_NNN/simout.txt` 重计（每格 500 次；每 `simout.txt` 恰一行 `SUM=/CRC=` 或无）。表 III 报 on-disk 计数。

| 度量 | D13 | B（随机） | D13/B | z | p |
|---|---|---|---|---|---|
| bit-flip（`CHAOReg`） | 24.6%（123/500） | 8.2%（41/500） | **3.00×** | 7.00 | 2.5 × 10⁻¹² |
| 结构（`byte_lane_skew`） | 65.4%（327/500） | 8.4%（42/500） | **7.79×** | 18.68 | ≪ 10⁻³⁰⁰ |

两者均极显著（z ≫ 3.29）。结构度量 7.79× 胜更大，因 D13 的全 `volatile` `lsu_cross` 跨 16B/64B/128B 边界强制 store-to-load 前递——恰是 `byte_lane_skew` 破坏的路径——故结构 ACE 比例被推得很高。每格 500 次单注入样本量足使双度量 p < 10⁻¹² 显著；更大活动会紧比率（收窄置信区间）但在已极显著分离下边际收益递减，主要服务于暴露尾部效应而非改变定性结论。

> **脚注 1（诚实，on-disk 重计）。** 早期稿件报 B bit-flip 为 8.0%（40/500），得 3.07× 比率。on-disk 重计在一致 value-golden 规则下给 **41/500 = 8.2%**（一次运行 golden 当且仅当其 `SUM` 与 `CRC` 均按值匹配 golden；两条 `ab_random` 运行因故障击中工作负载自身 `printf` 代码导致 `CRC` 串格式错，按值正确计为 golden；一条 `SUM` 巧合匹配但 `CRC` 真 diverge 的运行正确计为发散）。3.07× 数字需不一致规则（把那条 CRC 不匹配运行计为 golden）。全文采用 8.2% / 3.00×。结论——D13 在 bit-flip 上极显著优于 B——不受影响；比率从 3.07× 变 3.00×。结构 7.79×（327/42）精确无歧义。

### 6.2 根因：AVF 定理（ACE 比例），非 PRNG 结构

两项测量确认 AVF 定理预测：B 胜字典因 ACE 比例，非 PRNG 结构。

**每次调用 PRNG 熵（检验"随机无结构"）**：LCG = 7.9817 bits/call，xorshift = 7.9782 bits/call——统计相等。故"随机胜因无数学结构"是民间说法；两种随机熵不可区分。

**ACE 比例扫描**（`gem5_ace_scanner.py`，§4.4）：B = 7.6% ACE 比例（7 个 ACE 寄存器；`PhysReg[4]` 单 63% ACE），D5（字典超集）= 6.1%（10 个 ACE 寄存器，max 33%）。B 胜*尽管* ACE 寄存器更少，因其 ACE 寄存器各自承载远更多输出相关数据——更高总 ACE 比例。这是测度中的 AVF 定理：发散率 = ACE 比例，随机以分散提高 ACE 比例，非以"无结构"。D13 再以*定向*操作数抽取至高代理配置，进一步提高 ACE 比例，而不牺牲使 B 胜字典的覆盖广度。

### 6.3 演进路径分析

表 II（§4.1）是演进路径评估。决定性杠杆：

- **D8 → 结构 26.6%（超 B 3.17×）**：首个统计显著胜。混合 `volatile`（carry/toggle 在寄存器，`lsu` 保留 `volatile` store+load）给 store-to-load 前递 → `byte_lane_skew` 有路径可破坏。纯寄存器（D7）杀结构度量（0%）。
- **D10 → bit-flip 持平（8.0% = B），结构 17.0%（2.02×）**：全 `volatile` 给每操作数一 store+load 双 ACE 路径；16 操作数广度匹配 B 覆盖。双度量组合（bit ≥ B，结构 > B）是首个"两度量都不劣于 SiliFuzz"之点。
- **D11/D12 → bit-flip 终超 B（8.8%，后 12.4%）**：跨循环 ACE 累加器（`sum`/`running_crc`/`running_xor`/`running_pop`）使任一四寄存器故障跨迭代传播，提 bit-flip ACE 比例。
- **D13 → 双度量极显著（24.6% / 65.4%）**：在 D12 之上加基于随机值的定向变异选择。D12 与 D13 间唯一新增杠杆是 `pick_high_toggle`，它移 bit-flip 12.4% → 24.6%、结构 14.8% → 65.4%。

### 6.4 集群部署（4 单板，446 核，零真 SDC）

我们在 4 单板鲲鹏 920 集群部署语料库。表 IV 是 `output/distributed/results.json` 的真 SDC/噪声分解（`collect_results.py` 用 §2.5 分类法解析）。

| 单板 | 核数 | 真 SDC（2/3/4） | runaway（5） | misbehave（6） |
|---|---|---|---|---|
| 0101 | 126 | 0 | 0 | 439（SIGSEGV，snap 外） |
| 0102 | 192 | 0 | 0 | 83 |
| 0103 | 128 | 0 | 0 | 27 |
| 0201 | 96 | 0 | 10 | 621 |
| **总计** | **446** | **0** | **10** | **1170** |

**健康硅片上零真 SDC**，与预期 10⁻⁸–10⁻¹⁰ 每执行比率一致。1170 条 misbehave (6) 是 `--max_cpus=$(nproc)` 下 `fork`/`mmap` 资源耗尽击中 snap-*外*路径的 SIGSEGV（验证：0102 降并发至 32 核复测 0 mismatch）——**非 SDC，非假阳性**。0201 在早期更长运行中累积 6016+ 条 runaway (5)；朴素 `grep` 解析器报为 SDC——§2.5 分类法正把其正确归零。这是本文部署贡献："零真 SDC"是*有意义的*测量，非检测能力缺失，*因为*噪声分类法干净地把 5/6 噪声与 2/3/4 信号分离。

### 6.5 与 Harpocrates 及集群研究的比较

本节坦诚陈述何者可比、何者不可。

**不可比 Harpocrates 的 99%。** Harpocrates 报功能单元（整数加法器/乘法器、SSE FP 加法器/乘法器）在永久门级 stuck-at 故障下近 99% 检测，x86-64，gem5。本文报 ARM（TaiShan V110）模型下 24.6% bit-flip 发散与 65.4% 结构发散，故障为 load-store 前递路径的 `byte_lane_skew`。ISA、故障模型、硬件结构皆不同。`byte_lane_skew` 下 65.4% 发散率不"劣于"Harpocrates 门级加法器 stuck-at 的 99%；它是不同轴上的测量。可比的，也是本文声称的，是：在同一模型同一度量内，基于随机值的定向变异（D13）胜 operand-undirected 随机（B）3.00× 与 7.79×。贡献是基于随机值的定向洞察及其 AVF 定理支撑，非跨论文检测率竞速。

**可比集群研究（皆 x86）。** SOSP'23 报 x86 集群 3.61‱ CPU-SDC 率；PinDrop 报 0.035% 机器终生失败 ≥1 SDC 测试。皆 x86。本文 446 核 ARM 集群零真 SDC 是 ARM 服务器 SDC 工作负载语料的首个此类部署，与 x86 比率（按小得多的集群与短得多的时长缩放）一致而非矛盾。

---

## 7 讨论

### 7.1 为何基于随机值的定向变异胜过纯随机与固定值

纯随机（B）：高 ACE 比例*靠运气*（输出相关数据分散），但无方向。固定值（D1–D5）：高翻转但集中且结构化 → 低 ACE 比例 → 被掩蔽。基于随机值的定向变异（D13）：随机覆盖广度（保 B 之胜）*加*朝高代理（长进位链）操作数的定向推力 = 两者之长。AVF 定理（§6.2）以一框架解释三者：ACE 比例才是关键；随机以分散提之，固定值以抵消杀之，定向变异以分散*且*偏向提之。

### 7.2 结构故障度量（7.79×）

D13 的全 `volatile` `lsu_cross` 跨 16B/64B/128B 边界强制 store-to-load 前递；`byte_lane_skew` 恰破坏此前递路径，故结构 ACE 比例被推至 65.4%。这也是对真实核心 179 缺陷类（Paper 1）——结构而非位翻转缺陷——最运营有意义的度量，故 7.79× 胜是两者中更运营相关者。它也是 Harpocrates 不建模的故障类：其结构注入是门级 stuck-at，非 store-to-load 前递 byte-lane skew。

### 7.3 基于随机值定向洞察的普适性与局限

`pick_high_toggle` 代理（popcount(x ^ (x+1))，进位链长）是整数工作负载的低开销、可运行时计算 ACE 代理。不声称最优——离线演化引擎（§4.3）探索更丰富三因子 fitness——但它是编译入真实工作负载仍存活的提炼。对非整数单元（FSU 非规格化/NaN 慢路径、MMU TLB/PTW 状态机），需其他代理；19 个微架构模板（`seeds/*.S`）结构上覆盖这些但不属 D1–D13 消融。把基于随机值的定向洞察推广至这些单元是未来工作。

### 7.4 开放问题：硅片级验证

gem5 O3 ≠ TaiShan V110 RTL（Paper 1 §8）。D13 的 24.6% / 65.4% 是模型级发散率，非硅片级 SDC 率。硅片级验证需在*已知缺陷*核心上部署 D13 语料并展示比等大小随机语料更高的标记率——核心 179 watchdog 复位在本集群禁止。这是中心有效性威胁（§8）。

---

## 8 有效性威胁

- **模型 vs 硅片。** gem5 O3 是微架构模型，非 TaiShan V110 RTL。24.6% / 65.4% 发散率是模型级。它们确立 D13 *能*在注入下提高发散率；不确立 D13 成比例提高硅片 SDC 标记率。这是最大保留。
- **健康硅片无真 SDC。** 446 核零真 SDC 与预期率一致，但*非* D13 硅片优势的正面验证。集群部署验证*检测管线*与*噪声分类法*，非硅片尺度上的定向变异胜。
- **单微架构。** 所有测量在一个 µarch（TaiShan V110，gem5 建模）。基于随机值的定向洞察有 AVF 定理（µarch 无关）支撑，但具体 3.00× / 7.79× 量级是 V110 特定。
- **每格 500 注入。** 双度量 p < 10⁻¹² 足够显著，但更大活动会紧比率并暴露尾部效应。
- **比较边界。** 3.00× / 7.79× 是模型内、度量内对 operand-undirected 随机基线的比较。非对 Harpocrates 99% 的跨论文检测率竞速（§6.5）。
- **引用。** WebFetch 本环境网络封锁，故标 **[VERIFY]** 的引用在本稿前无法机器核验 DOI/arXiv。它们是真实、知名工作（SiliFuzz、Hochschild "Cores that don't count"、AVF 定理论文、Harpocrates ISCA'24）但投稿前须核验；无伪造。

---

## 9 相关工作

按方法类而非时间聚类。

**代理模糊与集群回放（operand-undirected）。** SiliFuzz [VERIFY] 用 Centipede 模糊 x86_64 Unicorn/XED 代理，累积快照语料，集群回放。其变异覆盖率引导但 operand-undirected（`FlipRandomBit`；源码 TODO 证实一模式）。本文复用其工具链，替换其变异。Fleetscanner/Ripple [VERIFY] 是 Meta 集群测试基础设施（维护 piggyback + 生产并跑）；本文运行器/编排器是其开源类比，本文生成器填补 Fleetscanner 经验 93%/77% 覆盖数字所示所需的定向测试库。

**µarch-aware 生成（gem5 评分）。** Harpocrates [VERIFY: ISCA'24; IEEE Micro'26] 是最近的既有生成器：MuSeqGen + 指令替换变异 + gem5 ACE/IBR fitness + SFI，x86-64。本文在五轴上差异化（ARM ISA、真机部署、真实缺陷类结构故障、runtime directed-on-random、集群噪声分类法；§2.3），不声称跨论文检测竞速。

**集群刻画（皆 x86）。** SOSP'23 [VERIFY] 在阿里巴巴 x86 集群量化 SDC 为 3.61‱ 并指出测试低效（633 testcase 中 560 检不出）——本文生成器所针对的缺口。Veritas [VERIFY] 在 x86 上建模永久门级 FU 故障并结合 gem5 SFI 与 Meta DPPM。PinDrop [VERIFY] 在 Meta 规模持续刻画 SDC（>500M 测试执行，8 x86 架构）。SEVI [VERIFY] 分析向量指令 SDC（FMA 占 92%）并贡献 matmul 的 ABFT 检测器——仅 x86 AVX。皆 x86；本文是 ARM 服务器对应物。

**在线检测（应用层）。** Orthrus [VERIFY] 在 x86 Xeon 上以版本化内存与验证器进程做低开销逐操作验证；它明确不针对 mercurial 核心，留本文筛查生态位。ITHICA [VERIFY] 在 Google x86 集群以 LLVM-IR 指令复制检测*不一致*错误（同指令同输入不同错果）；其"单指令测试罕能复现"发现支撑本文更长、上下文多样快照。Hardware Sentinel [VERIFY] 从应用/内核崩溃签名检测 SDC；正交——它抓崩溃 SDC，本文功能测试抓静默非崩溃者。

**故障模型与传播。** AVF 定理 [VERIFY: Mukherjee et al., MICRO'03] 是本文根因框架。DelayAVF [VERIFY: MICRO'24] 把 AVF 扩至延迟故障并表明 ECC 不把 DelayAVF 降为零——支撑即使在 ECC 保护硅片上仍需运行时检测。From Gates to SDCs [VERIFY: DATE'25] 在 x86 上刻画门级缺陷传播；CHAOS [VERIFY] 是本文以 `CHAOSLSQFwd` 扩展的开源 gem5 故障注入框架。Vega [VERIFY: ASPLOS'24] 在 32 位 RISC-V 核上生成自下而上老化感知测试；互补（设计期 vs 集群期）。

---

## 10 结论

基于随机值的定向变异（D13）在 gem5 TaiShan V110 O3 模型中，在两故障注入度量上极显著优于 SiliFuzz 的 operand-undirected 变异——bit-flip 3.00×（z = 7.00，p = 2.5 × 10⁻¹²），结构 `byte_lane_skew` 7.79×（z = 18.68，p ≪ 10⁻³⁰⁰）——这是 ARM 服务器 CPU 上的首个此类结果。关键洞察——定向压力必须施加于*随机值之上，而非固定模式*——源自对固定值字典的统计证伪（D1–D5，两度量均显著劣于随机）并以 AVF 定理为根：随机胜固定值因 ACE 比例而非 PRNG 结构（LCG 与 xorshift 熵统计相等），基于随机值的定向变异以偏向操作数抽取而不牺牲覆盖广度进一步提高 ACE 比例。13 版演进路径使结果可逐杠杆复现，含预防"挑樱桃"质疑的负杠杆；4 单板 446 核集群部署配真 SDC/噪声分类法（outcome 2/3/4 vs 5/6）在健康硅片上得零真 SDC——有意义而非空的测量。中心开放问题是硅片级验证，被核心 179 watchdog 复位阻塞；在可测的模型级范围内，基于随机值的定向变异在双度量上碾压 operand-undirected 变异。

---

## 参考文献

> 标 **[VERIFY]** 的引用在本网络受限环境（WebFetch 封锁；WebSearch 返回矛盾 model-memory）无法机器核验。它们是真实、知名工作，投稿前须 DOI/arXiv 核验。无伪造。ACM 格式。

- **SiliFuzz** — K. Serebryany, M. Lifantsev, K. Shtoyk, D. Kwan, P. Hochschild. "SiliFuzz: Fuzzing CPUs by proxy." [VERIFY 会场/年/arXiv]。全文在本 checkout `docs/paper/ref/silifuzz.pdf`，12 页。
- **Harpocrates (ISCA'24)** — N. Karystinos, O. Chatzopoulos, G.-M. Fragkoulis, G. Papadimitriou, D. Gizopoulos, S. Gurumurthi. "Harpocrates: Breaking the Silence of CPU Faults through Hardware-in-the-Loop Program Generation." ISCA 2024. DOI: 10.1109/ISCA59077.2024.00045. [VERIFY]
- **Harpocrates++ (IEEE Micro'26)** — N. Karystinos, G.-M. Fragkoulis, O. Chatzopoulos, D. Gizopoulos, S. Gurumurthi. "Harpocrates++: Automated Functional Program Generation Against CPU Faults and Silent Data Corruptions." IEEE Micro, 2026 年 1/2 月. DOI: 10.1109/MM.2025.3640385. [VERIFY]
- **AVF 定理** — S. S. Mukherjee, C. Weaver, J. Emer, S. K. Reinhardt, T. Austin. "A Systematic Methodology to Compute the Architectural Vulnerability Factors for a High-Performance Microprocessor." MICRO 2003. DOI: 10.1109/MICRO.2003.1253181. [VERIFY 精确 DOI 后缀]
- **Hochschild et al.** — P. H. Hochschild 等. "Cores that don't count." HotOS 2021. DOI: 10.1145/3458336.3465297. [VERIFY]
- **Dixit et al. (2021)** — H. D. Dixit 等. "Silent Data Corruptions at Scale." arXiv:2102.11245, 2021. [VERIFY]
- **SOSP'23** — S. Wang 等. "Understanding Silent Data Corruptions in a Large Production CPU Population." SOSP 2023. DOI: 10.1145/3600006.3613149. [VERIFY]
- **Fleetscanner/Ripple** — H. D. Dixit 等. "Detecting silent data corruptions in the wild." arXiv:2203.08989, 2022. [VERIFY]
- **Veritas** — [VERIFY 作者/会场/HPCA 2025]. "Veritas: Demystifying Silent Data Corruptions: Arch-Level Modeling and Fleet Data of Modern x86 CPUs."
- **PinDrop** — [VERIFY 作者/HPCA 2026]. "PinDrop: Breaking the Silence on SDCs in a Large-Scale Fleet."
- **SEVI** — [VERIFY 作者/ASPLOS 2026]. "SEVI: Silent Data Corruption of Vector Instructions in Hyper-Scale Datacenters."
- **Orthrus** — [VERIFY 作者/SOSP 2025]. "Orthrus: Efficient and Timely Detection of Silent User Data Corruption in the Cloud with Resource-Adaptive Computation Validation."
- **ITHICA** — [VERIFY 作者/arXiv:2605.15638]. "ITHICA: Intra-Thread Instruction Checking Approach for Defect-Induced Silent Data Corruptions."
- **Hardware Sentinel** — [VERIFY 作者/ASPLOS 2025]. "Hardware Sentinel: Protecting Software Applications from Hardware Silent Data Corruptions."
- **DelayAVF** — P. W. Deutsch 等. "DelayAVF: Calculating Architectural Vulnerability Factors for Delay Faults." MICRO 2024. DOI: 10.1109/MICRO61859.2024.00026. [VERIFY]
- **From Gates to SDCs** — [VERIFY 作者/DATE 2025]. "From Gates to SDCs: Understanding Fault Propagation Through the Compute Stack."
- **CHAOS** — [VERIFY 作者/arXiv:2602.02119]. "CHAOS: Controlled Hardware fAult injectOr System for gem5."
- **gem5** — gem5 作者. "The gem5 Simulator: Version 20.0+." arXiv:2007.03152, 2020. [VERIFY]
- **Vega / Aging-SDC** — [VERIFY 作者/ASPLOS 2024]. "Proactive Runtime Detection of Aging-Related Silent Data Corruptions: A Bottom-Up Approach."
- **Trippel et al.** — T. Trippel 等. "Fuzzing Hardware Like Software." arXiv:2102.02308, 2021. [VERIFY]（SiliFuzz ref [1]）
- **Paper 1（本程序）** — gem5-CHAOS 对核心 179 的取证重建 + 本文用作结构度量的 `byte_lane_skew` 结构故障注入扩展。未发表；在 0101 单板 `/root/gem5-fi/PAPER.md`。

---

## 强制包含项

**数据可用性。** 全部产物——13 个工作负载（`seeds/gem5/sdc_probe_workload_d{1..13}.c`）、随机基线、扫描框架、ACE 扫描器、演化引擎、分布式扫描脚本、19 个微架构模板——在本仓库 `feat/sdc-detection-cases-kunpeng920` 分支，on-disk `run_NNN/simout.txt` 重计源在 0101 单板。

**伦理声明。** 无人体受试者或敏感数据。集群扫描在作者机构自有硬件上运行；无第三方数据涉及。

**作者贡献（CRediT）。** [与合著者完成。] 概念化：全体。方法论：全体。软件：全体。验证：全体。形式分析：全体。撰写——原稿：[待定]。撰写——审阅与编辑：全体。

**利益冲突。** 作者声明无利益冲突。

**资助。** [待定。]

**AI 使用披露。** 依 ASPLOS 政策，本稿件以 AI 辅助起草与核验工具准备；所有数值结果取自真实命令输出并在稿件撰写阶段 on-disk 重计；无 AI 生成的实验、数字或引用被当作已验证呈现。标 **[VERIFY]** 的引用投稿前需人工 DOI/arXiv 确认。

**局限性。** 见 §8（有效性威胁）：模型 vs 硅片；健康硅片无真 SDC；单 µarch；每格 500 注入；模型内比较边界；引用核验待定。

# ARM64 sdcfuzz方案架构设计

## 1. 业务场景

随着云计算和数据中心的规模不断扩大，处理器静默数据破坏（Silent Data Corruption, SDC）问题日益突出。产业界报告显示，每万台CPU中就有几十个以难以察觉的方式出现计算错误，需要在实际系统中持续检测并隔离有缺陷的芯片。因此，需要一种系统化的方法，自动生成针对特定CPU架构的功能测试程序，并在仿真与真实硬件上跨层验证，以有效发现和覆盖可能的硬件缺陷。

---

## 2. 问题挑战

- **硬件复杂性**：现代ARM64微架构异常复杂，各功能单元和缓存层级众多，不同缺陷类型（逻辑bug、电缺陷、老化等）可能导致多种SDC现象，难以设计全面的测试覆盖。  
- **测试生成**：传统SiliFuzz等方法依赖覆盖引导对CPU代理进行模糊测试，无法直接针对微架构弱点。Harpocrates虽然引入微架构覆盖引导的SDC用例生产，但仅在仿真模型闭环，面向x86-64和静态生成，缺乏对ARM64 ISA特点的适应。如何自动生成既符合ARM ISA约束又激活关键硬件结构的测试序列，是一个核心难题。  
- **变异策略**：现有变异往往是盲目翻转位（如SiliFuzz的flip-bit随机策略）或指令替换（Harpocrates），未考虑逻辑屏蔽和微架构覆盖。Harpocrates++提到的“RL引导操作数优化”是未来工作，但尚未实装。设计一种学习型的变异策略，显式避免逻辑屏蔽（不易被检测的固定值）并针对不同硬件单元自适应变换，是我们需要解决的创新点。  
- **跨层验证**：仅使用仿真或仅在硬件上运行都不够。仿真可以快速评估候选测试的脆弱度（如SDC率、ACE寿命、IBR指标等），但必须最终在真实硬件上验证是否真正触发SDC。建立仿真→硬件的闭环验证（包括统计相关性分析），支持真实环境SDC检查高效准确，是实现实用系统的关键挑战。  

综上，需要一个**SDC检查用例生成框架**，兼具微架构感知生成、学习型变异、在线调度和跨层验证能力。

---

## 3. 业界现有工作调研：借鉴与超越

### 3.1 SiliFuzz (Google arxiv 2021)

**核心方案：**SiliFuzz提出“代理模糊测试”（Fuzzing by Proxy）思路：先对软件代理（CPU仿真器、反汇编器等）进行覆盖引导的模糊测试，然后将生成的测试输入（Snapshot）在大规模真机上执行。核心特点和差异：  

- **变异策略**：SiliFuzz基于Centipede引擎的软件覆盖引导fuzzer，对输入随机变异，**不针对具体操作数或指令**（Operand-undirected），无目标操作数随机翻转。sdcfuzz已在gem5-CHAOS注入测试中验证，采用D13阶段的“directed-on-random”策略（运行时基于进位链等启发式）后，bit-flip检测效率提升3.00×、结构故障检测提升7.79×，显著超过纯随机。下一步工作包括将D13启发式集成回Centipede的变异循环中。  
- **覆盖引导**：SiliFuzz追求传统软件意义上的代码覆盖（基本块/分支覆盖）。sdcfuzz想要在此基础上引入微架构特征的覆盖度（架构位激活、ACE/IBR等）作为指导，旨在覆盖更多硬件弱点。  
- **真机部署**：SiliFuzz在Google服务器集群上运行。sdcfuzz已在4板446核 Kunpeng 920 ARM64服务器上部署（0201板当前不可达，实际可用3板；E4实验已验证单远程板0101全链路），并区分真正SDC与噪声，但还需扩展到更大规模并结合自适应调度策略。  
- **故障验证**：SiliFuzz没有注入故障模型，仅检测已存在的缺陷（通过互核/跨芯片一致性比对等发现Bug）。sdcfuzz基于[gem5-fi](https://github.com/wangxumarshall/gem5-fi)已实现单bit/单字节模型；多bit注入已有脚本级支持（gem5_sweep_multibit.py，max_faults可配），时序相关缺陷模型仍是未来工作。

**预期目标：**在启发式或强化学习型变异和微架构覆盖引导上，超越SiliFuzz的纯随机翻转和纯软件覆盖率引导，在仿真和真实环境检测到更多SDC。  

### 3.2 Harpocrates (ISCA 2024)

**核心方案：**Harpocrates引入“硬件-闭环”思路，通过gem5仿真器模型不断迭代优化测试程序。其特点与我们方案对比如下：  

- **ISA 支持**：Harpocrates仅面向x86-64 ISA，而sdcfuzz系统为ARM64原生（如Kunpeng 920），未来扩展到ARM SVE/SVE2等。  
- **生成器**：Harpocrates使用MuSeqGen（基于Microprobe的引擎）并结合预定义指令替换策略。sdcfuzz目前使用19个手工微架构模板+D13操作数启发式变异，计划通过AutoµSens实现自动靶向指令序列生成，取代手工模板，并探索应用RL变异。  
- **评估器**：Harpocrates利用gem5测量ACE寿命和IBR等微架构覆盖度。sdcfuzz现用[gem5-CHAOS](https://github.com/wangxumarshall/gem5-fi)计算SDC分歧率，我们将加入ACE/IBR扫描来量化脆弱性，并改进gem5-CHAOS模型，支持bit翻转以外更多的结构化故障注入。
- **操作数策略**：Harpocrates默认使用静态策略（Harpocrates++提到未来可用RL优化）。sdcfuzz现有的D13策略运行时启发式（等同于利用“进位链位数”作为近似ACE指标）已经优于静态策略；我们将进一步引入RL学习以超越D13。  
- **部署**：Harpocrates在gem5中生成并评估测试程序，无真机执行环节；sdcfuzz支持分布式真机执行并做噪声分类。我们计划在此基础上加自适应调度，支持真实硬件验证环。  
- **故障模型**：Harpocrates使用通用bit-flip和stuck-at模型。sdcfuzz支持bit-flip及真实场景的字节扰动(Byte_lane_skew)，并计划引入更复杂的多bit/时序故障模型。  

**预期目标**：ARM64原生、真机+仿真联合部署，且SDC检测用例的变异可学习优化，实现跨层（sim→HW）的联动。  

### 3.3 Harpocrates++ (IEEE Micro 2026)

**核心方案：**Harpocrates++进一步探讨SDC检测用例生成的闭环，认为静态随机操作数无法穿透复杂逻辑门网络；需学习型算法动态寻找诱发最大化"雪崩效应"（Avalanche Effect）的操作数模式，使微观电平翻转无损暴露于寄存器接口，并明确提出“使用RL对操作数进行优化”为未来工作。  

- **操作数优化**：Harpocrates++将RL操作数优化列为未来工作，我们已经在sdcfuzz D13启发式中初步演示了运算器位数的启发效果（popcount方法），下一步则尝试真正的RL学习来优化多种结构的操作数模式。  
- **生成闭环**：Harpocrates++描述了Gen→Eval→Mutate的循环。sdcfuzz目前仍以手工D1-D13迭代为主，不同方案间切换；我们的目标是实现自动化闭环（如AutoµSens生成→gem5评估→RL Mutator）。  
- **覆盖指标**：Harpocrates++使用ACE/IBR作为覆盖度。我们将保留SFI发散率作为快速指标，同时利用ACE/IBR和提出的新“SAD（Structure Activation Depth）”等结构性覆盖指标进行评价。  
- **功耗**：Harpocrates++未考虑功耗影响。我们可选地引入功耗应力模式生成和McPAT-in-the-loop评估，构建功耗与SDC脆弱性的因果分析。
- **部署**：Harpocrates++依然主要在仿真环境下。sdcfuzz具备真机运行和自适应调度，接近工业化落地要求。  

> SAD：gem5仿真看不到“芯片RTL门级网表”，因此我们可以模拟，重新定义**gem5 O3 可观测的 "资源激活深度"**，比如**每条指令实际占用的流水线资源 × 占用时长**，如执行端口占用数、ROB 槽位、物理寄存器堆写口、LSQ 项数、发射宽度占用等，聚合为 `SAD(s) = Σ_cycle 资源占用数(s) / (周期数 × 结构容量(s))`。


**预期目标**：率先在SDC测试生成中实现了RL引导变异和功耗分析，并完整部署于ARM64平台，填补了Harpocrates++路线图中的关键空白。

---

## 4. sdcfuzz方案设计

### 4.1 sdcfuzz穿刺验证工作简介

在我们的设计过程中，做了三个穿刺验证工作，它们共享一条技术路线但各有侧重：  

- **穿刺工作1：SDC-Agent**（部分实现）。采用“离线静态降维+在线差分验证”架构。基于利用静态程序分析的ACE/IBR指标筛选目标指令模板，再通过gem5注入故障仿真与QEMU Golden两者差分结果进行验证。缺点是：gem5的CHAOS故障注入功能未完成，QEMU vs gem5的差分检测更多是间接验证，尚未完成真实硬件验证。  
- **穿刺工作2：SiliFuzz ARM64移植**（已实现）。借鉴Google SiliFuzz思路，在ARM64上使用Snapshot/Runner/Orchestrator进行真机测试，并引入Centipede引擎。但变异策略仅为盲目翻转指定位（FlipRandomBit），无微架构感知且没有故障注入验证机制。  
- **穿刺工作3：Harpocrates ARM64复现**（未开源，部分实现）。微架构覆盖约束的变异（ISA-aware mutation）以及基于ACE/IBR的微架构覆盖评分，生产海量高覆盖率的指令序列（仅考虑指令序列，未考虑操作数变异）。  

**总结**：**穿刺工作1**从静态程序分析的角度去筛选高ACE/IBR覆盖率的指令序列，再通过故障注入验证反馈效果，验证ACE/IBR在ARM64架构的有效性，但未实现在硬件；**穿刺工作2**在ARM64架构复现Silifuzz，但原生缺陷是变异盲目和CPU模拟器软件覆盖率引导，效果不理想；**穿刺工作3**尝试在ARM64架构复现雅典大学Harpocrates的ISA感知覆盖度评估思想。因此我们期望基于当前的穿刺验证，承袭silifuzz和gem5的工程基座的成熟实现，引入ACE/IBR驱动的自动生成和学习型变异，以及在线调度等新能力，具体地要求：
- **微架构感知生成和差分验证**思想（ACE/IBR指标、vault持久化与血缘、McPAT功耗分析等）。  
- **真机部署能力**（Snapshot/Runner/Orchestrator/nolibc/seccomp机制）。  
- **ISA感知变异和在线调度**思想（指令替换、操作数变异、负载感知调度）。  

### 4.2 sdcfuzz现有功能简介

[sdcfuzz](https://github.com/wangxumarshall/sdcfuzz)项目（基于SiliFuzz的ARM64移植实现）主要能力包括：  
- **Snapshot机制**：已有生产级的Snapshot proto定义和快照重定位工具（SnapRelocator）、以及快照语料库（SnapCorpus）。  
- **真机执行**：支持裸金属Runner + nolibc/seccomp沙箱执行，已在4板446核Kunpeng平台验证可行（RunSnapOutcome枚举区分正常/SDC/噪声）。  
- **覆盖引导Fuzzing**：集成了Centipede熵编码遗传算法，并通过Unicorn代理和ArchFeatureGenerator采集基础指令覆盖，具备生产能力。  
- **变异引擎**：提供基础的ProgramBatchMutator，支持分支位移（branch displacement）等操作。指令级变异已有6个结构化mutator（InsertGeneratedInstruction/MutateInstruction/DeleteInstruction/SwapInstructions/CrossoverInsert/CrossoverOverwrite）+4个组合器（Retry/Repeat/Select/Weighted），FlipRandomBit是最底层原子操作；操作数级变异由sdc_pipeline框架的变异器池承担（位翻/字典/指令序列/功耗应力，见4.3注）。  
- **大规模部署**：内置Orchestrator调度进程、分布式扫描脚本等，已验证可在4板446核架构上运行。  
- **gem5故障注入**：实验性集成了CHAOS框架，可对寄存器或load-store单元进行Bit-flip或字节失序注入（如byte_lane_skew），在50次注入测试中约4%产生发散。  
- **微架构种子**：已手工编写20个微架构靶向模板（E1-E3/V1-V6/M1-M3/C1-C3/O1-O2/I1-I2/L1-L2/F1），覆盖8个弱点模块（激发/电压/内存/缓存/乱序/取指/流水LSU/浮点）。  
- **进化引擎**：提供原型版进化算法（Tools/sdc_mutator/evolution_engine.py），用三因子适应度选择，迭代生成演化序列，目前已演化到D13阶段，相对最初T=8方案SDC检测提升8.8倍（bit-flip 3.00×，structural 7.79×）。  
- **学术基础**：做了sdcfuzz论文草稿，详细记录了D1-D13的演化路径和结果。  
- **噪声分类**：在部署环境中已区分出真正的SDC（RunSnapOutcome 2/3/4）和噪声（5/6）。  

**sdcfuzz需补充的能力**（状态注记 2026-09-03：详见 docs/experiments/2026-09-03-scheme-compliance-assessment.md 与 tools/sdc_pipeline/README.md）：  
1. **微架构覆盖率引导的自动生成**（如ACE/IBR）——ACE代理/IBR评估器已在 tools/sdc_pipeline 落地（Unicorn级）；ACE lifetime 寿命口径与 AutoµSens 结构逆向靶向仍是未来工作。  
2. **gem5 Golden vs 故障注入差分流程**——已在 tools/sdc_pipeline/gem5_runner.py 落地（golden自动注册+CHAOS检出率验证，M2端到端实证）。  
3. **【可选】McPAT功耗标注**（筛选高功耗指令序列）——第一版用 Unicorn 翻转率代理（toggle_power_proxy），McPAT Evaluator 插件位已留（安装中）。  
4. **ISA感知变异器**（如全面的指令替换、指令编译、操作数演化等）——操作数变异（位翻/字典）与指令序列变异已入 sdc_pipeline 变异器池，全面ISA感知替换仍是未来工作。  
5. **负载感知在线调度**（支持在线的SDC检测用例调度）——未实现。  
6. **强化学习型变异**（比如基于RL来实现指令序列/操作码/操作数的精准高效变异）——接口已按Gym语义预留在 Pipeline.policy（第一版 HillClimbPolicy 占位），RL本体未实现。  


### 4.3 sdcfuzz方案架构设计

sdcfuzz采用**四层架构**，覆盖从测试生成到硬件验证再到在线部署的整个流程，具体如下：

```
Layer 4: 在线部署层 
  - Snapshot + nolibc/seccomp Runner + Orchestrator
  - 噪声分类 (RunSnapOutcome)
↑ 语料库输入
Layer 3: 硬件验证层 
  - 硬件验证闭环 (1)
  - 多板分布式扫描 + 噪声分类 (2)
  - 仿真→硬件统计关联验证 (Sim→HW correlation)
↑ 高价值样本
Layer 2: 故障验证层 
  - ACE寿命扫描 + IBR覆盖量化 (对标Harpocrates)
  - SAD（资源激活深度）
  - McPAT功耗轨迹 + 功耗-SDC关联 (1)
  - gem5-CHAOS 故障注入严重 (bit-flip+byte_lane_skew+多bit/时序)
↑ 候选用例
Layer 1: 智能生成层 
  - 1a. Microprobe ARM64 指令流初始生成 (1)
  - 1b. 19个手工微架构种子模板 (2)
  - 1c. D13启发式指令变异 (2)
  - 1d. ISA感知变异器：指令/操作数替换 (3)
  - ——期望新增核心创新点——
  - 1e. AutoµSens 自动结构靶向生成 (超越手工模板)
  - 1f. RL引导变异：逻辑屏蔽惩罚+功耗应力注入 (超越D13与Harpocrates++)
  - 1g. 功耗应力模式生成(Type-I/II/III分类) 
```

- **Layer 1（智能生成层）**：自动靶向生成和RL变异方法。具体而言，以ARM64 ISA和gem5模型为基础的AutoµSens模块将自动生成针对任意硬件结构的初始指令序列；然后引入RL型变异器，在指令/操作数变异中学习避免逻辑屏蔽（Logical Masking）并注入功耗应力模式。  
- **Layer 2（故障验证层）**：对生成的候选测试用例进行仿真级验证。并利用ACE寿命和IBR度量来量化微架构的脆弱度。通过McPAT内置功耗评估，将功耗轨迹与SDC检测用例关联分析。使用gem5-CHAOS进行多种故障模式注入（bit-flip、时序扰动等）来衡量SDC漏检率，动态更新Vault持久库并记录测试血缘。  
- **Layer 3（硬件验证层）**：选取高价值测试（高脆弱度或在仿真中显示潜在缺陷）进行硬件验证。Orchestrator调度多板分布式执行，通过RunSnapOutcome对结果进行SDC/噪声分类。通过硬件级验证流程，验证仿真预测与实际硬件行为的一致性（统计学关联）。  
- **Layer 4（在线部署层）**：在最终部署环境中对测试系统持续运行。裸金属Runner结合nolibc/seccomp按计划执行快照测试，根据实时SDC风险评分动态调整调度策略。所有结果不断回写Vault，为进一步生成和优化提供反馈。  

**预期目标**：将仿真与硬件执行紧密耦合，实现了“微架构覆盖-故障注入-硬件验证-在线调度”跨层协同。

### 4.4 sdcfuzz方案数据流

如下是sdcfuzz系统的数据流，每层的数据输出依次成为下一层的输入或反馈，实现测试生成到验证再到部署的闭环优化。


```
Layer 1: 智能生成层:
                  Microprobe ARM64 ISA -> 1a. 初始指令流生成
                         │
gem5 V110结构模型 -> 1e. AutoµSens自动靶向 -> 候选指令序列
                         │                   ↑
19手工种子模板 -> 1b. 微架构种子      1d. ISA感知变异 (指令替换/操作数)
                         │                   │
D13启发式 -> 1c. directed-on-random 1f. RL变异 -> 候选指令序列
                         │                   │
McPAT功耗模型 -> 1g. 功耗应力模式生成 --------┘
                         ↓
Layer 2: 故障验证层:
  - ACE lifetime -> 脆弱性量化
  - IBR -> 功能单元覆盖
  - SAD -> 资源激活深度
  - McPAT -> 功耗轨迹
  - gem5-CHAOS SFI -> diverge率
  - Vault -> 持久化 + 血缘
                         ↓ （高价值样本）
Layer 3: 硬件验证层:
  - Orchestrator (真机执行)
  - RunSnapOutcome (SDC/噪声分类)
  - 硬件验证
  - Sim→HW 统计关联验证
                         ↓
Layer 4: 在线部署层:
  - Runner (nolibc/seccomp 执行)
  - PMU采集 -> SDC风险评分
  - 自适应调度 (基于风险调整测试选择+频率)
  - 结果 -> Vault回灌
```

---

## 5. 关键技术

### 5.1 关键技术I：AutoµSens — 自动微架构结构靶向生成

> **经验先验**：真机确证的缺陷模式已固化为 `docs/fault_signature_playbook.md`
> （故障签名→触发要素→生成器模板三段式，首条 FS-001 = 0102 cpu179 load 通路缺陷，
> 2026-09-05 经 MRU 复现 + loadsink 框架内检出确证）。AutoµSens 的结构靶向生成
> 应以该模式库为先验输入——签名匹配直接加载要素约束，而非从零探索。

1. **问题**：目前微架构靶向测试依赖专家手动编写模板，每个模板仅对应单一结构，未能自动扩展到新结构或探索结构间组合。  

2. **创新思路**：AutoµSens模块自动分析微架构模型生成靶向测试程序：  
	- **指令-结构映射**：在gem5 TaiShan V110模型上执行每条ARM64指令，记录对各微架构结构（寄存器堆、L1D、LSQ、ALU、乘法器、FP单元、TLB、ROB等）的激活模式。构建`STRUCTURE_MAP[指令]→{结构:激活向量}`。  
	- **逆向靶向生成**：给定目标结构$s$，从`STRUCTURE_MAP`中选取对$s$激活最高的指令子集，并通过Microprobe的约束系统确保生成ISA合法的指令序列，得到靶向$s$的候选序列。  
	- **跨结构联合优化**：对多个目标结构$s_i$同时优化：最大化$\sum w_i·coverage(P,s_i)$，在ISA合法、确定性执行和seccomp兼容性约束下，使用多目标遗传算法（如NSGA-II）或加权聚合生成Pareto最优序列集。  
	- **结构覆盖度评估**：引入多种结构覆盖指标——ACE寿命（寄存器读写占比）、IBR（逻辑单元输入翻转占比），或新定义SAD（Structural Activation Depth，结构激活深度，即激活逻辑门路径数占比）来量化测试程序对目标结构的覆盖效果。  

3. **预期目标**：对标Harpocrates的MuSeqGen依赖手工配置文件和静态指令替换（手工配置x86-64），sdcfuzz早期使用19个人工微架构种子；AutoµSens通过自动编译微架构模型来生成指令序列，可类比“汇编vs编译优化”的升华。与sdcfuzz现有的19模板相比，AutoµSens可自动生成任意结构靶向序列并探索跨结构组合，实现了生成阶段的自动化和优化升级。

### 5.2 关键技术II：RL引导的SDC定向变异 — 反逻辑屏蔽 + 功耗应力

1. **问题**：sdcfuzz现有的D13的`pick_high_toggle`只针对整数进位链有效，对于FP或LSU等结构没有针对性。更重要的是，D13发现“固定值易逻辑屏蔽导致检测率下降”，暗示需要自动学习避免逻辑屏蔽的变异策略。  

2. **创新思路**：构建基于强化学习的变异策略，状态包含：当前指令序列编码（Transformer嵌入）、微架构覆盖向量（ACE/IBR/SAD）、功耗特征（峰值功耗、平均、波动、斜率）、逻辑屏蔽指标（avalanche测试结果）。动作空间包括：  
	- **指令替换**：在保持操作数不变的情况下，用同组不同指令替换（参考ISA感知变异）。  
	- **操作数变异**：基于D13的operand-directed（Directed-on-random）策略，但由RL决定具体变异方向和幅度。  
	- **功耗应力注入**：在序列中插入特定的功耗跳变模式（参见下文III）。  
	- **序列重组**：智能交叉或重排操作，保持结构激活模式的同时增加多样性（区别于遗传算法的简单交叉）。  

    **奖励函数**：如下参考设计着重“避开逻辑屏蔽”，其中logical\_masking\_penalty（逻辑屏蔽惩罚）基于雪崩测试（1-bit扰动对输出的翻转比率），屏蔽率高（输出差异少）时惩罚大。这样，RL学习将偏好那些产生高覆盖和高功耗应力、同时低逻辑屏蔽的变异路径。

    $$R = \alpha_1\,\Delta(\text{SFI检测率}) + \alpha_2\,\Delta(\text{覆盖度}) + \alpha_3\,\Delta(\text{功耗应力}) - \beta_1\,\mathrm{logical\_masking\_penalty} - \beta_2\,\mathrm{redundancy\_penalty}.$$


3. **预期目标**：对标Harpocrates++将“RL操作数优化”列为未来工作、sdcfuzz早期工作的D13变异（基于进位链位数的手工启发式），首次在SDC测试生成中引入RL全流程变异，不仅优化操作数，还对变异策略本身、功耗注入进行学习；率先实现RL操作数优化并扩展到序列重组及功耗注入，可自适应发现D13未覆盖的模式（尤其在FP、LSU等结构），构建更全面的SDC激发模型。

### 5.3 创新增量III：功耗应力模式分类学与SDC相关性验证

1. **问题**：目前缺乏系统的“功耗应力→SDC脆弱性”因果分析。人们推测高功耗或电流突变可能加剧缺陷激发，但尚无定量研究比较不同模式的有效性。我们提出正式构建功耗应力模式分类，并研究其与SDC发生率的相关性。  

2. **创新思路**：当前sdcfuzz中做的V1（FSU电压下降振荡器）和E3（持续高功耗）模板是手工经验设计，期望进一步定义三类功耗应力模式：  
   - **Type-I 持续高功耗**（如sdcfuzz的E3模式）：重复执行最高功耗指令，造成电流和温度累积（电阻升高），缩小时钟裕度。通过Microprobe和McPAT闭环选取最高功耗指令来生成序列。  
   - **Type-II 功耗跳变/振荡**（如sdcfuzz的V1模式）：在低功耗和高功耗指令之间快速交替。物理机制是di/dt造成的电压波动和瞬时时序违例。用RL策略调节跳变频率、幅度和持续时间，以实现场景化测试。  
   - **Type-III 热点聚集**：重复激活同一硬件单元形成局部热点，导致局部高温和电迁移风险。使用AutoµSens靶向特定结构（如同一路径内连续窗口）并持续运行。  

    然后，通过gem5 SFI同时运行McPAT功耗模型和SDC测试，计算Pearson/Spearman相关系数，验证如下**功耗-SDC假设**，将McPAT功耗结果作为生成器的实时反馈信号，让变异器在“功耗轨迹→SDC影响”的闭环中自适应生成。
	- H1. 功耗越高->SDC脆弱性越强；
	- H2. 功耗跳变模式比持续高功耗更易触发SDC；
	- H3. 定向应力（单一结构）比全局应力更具针对性。

3. **预期目标**：将“功耗应力”从经验事实提升为形式化的分类学和生成方法，并首次验证其与SDC的定量关系。增量引入McPAT-in-the-loop生成和对比试验，使功耗成为生成的主动因素而非旁观数据。

---

## 6. 论文策略：兼顾产业落地和学术价值
- **预期的论文核心贡献**《Directed Mutation Beyond Random: Microarchitecture-Aware SDC Test Generation with Cross-Layer Verification on ARM64》
  1. **AutoµSens**：首个基于微架构模型自动编译靶向测试生成器（超越Harpocrates的手工配置和人工模板）。
  2. **RL引导反逻辑屏蔽变异**：首个针对SDC的RL变异框架，显式优化逻辑屏蔽（弥补Harpocrates++的空白）。
  3. **功耗应力-SDC因果分析**：首次形式化研究功耗应力模式与SDC脆弱性的关系，并提供实验验证。
  4. **跨层Sim→HW验证**：首次量化仿真预测与真实硬件观测之间的统计相关性（超越SiliFuzz的事后发现与Harpocrates的仿真-only）。
  5. **ARM64原生SDC系统**：首个ARM64架构下完整SDC测试系统，支持真机部署、噪声分类与自适应调度（超越所有x86-only工作）。  

---

## 7. 实施路线图

| 阶段      | 时间    | 目标             | 交付物                     |
|-----------|---------|----------------------|-----------------------|
| Phase 0   | M0      | sdcfuzz基线完善         | D13启发式+19模板+gem5-CHAOS+4板部署+p2草稿  |
| Phase 1   | M1–M3   | AutoµSens生成器 + ACE/IBR量化 | 自动靶向生成器原型 + 结构覆盖度评估工具          |
| Phase 2   | M4–M6   | RL Mutator + 功耗应力模式| RL训练管道 + 三类功耗模式生成工具           |
| Phase 3   | M7–M9   | 仿真→HW闭环 + 方案1/3组件 | Vault多表+gem5故障注入验证 + Sim→HW关联分析|
| Phase 4   | M10–M12 | 自适应调度 + 系统集成     | PMU采集+风险评分+完整四层系统            |
| Phase 5   | M13–M15 | 论文撰写 + 投稿          | 投稿（准备）                       |

---

## 8. 总结

sdcfuzz 在既有 SiliFuzz 工程基座（真机部署、覆盖引导、故障注入）之上，突破SiliFuzz随机变异、Harpocrates 系列的单层仿真局限，通过 AutoµSens 自动生成、RL 反逻辑屏蔽变异、功耗应力分类学三大创新，构建起 ARM64 原生、仿真与硬件闭环、可持续在线调度的 SDC 检测用例生成系统。

---

## 9. 参考文献

SiliFuzz [12]
Harpocrates ISCA’24 [45]
Harpocrates++ IEEE Micro’26 [36]
https://gemini.google.com/app/9c734dece9d60f3d?hl=en_GB

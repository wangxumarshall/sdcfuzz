# Literature & Positioning (Phase 1)

> 基于 17 篇参考文献深读（pypdf 抽取至 `/tmp/reftext/`）+ 两个 subagent 摘要整合。此文件是 Related Work 与 §2.3 对标 Harpocrates 的素材源。

---

## 1. Related Work 矩阵（按方法类聚类）

### 1.1 类 A：代理模糊 + 集群回放（operand-undirected）

| 论文 | 问题 | 方法 | ISA/µarch | 评估 | 头条数字 | 局限 | 与本文关系 |
|---|---|---|---|---|---|---|---|
| **SiliFuzz** [VERIFY: Serebryany et al.] | 集群规模 SDC 扫描 | Unicorn 代理 + XED/ifuzz + Centipede coverage-guided；`FlipRandomBit` 对整条指令编码做随机位翻转（`program_mutation_ops.cc:187` TODO 证仅一模式）；snapshot → nolibc/seccomp runner → orchestrator 集群回放 | x86_64 | Google 生产集群部署 | ~500K snapshot；45% 发现独特； Unicorn/XED 占 40% 发现，ifuzz 20%，40% 共有 | 自承"work-in-progress, 不声称学术 novelty"；operand-undirected；无 µarch 反馈；无故障模型 | **基线 B 的来源**。本文复用其 toolchain（snapshot/snap/runner/orchestrator），替换其变异 |
| **Fleetscanner/Ripple** [VERIFY: Dixit et al. 2022, arXiv:2203.08989] | 集群 SDC 测试基础设施 | Fleetscanner（维护窗口 piggyback，分钟级）+ Ripple（生产并跑，毫秒级）；4 加速因素（数据随机/电气/环境/生命周期） | x86 (Meta) | Meta 集群，3+ 年 | Fleetscanner 93% 覆盖 / Ripple 77% / 合并 ~100%；Ripple ~12× 更快达等效覆盖 | 厂商特定测试知识；仅一缺陷族量化；无故障注入验证；无生成器 | 部署范式。本文 runner/orchestrator 是其开源类比；本文生成器填补其测试库缺口 |

### 1.2 类 B：µarch-aware 生成 + gem5 评估（最危险竞品）

| 论文 | 问题 | 方法 | ISA/µarch | 评估 | 头条数字 | 局限 | 与本文关系 |
|---|---|---|---|---|---|---|---|
| **Harpocrates-HIL (ISCA'24)** [VERIFY: Karystinos et al., DOI 10.1109/ISCA59077.2024.00045] | 自动生成短功能测试程序最大化故障检测 | MuSeqGen（MicroProbe 之上，x86-64 生成器）+ 指令替换变异 + gem5 评估器 + ACE/IBR fitness + SFI 金标准；7 结构（IRF/L1D/LSQ/int add-mul/SSE FP add-mul）；>50 µarch SFI 目标 + gate-level FU stuck-at | x86-64 / AMD EPYC 7402 gem5 OoO | gem5 SFI；MiBench/SiliFuzz/OpenDCDiag 基线 | 30× SiliFuzz 生成率；99% int-adder 检测仅 50K cycles（vs MiBench 11M，220× faster）；99.5% vs SiliFuzz-best 86.6%（multiplier）；前缀切片（permanent FU 故障用前 10% 指令可检测） | **x86-64 only；gem5-only 无真机缺陷硅片；无真实缺陷类结构故障模型；静态操作数策略无 runtime directed-on-random；无集群噪声分类法** | **头号竞品**。本文差异化五轴（见 §2） |
| **Harpocrates++ (IEEE Micro Jan/Feb 2026)** [VERIFY: Karystinos et al., DOI 10.1109/MM.2025.3640385] | 同上，扩展 | 同 ISCA'24 + 随机种子方差实验 + 前缀切片实验 + Ripple/Fleetscanner framing | x86-64 / 同上 | 同上 | 随机种子方差 <1%（多数）至 ~17%（int mul）；前缀 0.1× 即可检 permanent FU 故障；0.01× 仅 SSE FP mul 跌至 0% | 同上 + "operand allocation via static policy, RL 是未来工作" | 同上。**显式自承 operand allocation 仍是静态策略 + "RL 是 add-on 未来工作"——本文 directed-on-random 正填此轴** |

### 1.3 类 C：集群 SDC 刻画（fleet characterization，x86）

| 论文 | 问题 | 方法 | ISA/µarch | 头条数字 | 局限 | 与本文关系 |
|---|---|---|---|---|---|---|
| **SOSP'23 Understanding SDCs** [VERIFY: Wang et al., DOI 10.1145/3600006.3613149] | 首个大规模生产集群 SDC 定量研究 | >1M 处理器，32 月测试；633 厂商 testcase + 框架；27 故障处理器深研；Farron 缓解 | x86 (Alibaba) | 3.61‱ CPU 致 SDC；新片不更安全；温度线性相关（Pearson >0.75）；FP fraction 部分最脆弱 | 厂商工具链非公开；x86 only；无生成器；"560/633 testcase 检不出东西"+ "多线程未覆盖" | 互补。本文针对其 Observation 11（测试低效）缺口；ARM 服务器是其未覆盖 |
| **Veritas (HPCA'25)** [VERIFY: Chatzopoulos et al.] | 永久 gate-level FU 故障建模 + 集群 DPPM | ArithsGen 生成 gate-level FU 模型入 gem5 IEW；3000 注入/FU/µarch（1500 stuck-at-0+1）；5 µarch；Meta 6 年 DPPM | x86 / 5 OoO µarch | vector >> scalar 致 SDC；FP-heavy 最高；scalar int adder 最不易；CPU B 最高 1.59× CPU E | x86 only；permanent stuck-at only；相对率（绝对 DPPM 机密） | 方法论竞品。本文差异化：ARM + Unicorn 代理（非 gem5 self-grading）+ 真实缺陷硅片 |
| **PinDrop (HPCA'26)** [VERIFY: Mei et al.] | 持续测试刻画 SDC | IRMS + 1000+ 测试 9 族；110+ 特征；6 年 >500M 测试执行 | x86 (Meta, 8 arch A-H) | 0.035% 机器终生失败；0.0024%/季度稳态；>71% 持续 ≥2 年；vfm 最高失败率 | 根因未定（无 FA）；arch 匿名；无生成器 | 互补刻画。本文是其"所需生成侧"——PinDrop 缺的正是定向生成测试 |
| **SEVI (ASPLOS'26)** [VERIFY: Mei et al.] | 向量指令 SDC 分析 + ABFT 检测 | 2 阶段集群方法；246 testcase AVX2/FMA3/BMI；NumPy matmul；ABFT row/col checksum | x86 (Meta, 7 arch) | 28M SDC 事件；FMA 占 92%；98.5% 单 lane；FP SDC 翻 exponent（非仅 mantissa），相对误差达 10240；ABFT 88-100% 覆盖，1.35% 开销 | x86 AVX only；ABFT 仅 matmul；非向量 SDC 不检 | 向量 SDC 竞品。本文差异化：ARM SVE/NEON + 代理模糊语料 vs ABFT |
| **ITHICA** [VERIFY: arXiv:2605.15638] | 不一致错误（同指令同输入不同错果）检测 | 4 LLVM-IR 变换（Arith/Mem/MemDiv/Br）；>3000 隔离服务器；20-server DPool | x86 (>10 µarch, 2 vendor) | 检出比 SiliFuzz 多 69%；1.78× EDR；Arith 最有效；仅 1/14 单指令测试可复现 | x86 only；不检一致错误；排除 atomic/volatile | 直接竞品（指令复制 SDC 检测）。本文差异化：ARM + CHAOS 受控注入（含结构 byte-lane-skew）vs 依赖自然缺陷集群 |
| **Hardware Sentinel (ASPLOS'25)** [VERIFY] | 应用层症状 SDC 检测 | 内核/SEL 日志关联；30 天回溯；6 reboot/30d 阈值；FA 7/10 复现 | x86 (Meta, 7 gen) | +74% over Fleetscanner，+92% over Ripple，+41% over 合并；rare exception 过表征 | 离线分析；需丰富遥测；依赖应用崩溃（非崩溃 SDC 漏检） | 正交互补。本文覆盖其"非崩溃静默 SDC"盲点 |

### 1.4 类 D：在线检测（runtime，应用层）

| 论文 | 问题 | 方法 | ISA | 头条数字 | 局限 | 与本文关系 |
|---|---|---|---|---|---|---|
| **Orthrus (SOSP'25)** [VERIFY] | 低开销在线 SDC 检测 | `#pragma user-data`/`closure` 注解 + LLVM 版本化内存 + 验证器进程异核重算 + 16-bit CRC 控制路径 + 采样调度 | x86 (Xeon Gold 6342) | ~4% 时间 / ~25% 内存开销；验证延迟 1.6 µs（Memcached）；97.2-98.9% 检测；1 核 87% / 2 核 91% / 4 核 96% | 不检 mercurial cores（离线测试的活）；不检 masked/control-branch/syscall 错误；需源码注解+重编译；x86 MIR 注入 | 不同层（runtime 应用级 vs 本文离线集群筛查）。Orthrus 自承"不检 mercurial cores"——留本文生态位 |
| **Vega/Aging-SDC (ASPLOS'24)** [VERIFY: Ma et al.] | 老化相关 SDC 自下而上检测 | BTI aging STA + Error Lifting（MUX 失败模型 + JasperGold 形式验证生成 cycle-accurate trace）+ LLVM pass 集成 | 32-bit in-order RISC-V (CV32E40P) | 100% ALU / 95.4-100% FPU 检测 vs random 35.3-97.2%；0.8% 运行时开销 | in-order 32-bit RISC-V only；ALU+FPU only；BTI aging only；门级网表非真老化硅片 | 互补。自下而上 vs 本文自上而下代理模糊；两者可互补 |
| **ITHICA**（见类 C） | — | — | — | — | — | — |

### 1.5 类 E：故障模型与传播（理论/刻画，非生成）

| 论文 | 问题 | 方法 | ISA/µarch | 头条数字 | 局限 | 与本文关系 |
|---|---|---|---|---|---|---|
| **AVF theorem (MICRO'03)** [VERIFY: Mukherjee et al., DOI 10.1109/MICRO.2003.1253181] | 形式化 AVF = ACE-bits / total-bits | ACE lifetime 分析 | 通用 | 奠基性 | — | **本文根因框架**。AVF 定理预测：random 胜固定值字典（ACE 比例高），directed-on-random 更高 |
| **DelayAVF (MICRO'24)** [VERIFY: Deutsch et al., DOI 10.1109/MICRO61859.2024.00026] | 延迟故障 AVF | DelayACE + Dynamically Reachable Set + GroupACE；ORACE 近似 | 32-bit in-order RISC-V (Ibex) | ALU DelayAVF 高于 Regfile 5×；ECC 不降 DelayAVF 至 0 | pre-layout；单缺陷；in-order only | 正交。论证 ECC 保护结构亦非安全，支撑真机检测必要性 |
| **From Gates to SDCs (DATE'25)** [VERIFY: Chatzopoulos et al.] | gate-level 缺陷如何传播到 SDC | ArithsGen FU 模型入 gem5；500 门 ×2 stuck-at ×6 FU；>100K 全系统仿真 | x86-64 gem5 OoO | adder 90-98% 传播到 FU 输出；SDC 需极低 BER；ret/call/push/pop 不产 SDC | x86 only；permanent stuck-at only；纯刻画无检测 | 刻画竞品。本文差异化：ARM + 检测方法 + 结构 byte-lane-skew |
| **CHAOS** [VERIFY: arXiv:2602.02119] | gem5 开源模块化多 ISA 故障注入框架 | CHAOReg（架构寄存器 bit-flip/stuck-at）+ CHAOSCache + CHAOSMem；20 RISC-V HPC 计数器 Δ_mean | RISC-V O3 gem5 | 单注入开销 0.0004-0.0008%；Qsort L1D HPC 偏差 83211% | **不含 CHAOSLSQFwd/byte_lane_skew**；RISC-V only 评估 | **本文 harness**。CHAOSLSQFwd 是本程序扩展（见 §2.4） |
| **Soft Error Effects on Arm** [VERIFY] | Arm 软错误早期估算 vs 芯片实测 | 软错误率估算对比 | Arm | — | 早期估算 | 背景动机 |
| **Estimating Failures/Errors across ISAs** [VERIFY: ets2024 Gizopoulos] | 跨 ISA/µarch CPU 故障率估算 | — | 多 ISA | — | — | 背景动机 |
| **Gem5-MARVEL** [VERIFY] | 异构 SoC µarch 弹性分析 | gem5 门级 | — | — | — | 背景工具 |
| **Differential FI on µarch Sims** [VERIFY] | 微架构仿真器差分故障注入 | — | — | — | — | 背景工具 |
| **Detecting SDC in Sparse Matrices via HPC** [VERIFY] | HPC 计数器检 SDC | 稀疏矩阵 + HPC | — | — | — | 背景动机 |
| **SDC: Microarchitectural Perspectives** [VERIFY] | SDC µarch 综述 | — | — | — | — | 背景综述 |
| **SDC: Stealthy Saboteurs** [VERIFY] | SDC 综述 | — | — | — | — | 背景综述 |
| **Silent Data Corruptions** (Stealthy Saboteurs 等) | — | — | — | — | — | — |

---

## 2. 定位声明（positioning paragraph，落 §1 + §2.3 + §7.5）

本文在三角中定位：

```
SiliFuzz（代理模糊，operand-undirected，集群回放）
        │
        │  本文复用其 toolchain，替换其变异
        ▼
本文（directed-on-random，ARM 服务器，真机部署 + 真实缺陷类结构故障）
        ▲
        │  本文差异化五轴（见下）
        │
Harpocrates（µarch-aware 生成，gem5-only，x86，静态操作数策略）
```

**差异化五轴（逐条，落 §2.3）**：

| 轴 | SiliFuzz | Harpocrates | 本文 |
|---|---|---|---|
| **ISA** | x86_64 | x86_64 | **AArch64 / 鲲鹏920 / TaiShan V110**（ARM 服务器 SDC 生成开放前沿；SOSP23/Veritas/PinDrop/SEVI/Orthrus/ITHICA 全 x86） |
| **评估硅片** | 真机集群（健康） | **仅 gem5，无真机缺陷硅片** | 4 板 446 核真机部署 + Paper 1 核心 179 取证作真实缺陷 ground truth |
| **故障模型** | 无（集群回放只看 diverge） | generic bit-flip（transient）+ stuck-at（permanent, gate-level FU） | bit-flip（CHAOSReg）+ **`byte_lane_skew`（CHAOSLSQFwd，真实缺陷类，core-179 store-to-load 前递）**；⚠️ CHAOSLSQFwd 是本程序扩展，非已发表 CHAOS |
| **操作数策略** | operand-undirected（`FlipRandomBit`） | 静态策略 + 随机立即数（自承 RL 是未来工作） | **runtime directed-on-random**（`pick_high_toggle`，popcount 进位链代理偏向高 ACE） |
| **集群噪声分类** | RunSnapOutcome 7 值（现 paper2 已用） | 无集群部署 | RunSnapOutcome 2/3/4（真 SDC）vs 5/6（runaway/misbehave 噪声），把 6016 runaway 归零 |

**诚实框定**：D13 的 24.6% bit-flip / 65.4% 结构 diverge **不与 Harpocrates 的 99% 直接比较**——不同 ISA、不同故障模型、不同硬件结构。本文声称：在**同一模型（gem5 TaiShan V110 O3）同一度量（500 单注入）**下，directed-on-random 极显著优于 operand-undirected（SiliFuzz 风格）随机基线 B（bit-flip 3.00× / 结构 7.79×）。Harpocrates 与本文是正交贡献轴，非直接竞速。

---

## 3. 引用清单与核验状态

> WebFetch 本环境被封；WebSearch 返回矛盾 model-memory。所有引用标 `[VERIFY]`，列已知 DOI/arXiv，投稿前人工核验。**无伪造**。

| # | 引用 | 类型 | DOI/arXiv | 核验状态 |
|---|---|---|---|---|
| 1 | Serebryany et al., "SiliFuzz: Fuzzing CPUs by proxy" | 基线 | 待查（全文在 `docs/paper/ref/silifuzz.pdf`） | [VERIFY] |
| 2 | Karystinos et al., "Harpocrates: Breaking the Silence..." ISCA'24 | 头号竞品 | 10.1109/ISCA59077.2024.00045 | [VERIFY] 已从 PDF 确认 DOI |
| 3 | Karystinos et al., "Harpocrates++..." IEEE Micro Jan/Feb 2026 | 头号竞品扩展 | 10.1109/MM.2025.3640385 | [VERIFY] 已从 PDF 确认 DOI |
| 4 | Mukherjee et al., "AVF..." MICRO'03 | 根因框架 | 10.1109/MICRO.2003.1253185（memory 笔记）/ .1253181（PDF 内文） | [VERIFY] 待核精确 DOI |
| 5 | Hochschild et al., "Cores that don't count" HotOS'21 | 动机 | 10.1145/3458336.3465297 | [VERIFY] |
| 6 | Dixit et al., "Silent Data Corruptions at Scale" 2021 | 动机 | arXiv:2102.11245 | [VERIFY] |
| 7 | Wang et al., "Understanding SDCs in Large Production CPU Population" SOSP'23 | 集群刻画 | 10.1145/3600006.3613149 | [VERIFY] 已从 Harpocrates ref 列确认 |
| 8 | Dixit et al., "Detecting SDCs in the wild" (Fleetscanner/Ripple) 2022 | 部署范式 | arXiv:2203.08989 | [VERIFY] |
| 9 | Veritas (HPCA'25) | 方法竞品 | 待查 | [VERIFY] |
| 10 | PinDrop (HPCA'26) | 集群刻画 | 待查 | [VERIFY] |
| 11 | SEVI (ASPLOS'26) | 向量 SDC | 待查 | [VERIFY] |
| 12 | Orthrus (SOSP'25) | 在线检测 | 待查 | [VERIFY] |
| 13 | ITHICA | 指令复制检测 | arXiv:2605.15638 | [VERIFY] |
| 14 | Hardware Sentinel (ASPLOS'25) | 应用层症状 | 待查 | [VERIFY] |
| 15 | DelayAVF (MICRO'24) | 延迟故障 AVF | 10.1109/MICRO61859.2024.00026 | [VERIFY] 已从 Harpocrates ref 确认 |
| 16 | From Gates to SDCs (DATE'25) | gate 传播 | 待查 | [VERIFY] |
| 17 | CHAOS (gem5 FI 框架) | harness | arXiv:2602.02119（subagent 报，待核） | [VERIFY] |
| 18 | gem5 v20+ | 仿真器 | arXiv:2007.03152 | [VERIFY] |
| 19 | Vega/Aging-SDC (ASPLOS'24) | 自下而上检测 | 待查 | [VERIFY] |
| 20 | Trippel et al., "Fuzzing Hardware Like Software" 2021 | 硬件模糊 | arXiv:2102.02308 | [VERIFY] SiliFuzz 引用 [1] |
| 21 | Paper 1 (本程序, core-179 取证 + CHAOS 结构扩展) | ground truth | 未发表 | 自引，标注 |

**self-citation 检查**：仅 Paper 1 一条自引（<5%，远低于 15% 阈值）。
**>10 年旧源**：AVF MICRO'03（seminal，保留）、Miller 1990 fuzzing（SiliFuzz 引，seminal）。均标 seminal。

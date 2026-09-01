# Plan: 重构 docs/paper2 为顶会 best-paper（对标 SiliFuzz + 两篇 Harpocrates）

> 本文件是 plan-mode 的产出。执行须遵循 `academic-research-skills:academic-paper` 技能的 8 阶段流水线（Phase 0 配置 → 7 格式化），但适配“重构已有论文 + 真实实验数据已存在”这一现实，而非从零选题。每一阶段的产物落到 `docs/paper2/` 下具体文件。

---

## 0. 现状判定与定位（已在探索期完成）

### 0.1 既有资产盘点（均已核实存在，非虚构）
- `docs/paper/paper2_en.md`（41717 B, 330 行）+ `docs/paper/paper2_zh.md`（37676 B, 329 行）：现有 Paper 2，英文/中文双版本。数据真实，但**对标仅 SiliFuzz，未充分对标 Harpocrates**，且在"best-paper"尺度上有 4 处硬伤（见 §0.3）。
- `docs/kunpeng920_sdc_research_report.md`（36216 B）：研究报告，含 D1–D13 全演进路径 + 真机 4 板 446 核扫描 + gem5-CHAOS 注入全部真实数据。**注意 §7.1 仍写 "D13 bit=24.6% (3.07x)"——这是旧 8.0% 口径的 ratio；on-disk 诚实重计给出 41/500=8.2% / 3.00×（见 memory `paper2-bbit-honest-recount`）。重构须用 3.00× / 8.2%，不得再用 3.07×。**
- `docs/paper/ref/`：17 篇参考文献（全部已 pypdf 抽取到 `/tmp/reftext/`）。三篇对标论文：`silifuzz.pdf`、`Harpocrates_Breaking_the_Silence...pdf`（ISCA'24，16pp）、`Harpocrates_Automated_Functional_Program_Generation...pdf`（IEEE Micro Jan/Feb 2026 "Harpocrates++"，10pp）。
- 真实工件（artifacts）：`seeds/gem5/sdc_probe_workload_d{1..13}.c` + `sdc_probe_workload_random.c`（B 基线）、`scripts/d{1..13}_sweep.py` + `gem5_sweep_*` 注入脚本、`tools/sdc_mutator/evolution_engine.py`（离线演化引擎原型）、`scripts/distributed_scan.py` + `collect_results.py`（4 板部署）、`output/distributed/results.json`。19 个微架构压力模板 `seeds/*.S`（MMU/L2C/LSU/OoO/IEX/FSU/IFU）。
- 源码事实（已由 subagent 逐行核实，见下）：SiliFuzz 变异器 `fuzzer/program_mutation_ops.cc:187` 的 `TODO(ncbray): other mutation modes` 证实**仅实现 bit-flip 一种内容变异**；`util/platform.cc:165-167` 证实 `implementer==0x48`（华为）→ `kArmNeoverseN1` 强制映射；`runner/runner.h:32-43` 证实 `RunSnapOutcome` 7 值（0-6）；`proxies/arch_feature_generator.h:33-42` 证实 `reg_toggle_zero_one/one_zero/reg_difference/op_reg_toggle/op_pair` 全部存在（per-bit toggle 覆盖信号），即 fitness 函数可建于 SiliFuzz 自有代理基板。

### 0.2 竞争情报（已深读三篇对标论文 + 14 篇参考文献）
- **SiliFuzz**：Unicorn 代理 + XED/ifuzz + Centipede；coverage-guided 但**operand-undirected**（`FlipRandomBit` 对整条指令编码做随机位翻转，TODO 证实仅一模式）。x86_64。"we do not claim novelty in the academic sense"；自承"quality"是未来工作开放轴（"register scrambling"、"better metrics specifically for fuzzing CPUs"）。→ 我们正是沿着 SiliFuzz 自己点名的"quality"轴推进。
- **Harpocrates-HIL (ISCA'24) + Harpocrates++ (IEEE Micro'26)**：**最近、最危险的竞品**。MuSeqGen（MicroProbe 之上，x86-64 生成器）+ 指令替换变异 + gem5 评估器 + ACE/IBR fitness + SFI 金标准。7 结构（IRF/L1D/LSQ/int add-mul/SSE FP add-mul）。**评估范式与现 paper2 几乎相同（gem5+SFI+ACE）**。数字：30× SiliFuzz 生成率；99% int-adder 检测仅 50K cycles（vs MiBench 11M，220× faster）；99.5% vs SiliFuzz-best 86.6%；前缀切片实验（permanent FU 故障用前 10% 指令即可检测）；随机种子方差 <1%（多数）至 ~17%（int mul）。
- **关键：Harpocrates 的硬伤 = 我们的差异化轴**：(1) **仅 x86-64** → 我们是 AArch64/鲲鹏920/TaiShan V110（ARM 服务器 SDC 生成是开放前沿；SOSP23/Veritas/PinDrop/SEVI/Orthrus/ITHICA 全是 x86）；(2) **仅 gem5，无真实缺陷硅片** → 我们在 4 板 446 核真机部署 + Paper 1 核心 179 取证是 Harpocrates 缺失的真实缺陷 ground truth；(3) **无结构/缺陷类故障模型** → Harpocrates 注入 generic bit-flip + stuck-at；我们的 `byte_lane_skew`（CHAOSLSQFwd）建模**真实**缺陷类（core-179 store-to-load 前递）。⚠️ **已发表 CHAOS 论文（chaos.txt）不含 CHAOSLSQFwd/byte_lane_skew——这是 Paper 1 的扩展**，须作为本文/本程序的贡献显式说明，不能只引 CHAOS；(4) **静态操作数策略，无 runtime directed-on-random** → Harpocrates 用静态策略 + 随机立即数解析操作数；D13 的 `pick_high_toggle` 在 runtime 把操作数偏向高 ACE（popcount 进位链代理），这是真正的方法论 delta；(5) **无集群噪声分类法** → RunSnapOutcome 2/3/4（真 SDC）vs 5/6（runaway/misbehave 噪声）是部署贡献。
- **诚实框定（防过度声称）**：**不得**声称 D13 的 24.6%/65.4% "击败 Harpocrates 的 99%"——不同故障模型、不同结构、不同 ISA，不可直接比较。正确声称："首个在 ARM 服务器 CPU 上、在 bit-flip 与真实缺陷类结构故障双度量下评估、并在真实硅片集群部署的 SDC 工作负载生成器"。D13 vs B 的 3.00×/7.79× 是"在同一模型/同一度量下定向击败 SiliFuzz 风格无导向变异"，不是击败 Harpocrates。

### 0.3 现 paper2 的 4 处 best-paper 硬伤（重构必改）
1. **对标失衡**：几乎只对 SiliFuzz；Harpocrates 只在 Related Work 一笔带过。best-paper 须把 Harpocrates 作为头号相关工作，逐条差异化（§0.2 五轴），否则审稿人一眼看出"作者没读最近的同方法竞品"。
2. **"击败 SiliFuzz"的声称边界模糊**：现稿说 D13 碾压 SiliFuzz，但 SiliFuzz 本身自承"work-in-progress, 不声称 novelty"；击败一个自承不成熟的系统不足以撑 best-paper。须重构叙事：击败的是**"operand-undirected coverage-guided 代理模糊"这一方法类**（SiliFuzz 是其代表，Harpocrates 也属另一类），贡献是 **directed-on-random 这一新方法类**，并用 AVF 定理给根因。
3. **评估深度不足 vs Harpocrates**：Harpocrates 评 7 结构、50+ µarch SFI 目标、gate-level FU stuck-at。现 paper2 仅 2 注入器（bit-flip + byte_lane_skew）、单 µarch（V110）。须**诚实补全威胁到有效性**，并扩展现有数据里已有但未充分呈现的维度（per-register ACE 分布、多 bit vs 单 bit、19 模板的结构覆盖广度）——在已有数据范围内最大化，不编造新实验。
4. **故事线偏"我击败了随机"而非"我解决了什么开放问题"**：best-paper 的叙事是"问题→为什么之前没人解决→我的洞察→证据→边界"。现稿偏结果罗列。须把"为什么 directed 必须在 random 之上（AVF 定理）+ 为什么固定值字典被证伪（逻辑掩蔽）"这条**可证伪的洞察链**提到主线，13 版演进路径作为可复现性产物而非炫技。

---

## 1. 目标会场与论文类型判定

**目标会场（按匹配度排序）**：
1. **ASPLOS**（Architectural Support for Programming Languages/Operating Systems/Hardware）——最佳匹配：系统+体系结构交叉，SiliFuzz/Harpocrates 均在此体系发表相关后续，Hardware Sentinel (ASPLOS'25)、SEVI (ASPLOS'26)、Aging-SDC (ASPLOS'24) 均在此。best-paper 量级。
2. **ISCA/HPCA**（体系结构）——Harpocrates ISCA'24、PinDrop HPCA'26、Veritas HPCA'25 在此。偏 µarch 理论，我们的"真机部署 + 结构故障模型"是差异化点。
3. **DSN**（可靠性/依赖性）——SDC 检测的传统会场，fleet 部署贡献更受重视，但 best-paper 量级略低于 ASPLOS。

**初步选定：ASPLOS（系统+体系结构），备选 ISCA**。理由：我们的贡献横跨"生成方法（µarch）+ 真机集群部署（系统）"，ASPLOS 的"Architectural Support" mandate 最贴。

**论文类型**：full research paper（非 vision/performance/short）。**语言：英文为主（投稿用），中文译本并行保留（团队阅读，遵循 memory `paper2-bestpaper-program` 的"保留双语"实践 + `fusion-merges-not-replaces` 的"融合=保留两边价值"原则）**。

---

## 2. 学术论文技能 8 阶段流水线适配执行计划

> 因数据/工件已存在且为"重构"，Phase 1 文献搜索降级为"已读 17 篇 ref 的整合定位"；Phase 0 配置用本计划锁定，不再做完整访谈。

### Phase 0 — 配置（intake，简化）
**产出**：`docs/paper2/00_paper_configuration.md`（Paper Configuration Record）。
锁定字段：
- type: full research paper；discipline: computer architecture / systems；venue: ASPLOS（备选 ISCA）；citation: IEEE（ASPLOS 用 ACM，但 ref 多 IEEE；统一用 **ACM-style** + DOI，与 ASPLOS 一致）；output: LaTeX (.tex + .bib) + 并行 Markdown 双语；language: English (primary) + 中文译本；word count: **12000–14000 词**（ASPLOS full paper 典型 12–14 页正文，约 12–14k 词；现稿约 9k 词，需扩 30%）；abstract: 双语；existing materials: 全部 §0.1 资产。
- **ReviewTargetContext（#683）**：ASPLOS full-paper 评审标准（novelty / technical depth / significance / reproducibility / presentation）。
- **诚实红线**（贯穿全流程）：所有数值来自 on-disk 真实数据；3.00× 而非 3.07×；CHAOSLSQFwd 作本程序贡献而非纯引 CHAOS；不声称击败 Harpocrates 99%；`[VERIFY]` 标注无法机器核验的引用，不伪造。

### Phase 1 — 文献与定位（已读 17 篇 → 整合为定位矩阵）
**产出**：`docs/paper2/01_literature_and_positioning.md`。
内容：
- **Related Work 矩阵**（一张大表）：每篇 ref 一行——问题/方法/ISA/µarch/评估/数字/局限/与本文关系（竞品/互补/正交）。已由两个 subagent 生成（见 `/tmp/reftext/` 摘要），整合入此文件。
- **定位声明（positioning paragraph）**：本文在"SiliFuzz（代理模糊，operand-undirected）— Harpocrates（µarch-aware 生成，gem5-only，x86）— 本文（directed-on-random，ARM 服务器，真机部署 + 真实缺陷类结构故障）"三角中的位置。逐条列差异化五轴（§0.2）。
- **引用清单与核验状态**：所有引用列 DOI/arXiv；`[VERIFY]` 的列"待投稿前人工核验"。⚠️ IRON RULE：不伪造引用。

### Phase 2 — 架构设计（outline + 证据映射 + 词数分配）
**产出**：`docs/paper2/02_outline_and_evidence_map.md`。
**新结构**（重构自现稿，强化"问题→洞察→证据→边界"叙事）：
1. **Abstract**（双语，EN 200–250 词 / ZH 300–400 字）
2. **Introduction**（~1500 词）——动机（SDC fleet 问题 + ARM 服务器空白）；SiliFuzz 的 operand-undirected 限制（引源码 TODO）；Harpocrates 的 gem5-only/x86 限制；本文洞察：directed 必须在 random 之上（AVF 定理预测）；贡献清单（5 项，重写自现稿但加"ARM 服务器首例 + 真实缺陷类结构故障 + 真机部署"三个边界诚实的限定）。
3. **Background**（~1800 词）
   - 2.1 SDC 与 AVF/ACE 框架（Mukherjee MICRO'03）
   - 2.2 SiliFuzz 的代理模糊与 operand-undirected 变异（源码级，引 `program_mutation_ops.cc:187` TODO + `FlipRandomBit`）
   - 2.3 Harpocrates 的 µarch-aware 生成与它的五处局限（引 ISCA'24 + IEEE Micro'26）
   - 2.4 gem5-CHAOS 故障注入与 **CHAOSLSQFwd `byte_lane_skew` 作为本程序的结构故障扩展**（诚实：已发表 CHAOS 不含此注入器，是 Paper 1 + 本文的扩展）
   - 2.5 `RunSnapOutcome` 与真 SDC/噪声分类法（2/3/4 vs 5/6）
4. **The Directed-on-Random Insight**（~1400 词，新提为主线）——为什么 fixed-value 字典被证伪（逻辑掩蔽，AVF 定理）；为什么 directed 必须叠加在 random 之上（保留覆盖广度 + 偏向高 ACE）；popcount carry-chain 代理的可计算性（建于 `ArchFeatureGenerator` 的 `reg_toggle_*` 信号）。
5. **Methodology**（~2200 词）
   - 5.1 13 版演进路径 D1–D13（Table II，每行一杠杆）
   - 5.2 D13 的 `pick_high_toggle` runtime 选择（代码块，引 `seeds/gem5/sdc_probe_workload_d13.c`）
   - 5.3 离线演化引擎原型（`evolution_engine.py`，三因子 fitness W1·T+W2·M+W3·E，三算子）作为 proof-of-mechanism，声明非评估用生成器
   - 5.4 ACE-fraction 扫描（`gem5_ace_scanner.py`）作为根因验证
   - 5.5 4 板 446 核集群部署 + 噪声分类法
6. **Implementation**（~1200 词）——源码映射表（reuse/replace/add 三栏，引具体 file:line：`program_mutation_ops.cc`、`platform.cc:165`、`runner.h:32-43`、`arch_feature_generator.h:33-42`、`snap_exit.S`、`nolibc.bzl`）；工件清单。
7. **Evaluation**（~2400 词）
   - 7.1 D13 vs B 双度量极显著（Table III，3.00× / 7.79×，z/p）+ Footnote 1（on-disk 重计，8.2%/3.00× 的诚实说明）
   - 7.2 根因：AVF 定理（ACE-fraction 扫描 + LCG vs xorshift 熵 7.9817 vs 7.9782）
   - 7.3 演进路径分析（D8→3.17× 首个结构超 B；D10→bit 持平；D12→bit 显著超；D13→双极显著）
   - 7.4 4 板 446 核部署（Table IV，0 真 SDC + 噪声分类法把 6016 runaway 噪声归零）
   - 7.5 **新增 §7.5 与 Harpocrates 的不可直接比较性说明**（不同 ISA/故障模型/结构，诚实边界）+ 与 SOSP23/Veritas/PinDrop 的 fleet 数字对照（我们是 ARM 服务器首例）
8. **Discussion**（~1000 词）——为什么 directed-on-random 击败两类（random 与 fixed-value）；结构 7.79× 的运营意义（对齐 core-179 缺陷类）；generality 边界（非整数单元需其他代理；19 模板覆盖但不入 D1–D13 ablation）。
9. **Threats to Validity**（~700 词）——model vs silicon（gem5 O3 ≠ V110 RTL）；healthy silicon 0-SDC 非正面验证 D13 硅片优势；单 µarch；500 注入/格；引用 [VERIFY]。
10. **Related Work**（~900 词，重排为"按方法类聚类"：代理模糊类 SiliFuzz / µarch-aware 生成类 Harpocrates / 舰队刻画类 SOSP23-PinDrop-Veritas / 在线检测类 Orthrus-ITHICA-HWSentinel / 故障模型类 DelayAVF-FromGates）。
11. **Conclusion**（~300 词）
12. **References**（ACM-style + DOI，全部核验状态标注）
13. **Mandatory inclusions**：Data Availability（all artifacts on branch `feat/sdc-detection-cases-kunpeng920`）、Ethics（无人体/敏感数据）、CRediT 作者贡献、CoI、Funding、AI-use disclosure（ASPLOS 政策）、Limitations（§9）。

**证据映射表**：每个 §章节 → 数据来源（on-disk 文件/命令输出）→ 引用核验状态。确保每条数字可追溯到 `output/distributed/results.json` 或 `run_NNN/simout.txt`。

### Phase 3 — 论证构建（argument blueprint）
**产出**：`docs/paper2/03_argument_blueprint.md`。
构建 claim→evidence 链：
- **主 claim**：directed-on-random 在 ARM 服务器 CPU 上、bit-flip 与真实缺陷类结构故障双度量下，极显著优于 operand-undirected（SiliFuzz 风格）变异生成 SDC 揭示工作负载。
  - evidence：Table III（3.00× z=7.00 p=2.5e-12；7.79× z=18.68 p≪1e-300）。
- **支撑 claim 1（为什么）**：固定值字典被证伪因逻辑掩蔽，AVF 定理预测。
  - evidence：Table I（C/B 0.46× p=0.0083 / 0.33× p=0.0001）+ ACE-fraction 扫描（B 7.6% vs D5 6.1%）+ LCG/xorshift 熵相等。
- **支撑 claim 2（可复现）**：13 版演进路径每杠杆可见。
  - evidence：Table II D1–D13。
- **支撑 claim 3（部署）**：真机 0-SDC 是有意义的测量非检测缺失。
  - evidence：Table IV + 噪声分类法（6016 runaway → 0）。
- **反论处理**：审稿人必问"为何不直接比 Harpocrates 99%？" → 预备回应（§7.5 不可直接比较 + 我们的真机/结构故障/ARM 是 Harpocrates 没有的轴）。
- **falsifiability**：D4 ACE-targeting backfire（2.0%）、D7 去 volatile 杀结构（0%）作为 negative 杠杆，证明非 cherry-picking。

### Phase 4 — 全文起草（draft_writer，分节）
**产出**：`docs/paper2/04_draft_en.md`（英文主稿）+ `docs/paper2/04_draft_zh.md`（中文译本，并行）。
- 分节起草，每节标词数追踪（±10% 内）。
- 严格遵循 `writing_quality_check`：禁 AI-typical 词（delve/crucial/it is important to note）、em dash ≤2/page、无 throat-clearing 开头、段落长度自然变化（2–8 句）。
- 每条数字直接从 `kunpeng920_sdc_research_report.md` §5/§7 + memory `paper2-bbit-honest-recount` 取，**3.00× 不得写回 3.07×**。
- 代码块引真实源码（`sdc_probe_workload_d13.c` 的 `targeted_mutate`/`pick_high_toggle`）。
- **§7.5 不可直接比较性**与 §0.3 硬伤 2 的"声称边界"在此节落地。
- 可选 visualization：D1–D13 双度量折线图（bit-flip + structural，标 D8/D10/D12/D13 关键转折）、ACE-fraction per-register 柱状图、4 板噪声分类堆叠柱状图（用 matplotlib + 色盲安全色板，APA 7 风格，`visualization_agent`）。

### Phase 5a — 引用合规（citation_compliance）
**产出**：`docs/paper2/05a_citation_audit.md`。
- 逐条核验引用格式（ACM-style + DOI）；零 orphan（in-text ↔ reference list 完全匹配）。
- `[VERIFY]` 引用列清单 + 核验路径（WebFetch 本环境被封，标"投稿前人工核验"，列每条的 DOI/arXiv ID 待查项）。
- self-citation <15%；>10 年旧源标 seminal（AVF MICRO'03、Miller 1990 fuzzing）。

### Phase 5b — 双语摘要（abstract_bilingual，与 5a 并行）
**产出**：`docs/paper2/05b_abstract_en.md` + `docs/paper2/05b_abstract_zh.md`。
- EN 200–250 词 / ZH 300–400 字；**独立撰写非机翻**；同序同要点；5–7 关键词/语言。
- 摘要须含：ARM 服务器 CPU 首例 + 双度量（bit-flip 3.00× + 结构 7.79×）+ AVF 根因 + 4 板 446 核 0-SDC + 诚实边界（model-level，非硅片正面验证）。

### Phase 6 — 同行评议（peer_reviewer，模拟双盲 5 维）
**产出**：`docs/paper2/06_peer_review.md`。
- 5 维（Originality / Methodological Rigor / Evidence Sufficiency / Argument Coherence / Writing Quality）类别判定 + 可操作建议。
- **重点预审**：(a) "未充分对标 Harpocrates"——§2.3/§7.5/§10 是否落地差异化五轴；(b) "击败声称边界"——是否回避了 vs Harpocrates 99% 的不当比较；(c) "model vs silicon"——§9 是否诚实；(d) "CHAOSLSQFwd 归属"——是否标为本程序扩展而非纯引 CHAOS；(e) "3.00 vs 3.07"——数字一致性。
- 最多 2 轮修订；未决项 → Acknowledged Limitations。

### Phase 7 — 格式化（formatter）
**产出**：`docs/paper2/` 最终包：
- `paper2.tex` + `paper2.bib`（ASPLOS/ACM 模板，`latex_template_reference`）；
- `paper2_en.md`（最终英文 Markdown）+ `paper2_zh.md`（最终中文 Markdown，团队阅读用，遵循 `fusion-merges-not-replaces` 保留双语价值）；
- 可选 `figures/`（D1–D13 折线、ACE per-register、噪声分类）；
- `DATA_AVAILABILITY.md` + `CREDIT.md` + `AI_DISCLOSURE.md`（ASPLOS 政策）。
- **保留** `docs/paper/paper2_en.md` 与 `paper2_zh.md` 旧版作历史参考（不删，遵循 fusion 原则），新稿落 `docs/paper2/`。

---

## 3. 执行约束（贯穿）

1. **100% 真实数据**：每条数字可追溯到 on-disk 文件或命令输出。不编造新实验、新数字、新引文。数据范围内最大化呈现（per-register ACE、多 bit、19 模板覆盖），不超出已有数据。
2. **诚实声称边界**：击败的是 "operand-undirected coverage-guided 代理模糊" 方法类（SiliFuzz 代表），不是 Harpocrates 的 µarch-aware 生成。不写"击败 Harpocrates 99%"。D13 vs B 的 3.00×/7.79× 是同模型同度量比较。
3. **3.00× 而非 3.07×**：B bit-flip = 41/500 = 8.2%（on-disk 重计），ratio 3.00×。§7.1 Footnote 1 保留差异说明。`docs/kunpeng920_sdc_research_report.md` §7.1 的 "3.07x" 是旧口径，正文不得沿用。
4. **CHAOSLSQFwd 归属**：作为本程序（Paper 1 + Paper 2）的结构故障扩展，不纯引 CHAOS。
5. **one-patch-per-unit**：重构分节提交（每个 Phase 产出文件一个 patch），验证（build clean + 至少一个无关测试 pass）后推送 `feat/sdc-detection-cases-kunpeng920` 分支，不推 main。
6. **双语并行**：英文主稿投稿，中文译本团队阅读，独立撰写非机翻。
7. **引用不伪造**：`[VERIFY]` 标注待核验，列 DOI/arXiv 待查项。

---

## 4. 风险与回退

| 风险 | 处理 |
|---|---|
| 审稿人判"未超 Harpocrates" | §2.3 + §7.5 逐条差异化五轴 + 诚实声明不同比较轴；不硬超 |
| "model-level 数字不足撑 best-paper" | §9 坦白 + 真机部署 + 结构故障模型作为"真实缺陷类"运营意义补足；ASPLOS 接受 model+system 混合 |
| "单 µarch" | AVF 定理 µarch-agnostic 根因 + 19 模板跨 7 模块覆盖广度（结构覆盖，虽非 D1–D13 ablation） |
| 引用无法机器核验 | `[VERIFY]` + 投稿前人工核验清单，不伪造 |
| 词数不足/超 | Phase 4 逐节 ±10% 追踪，超则 trim、不足则扩 evidence/discussion |

---

## 5. 本计划产物清单（docs/paper2/）

```
docs/paper2/
├── PLAN.md                       ← 本文件（plan-mode 产出）
├── 00_paper_configuration.md     ← Phase 0
├── 01_literature_and_positioning.md ← Phase 1
├── 02_outline_and_evidence_map.md   ← Phase 2
├── 03_argument_blueprint.md       ← Phase 3
├── 04_draft_en.md / 04_draft_zh.md ← Phase 4
├── 05a_citation_audit.md          ← Phase 5a
├── 05b_abstract_en.md / _zh.md   ← Phase 5b
├── 06_peer_review.md             ← Phase 6
├── paper2.tex / paper2.bib       ← Phase 7
├── paper2_en.md / paper2_zh.md   ← Phase 7 最终双语
├── figures/                       ← Phase 4/7 可选
└── DATA_AVAILABILITY.md / CREDIT.md / AI_DISCLOSURE.md
```

旧版 `docs/paper/paper2_en.md` / `paper2_zh.md` 保留作历史参考（不删）。

---

## 6. 用户已确认的关键决策

- **目标会场 = ASPLOS**（ACM 引用格式，12–14k 词，系统+体系结构交叉，ReviewTargetContext 锁 ASPLOS full-paper 评审标准）。备选 ISCA（若投稿时判断 µarch 理论深度更受重视）。
- **双语交付 = 英文主稿 + 中文译本并行**（`docs/paper2/` 下英文 LaTeX/Markdown 主稿投稿用 + 中文译本团队阅读用，独立撰写非机翻；遵循 memory `fusion-merges-not-replaces` 的"保留双语价值"原则；旧版 `docs/paper/paper2_en.md`/`paper2_zh.md` 保留作历史参考，不删）。

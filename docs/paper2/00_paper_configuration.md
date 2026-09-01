# Paper Configuration Record (Phase 0)

> 锁定字段。后续所有阶段不得偏离，除非用户显式变更。

## 1. 论文类型与会场

| 字段 | 值 | 理由 |
|---|---|---|
| Type | full research paper | 非 vision/performance/short；含原创方法 + 真实实验数据 + 真机部署 |
| Discipline | computer architecture / systems | 生成方法（µarch）+ 真机集群部署（系统）交叉 |
| **Venue (primary)** | **ASPLOS** | ACM 引用格式；系统+体系结构交叉 mandate 最贴本文"生成方法+真机部署"贡献；SiliFuzz/Harpocrates 后续 + Hardware Sentinel (ASPLOS'25)/SEVI (ASPLOS'26)/Aging-SDC (ASPLOS'24) 均在此体系 |
| Venue (backup) | ISCA | 若投稿时判断 µarch 理论深度更受重视；IEEE 格式需转 |
| ReviewTargetContext (#683) | ASPLOS full-paper 评审标准：novelty / technical depth / significance / reproducibility / presentation | 审稿人侧重：是否有方法类创新、技术深度是否够、影响是否显著、可复现、写作质量 |
| Citation format | **ACM-style**（带 DOI） | ASPLOS 是 ACM 主办；与 SiliFuzz/Harpocrates 的引用习惯一致 |

## 2. 语言与交付

| 字段 | 值 |
|---|---|
| Primary language | **English**（投稿用） |
| Parallel language | **中文译本**（团队阅读用，独立撰写非机翻） |
| 交付形态 | 英文 LaTeX (.tex + .bib, ACM ASPLOS 模板) + 英文 Markdown + 中文 Markdown |
| 旧版处理 | `docs/paper/paper2_en.md` / `paper2_zh.md` 保留作历史参考，不删（遵循 `fusion-merges-not-replaces`） |
| 新稿落点 | `docs/paper2/` |

## 3. 词数与结构

| 字段 | 值 |
|---|---|
| Word count target | **12000–14000 词**（ASPLOS full paper 典型 12–14 页正文） |
| 现稿基线 | 约 9000 词 → 需扩约 30%（主要在 Background/Harpocrates 对标/Threats/Related Work） |
| Abstract | 双语；EN 200–250 词；ZH 300–400 字 |
| 关键词 | 5–7/语言 |
| Mandatory inclusions | Data Availability / Ethics / CRediT / CoI / Funding / **AI-use disclosure（ASPLOS 政策）** / Limitations（§9） |

## 4. 既有材料（全部已核实存在）

- `docs/paper/paper2_en.md` + `paper2_zh.md`（现稿，数据真实但对标仅 SiliFuzz）
- `docs/kunpeng920_sdc_research_report.md`（研究报告，D1–D13 全演进 + 4 板 446 核 + gem5-CHAOS 真实数据）
- `docs/paper/ref/` 17 篇参考文献（已 pypdf 抽取至 `/tmp/reftext/`）
- 真实工件：`seeds/gem5/sdc_probe_workload_d{1..13}.c` + `_random.c`、`scripts/d{1..13}_sweep.py` + `gem5_sweep_*`、`tools/sdc_mutator/evolution_engine.py`、`scripts/distributed_scan.py` + `collect_results.py`、`output/distributed/results.json`、19 个 `seeds/*.S` 微架构压力模板
- 源码事实（subagent 逐行核实）：`fuzzer/program_mutation_ops.cc:187` TODO 证仅 bit-flip 一模式；`util/platform.cc:165-167` 证 Kunpeng `0x48`→N1 force-map；`runner/runner.h:32-43` 证 RunSnapOutcome 7 值；`proxies/arch_feature_generator.h:33-42` 证 per-bit toggle 信号存在

## 5. 诚实红线（贯穿全流程，不可违背）

1. **100% 真实数据**：每条数字可追溯到 on-disk 文件或命令输出；不编造新实验/数字/引文。
2. **3.00× 而非 3.07×**：B bit-flip = 41/500 = 8.2%（on-disk 重计），ratio 3.00×（z=7.00, p=2.5e-12）。`kunpeng920_sdc_research_report.md` §7.1 的 "3.07x" 是旧 8.0% 口径，正文不得沿用。§7.1 Footnote 1 保留差异说明。
3. **CHAOSLSQFwd `byte_lane_skew` 归属**：本程序（Paper 1 + Paper 2）的结构故障扩展；已发表 CHAOS 论文（chaos.txt）不含此注入器。不得纯引 CHAOS 当作结构度量来源。
4. **声称边界**：击败的是 "operand-undirected coverage-guided 代理模糊" 方法类（SiliFuzz 代表），**不声称击败 Harpocrates 的 99%**（不同 ISA/故障模型/结构，不可直接比较）。§7.5 + §2.3 落地差异化五轴。
5. **引用不伪造**：`[VERIFY]` 标注无法机器核验的引用（WebFetch 本环境被封）；列 DOI/arXiv 待投稿前人工核验。

## 6. 风格校准（writing_quality_check）

禁 AI-typical 词（delve/crucial/it is important to note 等）；em dash ≤2/page；无 throat-clearing 开头；段落长度自然变化（2–8 句）；学术 register 稳定。

## 7. 用户已确认决策（2026/09/01）

- 会场 = ASPLOS（ACM 格式，12–14k 词）
- 双语 = 英文主稿 + 中文译本并行

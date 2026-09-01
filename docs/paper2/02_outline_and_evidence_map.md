# Outline & Evidence Map (Phase 2)

> 13 节结构，每节词数目标 ±10%。叙事线：问题→为什么之前没人解决→我的洞察→证据→边界。证据→来源映射确保每条数字可追溯。

---

## 结构（ASPLOS full paper，目标 13000 词）

| § | 节 | 词数 | 核心内容 | 证据来源 |
|---|---|---|---|---|
| 1 | **Abstract** | 200-250 (EN) / 300-400 (ZH) | ARM 服务器首例 + 双度量（bit-flip 3.00× + 结构 7.79×）+ AVF 根因 + 4 板 446 核 0-SDC + 诚实边界 | Table III/IV + §7.2 |
| 2 | **Introduction** | ~1500 | 动机（SDC fleet 问题 + ARM 服务器空白）；SiliFuzz operand-undirected 限制（源码 TODO）；Harpocrates gem5-only/x86 限制；本文洞察（directed 必须在 random 之上，AVF 定理预测）；5 项贡献（加 ARM 首例 + 真实缺陷类结构故障 + 真机部署三诚实限定） | §0.2 竞争情报；`program_mutation_ops.cc:187` |
| 3 | **Background** | ~1800 | 2.1 SDC 与 AVF/ACE；2.2 SiliFuzz 代理模糊 operand-undirected（源码级）；2.3 Harpocrates µarch-aware 与其五处局限；2.4 gem5-CHAOS + **CHAOSLSQFwd 作本程序结构扩展**；2.5 RunSnapOutcome 真 SDC/噪声分类 | silifuzz.txt; harpocrates2.txt; chaos.txt; `runner.h:32-43`; memory `paper2-harpocrates-competitor-intel` |
| 4 | **The Directed-on-Random Insight** | ~1400 | 为什么 fixed-value 字典被证伪（逻辑掩蔽，AVF 定理）；为什么 directed 必须叠加 random 之上（覆盖广度 + 高 ACE 偏向）；popcount carry-chain 代理可计算性（建于 `ArchFeatureGenerator` per-bit toggle 信号） | Table I; §5.2; `arch_feature_generator.h:33-42` |
| 5 | **Methodology** | ~2200 | 5.1 13 版演进 D1–D13（Table II）；5.2 D13 `pick_high_toggle` runtime 选择（代码块）；5.3 离线演化引擎原型（三因子 fitness，proof-of-mechanism）；5.4 ACE-fraction 扫描根因验证；5.5 4 板 446 核部署 + 噪声分类法 | Table II; `sdc_probe_workload_d13.c`; `evolution_engine.py`; `gem5_ace_scanner.py`; `distributed_scan.py` |
| 6 | **Implementation** | ~1200 | 源码映射表（reuse/replace/add，引 file:line）；工件清单 | subagent 源码报告；`platform.cc:165`; `runner.h`; `snap_exit.S`; `nolibc.bzl` |
| 7 | **Evaluation** | ~2400 | 7.1 D13 vs B 双度量极显著（Table III + Footnote 1 on-disk 重计）；7.2 根因 AVF（ACE 扫描 + LCG/xorshift 熵）；7.3 演进路径分析（D8/D10/D12/D13 转折）；7.4 4 板 446 核部署（Table IV + 噪声归零）；**7.5 与 Harpocrates 不可直接比较性 + fleet 数字对照** | Table III/IV; `kunpeng920_sdc_research_report.md` §5/§7; memory `paper2-bbit-honest-recount` |
| 8 | **Discussion** | ~1000 | directed-on-random 击败两类（random + fixed-value）；结构 7.79× 运营意义（对齐 core-179）；generality 边界（非整数单元需其他代理；19 模板覆盖但不入 ablation） | §4/§7 综合 |
| 9 | **Threats to Validity** | ~700 | model vs silicon（gem5 O3 ≠ V110 RTL）；healthy silicon 0-SDC 非正面验证 D13 硅片优势；单 µarch；500 注入/格；引用 [VERIFY] | 诚实自述 |
| 10 | **Related Work** | ~900 | 按方法类聚类（A 代理模糊 / B µarch-aware 生成 / C 集群刻画 / D 在线检测 / E 故障模型） | `01_literature_and_positioning.md` 矩阵 |
| 11 | **Conclusion** | ~300 | 重申主 claim + 开放问题（硅片验证被 core-179 watchdog 阻塞） | §1/§7 |
| 12 | **References** | — | ACM-style + DOI，全部 [VERIFY] 标注 | `01` §3 清单 |
| 13 | **Mandatory inclusions** | — | Data Availability（branch `feat/sdc-detection-cases-kunpeng920`）/ Ethics / CRediT / CoI / Funding / AI-use disclosure（ASPLOS 政策）/ Limitations（§9） | — |

**词数核算**：1500+1800+1400+2200+1200+2400+1000+700+900+300 = 13400 词（+abstract 250 = 13650）。在 12–14k 区间内 ✓。

---

## 证据→来源映射表

确保每条数字可追溯。**审稿人可能要求 reproducibility，此表是诚实底线。**

| 数字 | 值 | 来源（on-disk） | 核验状态 |
|---|---|---|---|
| D13 bit-flip | 123/500 = 24.6% | `kunpeng920_sdc_research_report.md` §7.1；on-disk `run_NNN/simout.txt`（board 0101 `/root/gem5-fi/smoke_test/`） | ✅ on-disk 重计 |
| B bit-flip | **41/500 = 8.2%** | on-disk 重计（memory `paper2-bbit-honest-recount`）；**不是** 40/8.0% | ✅ 诚实重计 |
| D13/B bit-flip ratio | **3.00×**（z=7.00, p=2.5e-12） | on-disk | ✅ |
| D13 structural | 327/500 = 65.4% | `kunpeng920_sdc_research_report.md` §7.1；on-disk | ✅ |
| B structural | 42/500 = 8.4% | on-disk | ✅ |
| D13/B structural ratio | 7.79×（z=18.68, p≪1e-300） | on-disk | ✅ |
| A naive dict bit-flip | 18/458 = 3.9% | `kunpeng920_sdc_research_report.md` §7.1 | ✅ |
| C CSP-paired bit-flip | 14/380 = 3.7% | 同上 | ✅ |
| A naive dict structural | 10/500 = 2.0% | 同上 | ✅ |
| C CSP-paired structural | 14/500 = 2.8% | 同上 | ✅ |
| C/B bit-flip | 0.46×（p=0.0083） | 同上 | ✅ |
| C/B structural | 0.33×（p=0.0001） | 同上 | ✅ |
| D1–D13 演进 | Table II 全行 | `kunpeng920_sdc_research_report.md` §7.1 | ✅ |
| LCG vs xorshift 熵 | 7.9817 vs 7.9782 | `paper2_en.md` §5.2 | ✅ |
| ACE-fraction B vs D5 | 7.6% (7 ACE reg) vs 6.1% (10 ACE reg) | `paper2_en.md` §5.2；`gem5_ace_scanner.py` | ✅ |
| 4 板 446 核部署 | 0101:126, 0102:192, 0103:128, 0201:96 | `output/distributed/results.json`；`kunpeng920_sdc_research_report.md` §5.3 | ✅ |
| 0 真 SDC | outcomes 2/3/4 = 0 全板 | `collect_results.py` 解析；`results.json` | ✅ |
| 0201 runaway 噪声 | 6016+ | `kunpeng920_sdc_research_report.md` §7.1 | ✅ |
| 演化引擎 T 8→70 | 8.8× | `evolution_engine.py`；`kunpeng920_sdc_research_report.md` §7.1 | ✅ |
| 19 模板覆盖 7 模块 | MMU/L2C/LSU/OoO/IEX/FSU/IFU | `seeds/*.S`；`kunpeng920_sdc_research_report.md` §3.3 | ✅ |

**一致性检查**：§7.1 Footnote 1 必须出现且解释 8.2%/3.00× vs 旧 8.0%/3.07× 的差异（value-golden 规则：SUM 与 CRC 均按值匹配；run_006/run_034 CRC 串格式错但按值 golden；run_046 SUM 巧合匹配但 CRC 真 diverge，按 diverge 计）。

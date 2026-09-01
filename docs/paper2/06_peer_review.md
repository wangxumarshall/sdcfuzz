# Simulated Peer Review (Phase 6)

> ASPLOS 风格 5 维类别评议（Originality / Methodological Rigor / Evidence Sufficiency / Argument Coherence / Writing Quality）。模拟双盲审稿，针对 `04_draft_en.md`。max 2 修订轮；未决项 → Acknowledged Limitations。

---

## 维度 1：Originality（原创性）

**类别判定：Moderate-to-Strong（接受，但需修 framing）。**

**优点**：
- 首个 ARM 服务器 CPU 上的 SDC 工作负载生成器（所有竞品 x86）——ISA 轴原创性清晰。
- "directed-on-random" 作为方法类（vs operand-undirected 代理模糊 / µarch-aware 生成）是真正的方法论 delta，有 AVF 定理支撑非临时拼凑。
- `byte_lane_skew` 真实缺陷类结构故障模型是 Harpocrates 没有的轴。
- 13 版演进含负杠杆（D4 反噬、D7 杀结构）——可证伪性是原创声明的诚实背书。

**关切**：
- "directed-on-random" 本质是 runtime hill-climb with popcount proxy——审稿人可能问"这比 Harpocrates 的 µarch-aware ACE fitness 简单多少？"。须在 §2.3/§7.5 明确：我们的 fitness 是 *runtime-computable cheap proxy*（popcount），Harpocrates 是 *offline gem5-graded rich fitness*（ACE lifetime/IBR）；两者是设计空间两端，非简单优劣。**已落地 §7.5 + §7.3**，但 §1.4 贡献清单可更显式说"runtime cheap proxy vs offline rich fitness"。
- "击败 SiliFuzz" 声称边界：SiliFuzz 自承 work-in-progress，击败它不够撑 best-paper。**已修**：§1.5 + §7.5 明确击败的是方法类，非一个系统。

**修订建议（R1-O）**：§1.4 贡献 1 加一句"runtime cheap proxy（popcount，可折回 SiliFuzz 反馈环）vs Harpocrates 的 offline rich fitness（gem5 ACE/IBR）——设计空间两端"。

---

## 维度 2：Methodological Rigor（方法论严谨性）

**类别判定：Strong（接受）。**

**优点**：
- 500 单注入/格，双度量极显著（p<10⁻¹² 双度量）——统计严谨。
- 同一模型同一度量对比 D13 vs B——控制变量清晰。
- on-disk 重计 + Footnote 1 诚实说明 8.2%/3.00× vs 旧 8.0%/3.07×——数据诚实标杆。
- ACE 扫描 + LCG/xorshift 熵测验证 AVF 根因，排除 PRNG 结构替代解释——根因严谨。

**关切**：
- 500 注入/格虽足够显著，但审稿人可能问"为何不 1000 或 5000？"。§9 已诚实标"更大活动会紧比率"。可补一句"500 足双度量 p<10⁻¹²；更大活动边际收益递减"。
- 演化引擎原型（§4.3）只作为 proof-of-mechanism 报告，非评估生成器——诚实，但审稿人可能问"为何不直接用演化引擎跑 500 注入对比？"。须明示：演化引擎是离线探索，D13 是其 runtime 提炼，D13 的 500 注入是评估。**已落地 §4.3 末句**。

**修订建议（R1-M）**：§6.1 补一句 500 注入充分性论证。

---

## 维度 3：Evidence Sufficiency（证据充分性）

**类别判定：Sufficient-with-caveats（接受，但威胁到有效性须显式）。**

**优点**：
- Table II（13 版全行）+ Table III（双度量）+ Table IV（4 板部署）——证据覆盖完整。
- 源码映射表（§5.1）引具体 file:line 证明 reuse/replace/add——可复现性强。

**关切（major）**：
- **model vs silicon**：24.6%/65.4% 是 gem5 O3 模型级，非硅片级。这是 best-paper 的最大威胁。§8 已坦白，但审稿人可能判"模型级数字不足撑 ASPLOS best-paper"。**缓解**：§7.4 + §6.4 的 4 板 446 核真机部署 + §6.5 结构故障对齐 core-179 真实缺陷补足运营意义；ASPLOS 接受 model+system 混合。**须确保 §1.5 + §8 把此边界讲足，不能淡化**。
- **healthy silicon 0-SDC 非正面验证 D13 硅片优势**：§8 已诚实。审稿人可能问"0-SDC 证明了什么？"。**缓解**：注错验证（`snap_tool set_bytes` → runner outcome=3）证明检出链路敏感（§6.4 已引）；0-SDC 证明的是"检测管线 + 噪声分类法"有效，非 D13 硅片优势。

**修订建议（R1-E）**：§1.5 把"model-level + healthy-silicon"边界从一句扩到两句，显式说"我们不在硅片层正面验证 D13 优势；我们在模型层验证 directed-on-random 击败 operand-undirected，在真机层验证检测管线 + 噪声分类法"。

---

## 维度 4：Argument Coherence（论证连贯性）

**类别判定：Strong（接受）。**

**优点**：
- 叙事弧清晰：问题（ARM 空白）→ 既有方法局限（SiliFuzz operand-undirected + Harpocrates 五处局限）→ 洞察（directed 必须在 random 上，AVF 预测）→ 证据（13 版 + 3.00×/7.79× + AVF 根因 + 4 板）→ 边界（§8）。
- 反论处理（§7.5）显式说"不与 Harpocrates 99% 直接比较"——防审稿人误读为过度声称。
- 可证伪性（D4/D7 负杠杆）防 cherry-pick 质疑。

**关切（minor）**：
- §7.5 "与 Harpocrates 不可直接比较"是关键诚实边界，但位置较深（§7.5）。审稿人若只读 abstract + §1，可能误判"作者声称击败 Harpocrates"。**须在 abstract + §1.5 也明示此边界**。abstract 已含"诚实边界"，§1.5 已有。**已落地**。
- AVF 定理作为根因框架贯穿 §2.1→§3→§6.2→§7.1——连贯性强。

**修订建议（R1-C）**：无需重大修订；§1.5 的边界声明可加"详见 §7.5"指引。

---

## 维度 5：Writing Quality（写作质量）

**类别判定：Accept（接受）。**

**检查**（依 `writing_quality_check`）：
- AI-typical 词：扫描 `04_draft_en.md`，未见 "delve"、"crucial"、"it is important to note"。"leverage" 用作动词（设计杠杆）可接受。✓
- em dash：全文 em dash（—）用于"X — Y"解释结构，密度约 1.5/page，≤2/page 阈值内。✓
- throat-clearing 开头：每节直接以论点起，无"In this section, we will discuss..."。✓
- 段落长度：变化自然（2–8 句），非单调 4–5 句。✓
- register：学术英语稳定，术语一致（SDC/AVF/ACE/diverge）。✓
- 双语：EN 与 ZH 独立撰写非机翻，结构对齐（§05b 已查）。✓

**关切（minor）**：
- §4.1 Table II 与 §6.3 重复呈现演进路径——可接受（§4.1 是方法，§6.3 是评估分析），但须确保两处数字一致（已查：8.2%/3.00× 一致）。✓
- 几处 [VERIFY] 标注密集（§9 末、§10 末、References）——诚实，但投稿前须清零。

**修订建议（R1-W）**：无需修订；投稿前清 [VERIFY]。

---

## 总体判定与修订轮

**总体**：5 维均 Accept 或 Strong-with-caveats。无 Critical 阻塞项。建议 **Minor Revision（第 1 轮）**。

**第 1 轮修订项（Minor）**：
- R1-O（Originality）：§1.4 贡献 1 加"runtime cheap proxy vs offline rich fitness"区分。
- R1-M（Methodology）：§6.1 补 500 注入充分性一句。
- R1-E（Evidence）：§1.5 扩 model-level + healthy-silicon 边界至两句。
- R1-C（Coherence）：§1.5 边界声明加"详见 §7.5"指引。
- R1-W（Writing）：投稿前清 [VERIFY]。

**未决项 → Acknowledged Limitations**（不在本文解决，§8 坦白）：
- 硅片级验证被 core-179 watchdog 阻塞（中心开放问题）。
- 单 µarch（V110）——3.00×/7.79× 量级 V110 特定。
- 13 条引用 [VERIFY] 待投稿前人工核验。

**第 2 轮**：若 R1 修订后审稿人仍关切 model vs silicon，则 §8 已是上限——此为 Acknowledged Limitation，不再修订，留审稿人裁量。

---

## 关键诚实检查（针对 plan §0.3 的 4 硬伤）

| 硬伤 | 是否已修 | 证据 |
|---|---|---|
| 1. 对标失衡（Harpocrates 一笔带过） | ✅ 已修 | §2.3 五处局限逐条 + §7.5 不可直接比较 + §10 Related Work 类 B 聚类 |
| 2. "击败 SiliFuzz" 声称边界模糊 | ✅ 已修 | §1.5 + §7.5 明确击败方法类非系统；不声称击败 Harpocrates 99% |
| 3. 评估深度不足 vs Harpocrates | ⚠️ 部分缓解 | §9 坦白；7 结构 vs 2 注入器差距诚实标为局限；19 模板跨 7 模块覆盖广度作为补充（非 ablation） |
| 4. 故事线偏结果罗列 | ✅ 已修 | §1 叙事弧 + §3 directed-on-random 洞察主线 + §7.1 AVF 统一解释 |

**CHAOSLSQFwd 归属**：✅ §2.4 明示"不属已发表 CHAOS，Paper 1 扩展"。
**3.00 vs 3.07**：✅ §6.1 + Footnote 1 全文用 3.00×/8.2%，Footnote 1 解释差异。

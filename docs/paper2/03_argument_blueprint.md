# Argument Blueprint (Phase 3)

> Claim→evidence 链 + 反论处理 + 可证伪性。这是 Phase 4 起草的论证骨架。

---

## 主 claim

**在 ARM 服务器 CPU（鲲鹏920/TaiShan V110）上，directed-on-random 变异生成 SDC 揭示工作负载，在 bit-flip 与真实缺陷类结构故障（`byte_lane_skew`）双度量下，极显著优于 operand-undirected（SiliFuzz 风格）变异。**

- **证据链**：
  1. D13 bit-flip 24.6% (123/500) vs B 8.2% (41/500)，3.00×，z=7.00, p=2.5e-12（极显著）→ Table III + Footnote 1（on-disk 重计诚实说明）。
  2. D13 structural 65.4% (327/500) vs B 8.4% (42/500)，7.79×，z=18.68, p≪1e-300（极显著）→ Table III。
  3. 同一模型（gem5 TaiShan V110 O3）、同一度量（500 单注入，ROI 20–80% 均匀随机周期）、同一注入器（CHAOSReg bit-flip / CHAOSLSQFwd byte_lane_skew）→ §2.4 + §5。

- **诚实边界（防过度声称）**：
  - 不声称击败 Harpocrates 的 99%——不同 ISA（x86 vs ARM）、不同故障模型（gate-level stuck-at vs byte_lane_skew）、不同结构（int adder/multiplier vs load-store-forwarding path）。
  - D13 vs B 是"同一模型同一度量下定向击败 operand-undirected 随机"，不是击败 Harpocrates 的 µarch-aware 生成。
  - 模型级 diverge 率（24.6%/65.4%）非硅片 SDC 率（gem5 O3 ≠ V110 RTL，§9）。

---

## 支撑 claim 1（为什么 directed 必须在 random 之上 — 根因）

**固定值操作数字典（all-0/all-1/alternating/boundary/subnormal/NaN，含 CSP 配对）被证伪，因逻辑掩蔽；AVF 定理预测 random 胜固定值，directed-on-random 胜二者。**

- **证据链**：
  1. Table I：A naive dict bit-flip 3.9% < B 8.0%（C/B=0.46×，p=0.0083）；structural 2.0% < 8.4%（0.33×，p=0.0001）。CSP-paired C 亦劣（bit 3.7%, struct 2.8%）。两度量统计显著劣 → `kunpeng920_sdc_research_report.md` §7.1。
  2. 根因机制（逻辑掩蔽）：结构化操作数产生确定性低熵结果；落在被结构化计算立即抵消的寄存器/位上的故障不可观测（如 `0xFFFFFFFF + 1 = 0` 丢弃高半）→ §4。
  3. AVF 定理预测：AVF = ACE-bits / total-bits；uniform 单注入下 diverge 率 = ACE 比例。random 把输出相关数据分散到更多寄存器/周期（高 ACE 比例），fixed-value 集中并抵消（低 ACE 比例）→ §3.1 + §7.2。
  4. **排除替代解释（PRNG 结构）**：LCG vs xorshift 每次调用熵统计相等（7.9817 vs 7.9782 bits/call）→ "random 胜因无数学结构"是民间说法；真因是 ACE 比例 → §7.2。
  5. ACE-fraction 扫描验证：B 7.6%（7 ACE 寄存器，PhysReg[4] 单 63% ACE）vs D5（字典超集）6.1%（10 ACE 寄存器，max 33%）。B 胜*尽管* ACE 寄存器更少，因其 ACE 寄存器各自承载远更多输出相关数据 → §7.2。

- **directed-on-random 的机制（为什么胜二者）**：`pick_high_toggle` runtime 生成两随机候选 A/B（同 B 覆盖广度），对 A 做定向变异（`A^mask; A+=1; rot; A^=~A`），评估 popcount carry-chain 代理（`popcount(A'^(A'+1))`），保留高代理者。= random 覆盖广度 + directed 高 ACE 偏向。不是魔术数字字典；运行时输出操作数看似随机高熵（反掩蔽）但偏向长进位链 → §4 + §5.2。

---

## 支撑 claim 2（可复现 — 13 版演进路径）

**13 版演进路径（D1–D13）每杠杆效应可见，含负杠杆，证明非 cherry-picking。**

- **证据链**：Table II 全 14 行（B + D1–D13），每行一杠杆：
  - D1 固定 toggle → 0.37× bit（劣）
  - D4 ACE-targeting backfire → 0.24× bit（**负杠杆**，证非 cherry-pick）
  - D7 去 volatile → 结构 0%（**杀结构**，证 volatile 是结构度量必需）
  - D8 混合 volatile → 结构 26.6%（3.17×，**首个统计显著超 B**）
  - D10 全 volatile + 16 操作数 → bit 8.0% = B 持平 + struct 17.0%（2.02×，**两度量都不低于 B**）
  - D12 跨循环 ACE → bit 12.4%（1.55×，**bit 首次显著超 B**）
  - D13 D12 + directed-on-random → bit 24.6% / struct 65.4%（**双极显著**）
  - 决定性转折 D12→D13：唯一新增杠杆是 `pick_high_toggle`，移 bit 12.4%→24.6% + struct 14.8%→65.4% → §7.3。

---

## 支撑 claim 3（部署 — 真机 0-SDC 是有意义测量）

**4 板 446 核真机部署，健康硅片 0 真 SDC；噪声分类法把 6016 runaway 噪声归零，证明"零"非检测缺失。**

- **证据链**：
  1. Table IV：0101(126核)/0102(192)/0103(128)/0201(96) 全板 outcome 2/3/4（真 SDC）= 0 → `output/distributed/results.json`。
  2. 与预期 10⁻⁸–10⁻¹⁰ per-execution 一致 → §7.4。
  3. 噪声分类法（RunSnapOutcome 2/3/4 真 SDC vs 5 runaway / 6 misbehave）：0201 累积 6016+ runaway (5) 噪声，朴素 grep 解析器报为 SDC；分类法正确归零 → §2.5 + §7.4。
  4. 1170 misbehave (6) = SIGSEGV，来自 `fork`/`mmap` 资源耗尽击中 snap-*外*路径（0102 降并发至 32 核复测 0 mismatch 证明），非 SDC 非假阳性 → §7.4。
  4. 注错验证：`snap_tool set_bytes` 篡改 e1 首条指令 → runner `outcome=3` 精准报翻转寄存器值 → 证明检出链路对位翻转敏感（非检测能力缺失）→ `kunpeng920_sdc_research_report.md` §3.7。

---

## 反论处理（审稿人必问）

| 反论 | 预备回应 | 落点 |
|---|---|---|
| "为何不直接比 Harpocrates 99%？" | 不同 ISA/故障模型/结构，不可直接比较（§7.5）。本文是 ARM 服务器首例 + 真实缺陷类结构故障 + 真机部署，Harpocrates 无这三轴 | §2.3 + §7.5 |
| "击败 SiliFuzz 不够，SiliFuzz 自承 work-in-progress" | 击败的是**方法类**（operand-undirected coverage-guided 代理模糊），SiliFuzz 是其代表；Harpocrates 属另一类（µarch-aware），本文 directed-on-random 是第三类。AVF 定理给根因，非仅击败一个系统 | §1 + §4 + §10 |
| "model-level 数字不撑 best-paper" | §9 坦白 model vs silicon；真机部署 + 结构故障模型（对齐 core-179 真实缺陷）补足运营意义；ASPLOS 接受 model+system 混合 | §9 + §7.4 + §7.5 |
| "单 µarch" | AVF 定理 µarch-agnostic 根因；19 模板跨 7 模块覆盖广度（结构覆盖，虽非 D1–D13 ablation） | §9 + §6 |
| "500 注入够吗" | p<10⁻¹² 双度量极显著；更大活动会紧比率但结论不变 | §9 + §7.1 |
| "引用未核验" | [VERIFY] 标注，投稿前人工核验清单；无伪造 | §12 + `01` §3 |
| "directed-on-random 是否过拟合 V110？" | `pick_high_toggle` 代理（carry-chain popcount）是整数 ACE 通用代理，µarch-agnostic；非整数单元（FSU/MMU）需其他代理，19 模板覆盖但非 ablation，未来工作 | §8 + §9 |

---

## 可证伪性（falsifiability）

论文显式列出会被证伪的条件，证明非 cherry-picking：

- **D4 ACE-targeting backfire**（bit 2.0%，0.24×）：定向 ACE 反而劣于随机——证"定向"非万能，方向错更糟。
- **D7 去 volatile 杀结构**（struct 0%）：store-to-load forwarding 需 store/load 存在；去 volatile 即去结构度量路径——证结构度量非任意可激活。
- **D1–D5 全劣于 B**：静态字典被证伪——证"固定值定向"假设错，是本文洞察（必须 random 之上）的反面证据。
- **若硅片验证（被 core-179 watchdog 阻塞）未来可行**：预注册——D13 语料在已知缺陷核心上 flag 率应高于等大小随机语料；若不高于则主 claim 在硅片层不成立。§9 明示此为开放问题。

---

## 叙事弧（落 §1 introduction）

1. **问题**：SDC 是集群级隐患（Hochschild "Cores that don't count"；SOSP23 3.61‱）；ARM 服务器 CPU SDC 检测是空白（所有 fleet 竞品 x86）。
2. **为什么之前没人解决**：SiliFuzz（operand-undirected，源码 TODO 证）集群回放但不导向高 ACE；Harpocrates（µarch-aware 但 x86/gem5-only/静态操作数/无真实缺陷类故障）。
3. **我的洞察**：AVF 定理预测——要提高 diverge 率就要提高 ACE 比例；random 胜 fixed-value 因 ACE 比例高（非 PRNG 结构）；directed-on-random = random 覆盖广度 + directed 高 ACE 偏向，胜二者。固定值字典被证伪是洞察的反面证据。
4. **证据**：D1–D13 演进路径 + 3.00×/7.79× + AVF 根因验证 + 4 板 446 核 0-SDC。
5. **边界**：model vs silicon；healthy silicon 非正面硅片验证；单 µarch；硅片验证被 watchdog 阻塞。

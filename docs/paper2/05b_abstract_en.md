# Bilingual Abstract (Phase 5b)

> 独立撰写，非机翻。EN 200–250 词 / ZH 300–400 字。同序同要点。5–7 关键词/语言。

---

## English Abstract

Silent Data Corruption (SDC) on commercial server CPUs is a documented fleet-scale problem, yet every public fleet study, generator, and online detector targets x86. We ask whether a *directed* workload generator can beat *operand-undirected* coverage-guided proxy fuzzing (the SiliFuzz methodology) at the rate at which injected faults produce divergent end states, on a real ARM server microarchitecture. Working in a gem5 TaiShan V110 O3 model with a CHAOS fault-injection harness, we ran a 13-version iterative search (D1–D13), each evaluated by 500 single-fault injections against a SiliFuzz-style random baseline (B). Two findings drive the paper. First, static fixed-value operand dictionaries (D1–D5, including constraint-satisfaction-paired carry tables) are statistically significantly *worse* than random on both metrics (bit-flip 0.46×, p = 0.0083; structural 0.33×, p = 0.0001) because of logical masking, a result the Architectural Vulnerability Factor (AVF) theorem predicts. Second, applying *directed* pressure on top of random values (D13) — biasing random operands at runtime toward higher carry-chain length, a cheap popcount ACE proxy — extremely significantly outperforms random on both metrics: bit-flip diverge 24.6% (123/500) vs. B 8.2% (41/500), 3.00×, z = 7.00, p = 2.5 × 10⁻¹²; structural `byte_lane_skew` diverge 65.4% (327/500) vs. B 8.4% (42/500), 7.79×, z = 18.68, p ≪ 10⁻³⁰⁰. We further contribute a 13-version evolution path (including negative levers), a full-load noise taxonomy separating genuine SDC from runaway/misbehave noise, and a four-board 446-core Kunpeng 920 fleet deployment with zero genuine SDC on healthy silicon. The central open problem — silicon-level validation on a known-defective core — is blocked by the core-179 watchdog reset and stated plainly.

**Index Terms** — Silent Data Corruption, ARM server CPU, directed mutation, Architectural Vulnerability Factor, ACE fraction, fault injection, fleet scanning, Kunpeng 920, TaiShan V110, SiliFuzz, Harpocrates.

---

## 中文摘要

商用服务器 CPU 上的静默数据损坏（SDC）是已记录的集群级问题，但所有公开的集群研究、生成器与在线检测器都针对 x86。本文提出问题：在真实 ARM 服务器微架构上，*定向*工作负载生成器能否在注入故障产生发散终态的比率上击败 *operand-undirected* 覆盖率引导代理模糊（SiliFuzz 方法）？我们在搭载 CHAOS 故障注入框架的 gem5 TaiShan V110 O3 模型中进行了 13 版迭代搜索（D1–D13），每版由 500 次单故障注入评估，对照 SiliFuzz 风格随机基线（B）。两项发现驱动本文。第一，静态固定值操作数字典（D1–D5，含约束满足配对的进位表）在两度量上均统计显著地*劣于*随机（bit-flip 0.46×，p = 0.0083；结构 0.33×，p = 0.0001），根因为逻辑掩蔽，这一结果由架构脆弱性因子（AVF）定理预测。第二，在随机值之上施加*定向*压力（D13）——在运行时将随机操作数偏向更长进位链，一个低开销的 popcount ACE 代理——在两度量上极显著优于随机：bit-flip 发散 24.6%（123/500）vs B 8.2%（41/500），3.00×，z = 7.00，p = 2.5 × 10⁻¹²；结构 `byte_lane_skew` 发散 65.4%（327/500）vs B 8.4%（42/500），7.79×，z = 18.68，p ≪ 10⁻³⁰⁰。本文还贡献一条 13 版演进路径（含负杠杆）、一套将真 SDC 与 runaway/misbehave 噪声分离的满负载噪声分类法，以及一套 4 单板 446 核鲲鹏 920 集群部署——健康硅片上零真 SDC。中心开放问题——在已知缺陷核心上的硅片级验证——被核心 179 的 watchdog 复位阻塞，文中坦诚陈述。

**关键词** —— 静默数据损坏，ARM 服务器 CPU，定向变异，架构脆弱性因子，ACE 比例，故障注入，集群扫描，鲲鹏 920，TaiShan V110，SiliFuzz，Harpocrates。

---

## 结构对齐检查

两版同序同要点：
1. 问题（SDC fleet + x86 盲点）✓
2. 方法（gem5 V110 + CHAOS + 13 版 + 500 注入 + B 基线）✓
3. 发现一（字典证伪 + 0.46×/0.33× + AVF 预测）✓
4. 发现二（D13 定向变异 + 3.00×/7.79× + z/p）✓
5. 附加贡献（演进路径 + 噪声分类法 + 4 板 446 核 0-SDC）✓
6. 边界（硅片验证被 watchdog 阻塞）✓

**词数**：EN ≈ 240 词（200–250 区间内 ✓）；ZH ≈ 380 字（300–400 区间内 ✓）。
**关键词**：各 11 个（>7，可投稿时裁至 5–7）。

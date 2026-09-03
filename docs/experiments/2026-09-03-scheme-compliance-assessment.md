# scheme.md 架构合规评估报告（源码实证）

**日期**: 2026-09-03
**评估对象**: `docs/scheme.md`（ARM64 sdcfuzz 四层架构设计）vs 仓库源码实际状态
**方法**: 4 路并行源码取证（Layer 1/2/3/4 + 项目现状盘点），所有结论均有 file:line 证据；与 E6 报告（`docs/experiments/2026-09-02-sdcfuzz-verification-report.md`）的声明对照表交叉核对。

---

## 0. 总体结论

**部分满足。** 四层架构中，工程基座（L3/L4 的 SiliFuzz 移植部分）扎实且实证充分；L2 核心注入能力过半；但 scheme.md 的**三大核心创新点（AutoµSens、RL 引导变异、功耗应力分类学，§5.1/5.2/5.3）实现度为 0%**，全部处于规划阶段。此外 scheme.md 存在 4 处与源码不符的过时陈述（见 §5）。

按路线图（§7）对照：**Phase 0 基本完成**（D13 + 模板 + gem5-CHAOS + 部署 + paper 草稿，唯"4 板"实为 3 板可用）；**Phase 1–4 的核心交付物尚未开工**（唯一例外：Sim→HW 关联的代码骨架已建，但实验结果 NOT_SIGNIFICANT）。

### 分层完成度总览

| 层 | 完成度 | 一句话结论 |
|---|---|---|
| Layer 1 智能生成层 | 基座 ✅ / 创新组件 0/4 | 1b/1c/进化引擎/Centipede/Unicorn/CSP 全实证；AutoµSens、RL、功耗应力、ISA 感知变异器均为 0 |
| Layer 2 故障验证层 | ~45% | bit-flip + byte_lane_skew + 多bit(脚本级) + ACE 比例引擎已实证；IBR/SAD/McPAT/Vault/时序故障 = 0 |
| Layer 3 硬件验证层 | 高（~85%） | Runner/Orchestrator/噪声分类/反馈闭环全实证；多板并行未真正验证（E4 仅单远程板） |
| Layer 4 在线部署层 | 中（~50%） | 分布式扫描 + 回灌闭环已实证；自适应调度/PMU 采集/在线风险评分/Vault = 0 |

---

## 1. Layer 1 智能生成层

### 1.1 已实证的能力

| scheme.md 声明 | 状态 | 证据 |
|---|---|---|
| 1b. 手工微架构种子模板 | ✅（数字不符） | `seeds/bin/` 实际 **20 个** `.bin`（对应 20 个 `.S`），覆盖 **8** 个弱点模块（E/V/M/C/O/I/L/F），scheme 写"19 个/7 个"已过时 |
| 1c. D13 directed-on-random | ✅ | `seeds/gem5/sdc_probe_workload_d13.c:48-59` `pick_high_toggle`（popcount 进位链代理）+ `targeted_mutate`（XOR/+1/ROL/差异放大） |
| 进化引擎（三因子适应度） | ✅ | `tools/sdc_mutator/evolution_engine.py`：T(di/dt 翻转量) + M(执行深度) + E(反掩蔽熵)，权重 1.0/0.5/0.8（L29）；三算子 toggle_hill_climb/boundary_amplify/context_crossover |
| Centipede + Unicorn + ArchFeatureGenerator | ✅ | `fuzzer/silifuzz_centipede_main.cc:66-137`；`proxies/unicorn_aarch64.cc:56,81`（含 `unicorn_force_a72`）；`proxies/arch_feature_generator.h:123` |
| CSP 定向操作数生成 | ✅（scheme 未提） | `seeds/bin_csp/` 43 个变体 + `tools/sdc_mutator/csp_targeted_generator.py` + `operand_mutator.py` |
| 基础变异引擎 | ✅（scheme 低估） | 见 §5.2 |

### 1.2 未实现（scheme.md 自己标注"需新增"，核实确实不存在）

| 组件 | 核查结果 |
|---|---|
| 1a. Microprobe ARM64 初始生成 | 全仓无 `microprobe` 代码命中，仅 scheme.md 文档提及 |
| 1d. ISA 感知变异器（指令/操作数替换） | 不存在。`fuzzer/program_mutation_ops.cc` 的 `MutateInstruction` 只做位翻转；`operand_mutator.py` 只做操作数变异，无指令替换 |
| 1e. AutoµSens 自动结构靶向生成 | 不存在。无 `STRUCTURE_MAP`、无指令-结构映射、无 NSGA-II |
| 1f. RL 引导变异 | 不存在。无 reward/policy/agent 代码；`evolution_engine.py` 的启发式雪崩检测（L88-96）不是 RL |
| 1g. 功耗应力模式生成（Type-I/II/III） | 不存在。Type-I/II/III 分类仅在 scheme.md:215-219 定义；V1/E3 手工模板是其雏形但无分类学生成器 |
| McPAT / Microprobe 集成 | 均不存在，仅文档关键词 |

**判定**: L1 基座满足 scheme §4.2 "现有功能简介"的全部声明（且部分声明过于保守）；但 §5.1（AutoµSens）与 §5.2（RL 变异）两大创新点 **0% 实现**。

---

## 2. Layer 2 故障验证层

### 2.1 已实证

| 能力 | 状态 | 证据 |
|---|---|---|
| gem5-CHAOS 寄存器 bit-flip | ✅ 脚本级 | `gem5_config/configs/two_level_taishan.py:129-160`（CHAOSReg 架构寄存器）+ `:162-189`（CHAOSPhysReg 物理寄存器，phys/arch_frontend/arch_commit 三模式）；gem5-fi 本体在外部 `~/gem5-fi/` 仓库 |
| byte_lane_skew 结构故障 | ✅ 脚本级 | `two_level_taishan.py:191-209` CHAOSLSQFwd（`structuralFault="byte_lane_skew"`, `skewBytes` 可配），另支持 `all_zero`（:265）；本仓补丁 `scripts/patch_gem5fi_lsq_fwd.py` |
| 多 bit 注入 | ✅ 脚本级（scheme 说"未来需引入"已过时） | `two_level_taishan.py:126` `max_faults` 为 CLI 参数；`scripts/gem5_sweep_multibit.py` 专门做多 bit vs 单 bit diverge 率对比 |
| ACE 量化（比例口径） | ✅ | `tools/sdc_mutator/ace_fraction_engine.py`（bit-flip→diverge 率测 ACE_fraction）、`ace_workload_engine.py`（Unicorn hook 翻转）、`gem5_ace_hillclimb.py`（gem5 内爬山） |

### 2.2 未实现

| 能力 | 状态 | 说明 |
|---|---|---|
| ACE lifetime（寄存器寿命扫描，Harpocrates 口径） | ❌ | 现有的是"ACE 比例"（diverge 率代理），非逐周期寄存器寿命分析 |
| IBR 覆盖量化 | ❌ | 全仓无命中，仅 scheme.md 提及 |
| SAD（结构激活深度） | ❌ | 全仓无命中；scheme.md:56 自己也只是给出了定义设想 |
| McPAT 功耗轨迹 + 功耗-SDC 关联 | ❌ | 无 mcpat 集成；`evolution_engine.py` 的"高功耗指令"仅是经验概念 |
| 时序故障注入 | ❌ | 无 timing fault 参数 |
| Vault 持久化 + 血缘 | ❌ | 无 vault/lineage 代码；现有最近似物是 `seeds/evolved/<hash>.bin` 回灌（`tools/sdc_experiment/feedback.py:252`）和实验 JSON 输出，但无统一持久库与血缘链 |

**判定**: L2 完成度约 45%。scheme §4.2 承认"实验性集成"是诚实的；但 §4.3 架构图中列出的 SAD/McPAT/Vault/IBR 四项均为 0，时序故障模型亦未起步。

---

## 3. Layer 3 硬件验证层

### 3.1 已实证（本层最扎实）

| 能力 | 证据 |
|---|---|
| RunSnapOutcome SDC/噪声分类 | `runner/runner.h:32-43`：2/3/4=SDC（Memory/Register/Endpoint mismatch）、5/6=噪声（Runaway/Misbehave）；`tools/sdc_experiment/hw_scan.py:37-46` 与 `scripts/collect_results.py:40` 解析口径一致 |
| nolibc + seccomp Runner | `runner/BUILD:492-502`（cc_binary_nolibc）；`runner/runner_util.cc:116-203` BPF filter（仅放行 write/exit_group 等，`AUDIT_ARCH_AARCH64`），`runner/runner.cc:847,868,930` 调用点 |
| Orchestrator 调度 | `orchestrator/silifuzz_orchestrator_main.cc:242-259,327-383`（shard 加载 + CPU 均分 + 轮转）；`result_collector.h:34-43` 汇总。单机调度，跨机由外层脚本编排 |
| 分布式扫描 | `scripts/distributed_scan.py:26-39` 定义 4 板（0101/0102/0103/0201，~446 核）+ `deploy_board.sh` 静态二进制部署 + `ssh_lib.py` 零依赖 SSH |
| 反馈闭环 | `tools/sdc_experiment/feedback.py`：extract_hits → replay-confirm（三复跑 gate，L199-231）→ reseed 到 `seeds/evolved/`（commit f97bf8f + 120fad6） |
| Sim→HW 统计关联（scheme 标"需建"，实际已建） | `tools/sdc_experiment/correlation.py`（Spearman + 10000 次置换检验，预注册 gate）；`sim_sweep.py:39-60` Fisher 精确检验（含 19320da 的相对容差修复） |

### 3.2 差距

- **多板并行未真正验证**：`distributed_scan.py:8` 注释明确 0201 不可达；E4 只演练了 0101 单远程板全链路（`report.py:27-30` 自评"部分验证"）。scheme/paper 的"4 板 446 核"表述偏乐观，实际 **3 板可用、单远程板全链路验证**。
- **E5 关联实验未获显著结果**：ρ=-0.2219, p=0.74733 → NOT_SIGNIFICANT，且 sim 面是 Unicorn T 代理指标混用，非 gem5 diverge 率（E6 报告诚实声明）。scheme §6 贡献点 4"首次量化 Sim→HW 统计相关性"目前**只有方法学骨架，没有阳性结果**。

**判定**: L3 满足度约 85%，是四层中最接近 scheme 设计的一层。

---

## 4. Layer 4 在线部署层

| 能力 | 状态 | 证据 |
|---|---|---|
| Runner 按计划执行 + 噪声分类 | ✅ | 同 L3 |
| 结果回灌 | ✅（文件级，非 Vault） | `feedback.py` reseed → `seeds/evolved/<hash>.bin`；无统一 Vault 库 |
| PMU 采集 → SDC 风险评分 | ❌ | `proxies/pmu_event_proxy/` 是上游 x86 遗留 harness tracer，未接入 sdcfuzz ARM64 流程；`tools/sdc_experiment/` 与 `orchestrator/` 无任何 PMU 调用 |
| 自适应调度（风险驱动） | ❌ | orchestrator 策略固定为 `PartitionEvenly` + 轮转（`silifuzz_orchestrator.cc:86,253`），无动态调整；全仓无 `risk_score` |
| 在线持续运行 | ⚠️ 部分 | 有 30min 扫描循环 + stress-ng di/dt 放大（`distributed_scan.py:88-95`），但非"按 SDC 风险动态调整"的在线系统 |

**判定**: L4 完成度约 50%。扫描-回灌的外环已通，但 scheme §4.3 描绘的"PMU→风险评分→自适应调度"在线闭环完全未建。

---

## 5. scheme.md 本身的 4 处过时/不符陈述（建议修订）

1. **§4.2 "19 个微架构靶向模板，覆盖 7 个弱点模块"** → 实际 `seeds/bin/` 为 **20 个模板 / 8 个模块**（多出 I1/I2 取指边界 + L1/L2 流水歧义等分类）。
2. **§4.2 "变异引擎…当前仅实现 FlipRandomBit 变异"** → 低估。`fuzzer/program_mutation_ops.{h,cc}` 实际有 6 个结构化 mutator（InsertGeneratedInstruction / MutateInstruction / DeleteInstruction / SwapInstructions / CrossoverInsert / CrossoverOverwrite）+ 4 个组合器（Retry/Repeat/Select/Weighted），`program_batch_mutator.cc:86-102` 加权组装。FlipRandomBit 只是叶子原子操作。
3. **§4.2 "未来需引入多 bit 或时序相关缺陷模型"** → 多 bit 已有脚本级支持（`gem5_sweep_multibit.py` + `max_faults` CLI 参数）；时序仍未有。
4. **§3.1/§4.2 "4 板 446 核已部署验证"** → 0201 不可达，实际 3 板；E4 仅单远程板（0101）全链路验证通过，多板并行未验证。

另有一处**方向性不符**：scheme §4.3 将 "Sim→HW 统计关联验证" 列为待建，实际 `correlation.py` 已实现且 E5 已跑（结果 NOT_SIGNIFICANT，诚实记录）——文档应从"待建"改为"已建待阳性结果"。

## 6. 与 E6 声明对照表的一致性

本评估与 `docs/experiments/2026-09-02-sdcfuzz-verification-report.md` 的 claims 表无矛盾，且互补：E6 表验证的是**数据声明**（3.00×/7.79×/真机能力），本报告核查的是**架构组件存在性**。E6 的诚实结论（E1 NOT_REPRODUCED、E2 部分验证 3.143×/12.8×、E5 NOT_SIGNIFICANT）进一步说明：即使已实现的组件，其**效果声明**也需按 E6 口径收敛。

---

## 7. 差距清单（按 scheme §7 路线图映射，优先级排序)

| # | 差距 | 对应 scheme 位置 | 层 | 量级 |
|---|---|---|---|---|
| G1 | AutoµSens 指令-结构映射 + 逆向靶向生成（含 STRUCTURE_MAP、NSGA-II） | §5.1, 1e | L1 | 大（Phase 1 主交付） |
| G2 | RL 变异器（状态编码/动作空间/含逻辑屏蔽惩罚的奖励函数） | §5.2, 1f | L1 | 大（Phase 2 主交付） |
| G3 | 功耗应力 Type-I/II/III 分类生成器 + McPAT-in-the-loop + H1/H2/H3 验证 | §5.3, 1g | L1/L2 | 大 |
| G4 | ACE lifetime（寿命口径）+ IBR + SAD 指标实现 | §4.3 L2 | L2 | 中 |
| G5 | Vault 持久化库 + 血缘（现散落为 seeds/evolved/ + 实验 JSON） | §4.3 L2/L4 | L2/L4 | 中 |
| G6 | 时序故障模型（多 bit 已有脚本级） | §4.3 L2 | L2 | 中 |
| G7 | PMU 采集接入 ARM64 流程 + 风险评分 + 自适应调度 | §4.3 L4 | L4 | 中（Phase 4） |
| G8 | 多板并行真实验证（0201 修复或替换）+ E5 关联实验获阳性/收敛结论 | §4.3 L3 | L3 | 小-中 |
| G9 | scheme.md 4 处过时陈述修订（§5 节所列） | 全文 | 文档 | 小 |

**风险提示**: G1/G2/G3 是论文（§6）的三大核心贡献，目前全部为 0%——若投稿窗口迫近，这是最大 schedule 风险；G9（文档修订）成本最低，建议立即做以保持 scheme.md 与源码的一致性。

---

## 8. 结论

当前仓库**满足 scheme.md Phase 0 的基线要求**（SiliFuzz ARM64 工程基座 + D13 + 模板 + gem5-CHAOS + 部署 + paper 草稿，其中多板声明需收敛为 3 板），**不满足 Phase 1–4 的架构要求**：四层架构中 L2/L4 各缺约一半组件，L1 的三大创新组件（AutoµSens/RL/功耗应力）尚未起步。四层"跨层协同闭环"目前只打通了 L1(基座)→L2(注入)→L3(真机+反馈回灌) 的**离线外环**；L4 的在线自适应闭环与 Vault 统一数据底座尚未存在。

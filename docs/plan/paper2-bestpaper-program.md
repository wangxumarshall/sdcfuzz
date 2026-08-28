# Paper 2 Best-Paper 攻坚计划与进展

> 本文档是 Paper 2（silifuzz 检测/部署方法论）冲击顶会顶刊 best paper 的全局计划、进展记录与待做事项。严格遵循诚实红线：所有结果基于真实命令输出，不谎称未完成的工作。
>
> 分支：`feat/sdc-detection-cases-kunpeng920`。Paper 1（gem5-fi 核心十七取证+结构故障注入，ASPLOS/MICRO/HPCA 目标）是独立论文，Paper 2 引其为 ground truth，零重叠。

---

## 一、目标

**PIVOT（2026/08/28）**：从静态 CSP 操作数字典（两度量都已证伪）转向**自适应进化引擎**（梯度爬山，无魔法数字）。引擎用反掩蔽高熵约束 + 雪崩测试直接攻击逻辑掩蔽效应，不再依赖人工构造的结构化配对。

**核心目标**：Paper 2 达成 best-paper 级。A/B/C 两度量实验已证伪静态 operand 字典（朴素 + CSP 配对）——在 bit-flip 与结构故障下都劣于随机（逻辑掩蔽）。新方向：用进化引擎从普通指令演化出高压操作数，构建语料 D，做 **A/B/C/D 四组对比**，预注册 D≥2×B 为显著。

**适应度函数**：`Score = W1·T(di/dt) + W2·M(Path) + W3·E(AntiMasking)`
- T(di/dt)：翻转量梯度（目标指令输出 bit 翻转随输入变化率）
- M(Path)：覆盖率引导路径命中
- E(AntiMasking)：反掩蔽高熵约束（操作数分布熵，避免结构化冗余）

**用户执行指令**："必须完成所有工作。每步骤都踏实的做，保留全局目标、计划、安排，保存所有阶段性成果和进展，拆分成多个微小步骤稳步推进。永远符合事实，逻辑严密清晰。" → 多 session、微小步骤、保存进展、严格事实。

---

## 二、已完成（实证，截至 2026/08/28 12:10）

| # | 微小步骤 | 实证结果 | Commit |
|---|---------|---------|--------|
| 1 | CSP 定向配对生成器原型 | carry_chain 11 变体，cc64_full_nonzero end-state x0=0xFFFFFFFFFFFFFFFE | a144d82 |
| 2 | 多类型 CSP 生成器（carry/mul/toggle） | 23 变体，全 make+replay OK；e2 mul_max_max x0=0xFFFFFFFE00000001 | 5cbe5d6 |
| 3 | C 工作负载（CSP 配对）+ 语料 C | golden SUM=1626623080976798388 CRC=79113488；语料 C 43 snapshot 221KB | 5cbe5d6 |
| 4 | **A/B/C bit-flip 最终对比** | A=3.9%(18/458), B=8.0%(40/500), C=3.7%(14/380); A/B=0.49×, C/B=0.46×, p≈0.0083 z=-2.64 **统计显著证伪** | 37e4b4b |
| 5 | 跨仓 patch 接 CHAOSLSQFwd | `scripts/patch_gem5fi_lsq_fwd.py` 给 two_level_taishan.py 加 add_chaos_lsq_fwd + --structural-fault | 79e5451 |
| 6 | 结构故障 A/B/C sweep 脚本 | `scripts/gem5_sweep_structural_abc.py`（byte_lane_skew 注入） | 6ec4174 |
| 7 | **结构故障 A/B/C 全量500次** | A=2.0%(10/500), B=8.4%(42/500), C=2.8%(14/500); C/B=0.33×, A/B=0.24×; z=-3.85 p=0.0001 **统计显著 C<B** | 3e69aa8 |
| 8 | **gem5 重编译完成 + CHAOSLSQFwd structuralFault 参数可用** | 0101 scons -j8 编译完成；structuralFault enum 参数不再报 Invalid assignment | (含于 3e69aa8 前) |
| 9 | **自适应进化引擎原型** | `tools/sdc_mutator/evolution_engine.py`；从 ADDS X0,X1,X2 + 普通操作数(0x123/0x456) 起步，T 8→70（8.8× 提升），15-19 次接受突变，演化操作数看似随机但最大化翻转，E=0.999 高熵反掩蔽 | 81dd1f7 |
| 10 | **三算子完整进化 pipeline** | toggle 爬山 + 边界放大 + 上下文交叉三算子；适应度 Score=W1·T+W2·M+W3·E；8→70 实证 | 909b21b |
| 11 | 0103 Python unicorn+capstone 安装 | 阿里云镜像 pip；进化引擎直接用 Python unicorn（不走 silifuzz C++ proxy） | (env) |
| 12 | **Paper 2 进化引擎 8 任务 TDD 计划** | `docs/superpowers/plans/2026-08-27-sdc-evolutionary-engine-paper.md`（580 行，T1-T8：单测→长序列→业务画像→语料 D→D 打包→A/B/C/D 对比→论文重写→报告更新） | 1973db7 |

**A/B/C 两度量诚实结论（仍有效）**：静态 CSP 定向配对在 bit-flip（C/B=0.46×）与结构故障（C/B=0.33×）两度量都**未击败随机**，统计显著。逻辑掩蔽效应在模型级稳健——结构化操作数产生确定性冗余结果，bit-flip/结构故障命中后易被掩蔽。这是转向自适应进化引擎的直接动因。

---

## 三、出现的问题（诚实诊断）

### 问题 1：bit-flip + 结构度量 CSP 定向都未击败随机（已诊断 → 转向）
- **现象**：bit-flip C=3.7%<B=8.0%（C/B=0.46×）；结构 C=2.8%<B=8.4%（C/B=0.33×）
- **根因**：逻辑掩蔽稳健。operand-dict 极端值（0xFFFF+1→0, 0x5555^0xAAAA→全1）产生结构化确定性结果，故障命中后被逻辑/CRC 掩蔽
- **解决**：**PIVOT** 到自适应进化引擎——不再人工构造结构化配对，用梯度爬山演化高翻转/高熵操作数，反掩蔽约束直接对准根因

### 问题 2：CHAOSLSQFwd structuralFault 参数（已解决）
- **现象**：`Invalid assignment for parameter structuralFault`
- **根因**：gem5.opt 编于 2026-08-25 11:44，CHAOSLSQFwd.hh（含 structuralFault enum）修改于 2026-08-26 17:05
- **解决**：gem5 重编译完成（0101 scons -j8），structuralFault 参数可用；结构故障 A/B/C 已跑通

### 问题 3：0103 24h 扫描 orchestrator stall（已停）
- **现象**：PID 392795 0% CPU，scan.log 空（tee 缓冲）
- **根因**：系统过载（gem5 编译 + 多板扫描同跑）
- **解决**：已 pkill 停止 stalled 扫描释放资源。0201 仍可达（sdc 用户，96 核）

### 问题 4：引用不可机器核实
- **现象**：WebFetch 全域名被封，WebSearch 返回冲突训练记忆
- **解决**：所有引用标 [CITE TBD: verify]，投稿前人工核验原文

---

## 四、待做事项（按优先级，TDD 8 任务）

### 🔴 高优先级（best paper 关键证据）

- [ ] **T1: 进化引擎单元测试**（适应度函数、三算子、接受准则）
- [ ] **T2: 长序列进化稳定性**（>50 代，验证不退化、不陷入局部最优）
- [ ] **T3: 业务画像 trace 演化**（真实指令序列，非合成 ADDS）
- [ ] **T4: 语料 D 生成**（进化引擎输出 → snap 语料，可被 runner 重放）
- [ ] **T5: D 打包入 A/B/C 对比框架**（与现有 sweep 脚本对齐）
- [ ] **T6: 🔑 A/B/C/D 四组对比（关键证据，预注册）** — **D 是否在 bit-flip + 结构度量上都击败 B？预注册 D≥2×B 为显著。** **当前未完成，绝不谎称 D>B**
- [ ] **T7: Paper 2 主线重写**（基于 T6 结果；若 D>B → best-paper 正面叙事；若 D≤B → 诚实 negative 方法论，DSN 级）
- [ ] **T8: 更新 docs/kunpeng920_sdc_research_report.md §7**

### 🟢 低优先级（待外部条件）

- [ ] EDA Gate-level 覆盖率耦合（鲲鹏商用 RTL 不开源）
- [ ] 老化烤机箱测试（需 85°C 物理设备）
- [ ] Vmin 电压裕量扫描（sdc 无 sudo + 服务器锁频）
- [ ] 微架构脆弱性测绘/业务画像/学术发表（长期调研）

---

## 五、诚实红线（不可违背）

1. **严格区分真 SDC（outcome 2/3/4）与 runaway(5)/misbehave(6) 噪声**——0201 满负载 2634 个 runaway 不是 SDC
2. **严格区分干净 diverge（SUM/CRC≠golden）与 gem5 异常退出**——结构故障 A/B/C/D 须按此分类
3. **未测出 D>B 绝不谎称"击败 SiliFuzz"**——A/B/C 两度量已诚实标失败，D 度量 pending；预注册 D≥2×B
4. **引用不可机器核实就标 [CITE TBD: verify]**，绝不伪造页码/卷号/作者列表
5. **gem5 O3 ≠ TSV110 RTL**（Paper 1 §7 已声明），所有 gem5 diverge 率是模型级非硅片级
6. **不谎称复现核心 179**（Paper 1 警告满载触发 watchdog 复位，禁止复现）

---

## 六、关键文件索引

- **Paper 2 正文**：`docs/paper/paper2_silifuzz_detection_deployment.md`（222 行，8 节，待 T7 重写）
- **进化引擎**：`tools/sdc_mutator/evolution_engine.py`（231 行，三算子 + 适应度）
- **进化引擎 8 任务 TDD 计划**：`docs/superpowers/plans/2026-08-27-sdc-evolutionary-engine-paper.md`（580 行）
- **CSP 生成器（已证伪，保留作对照）**：`tools/sdc_mutator/csp_targeted_generator.py`
- **C 工作负载**：`seeds/gem5/sdc_probe_workload_csp.c`
- **结构故障 sweep**：`scripts/gem5_sweep_structural_abc.py`
- **CHAOSLSQFwd patch**：`scripts/patch_gem5fi_lsq_fwd.py`
- **A/B/C bit-flip 数据**：0101 `/root/gem5-fi/smoke_test/{sdc_sweep_runs,ab_random_runs,ab_csp_runs}/`
- **研究报告**：`docs/kunpeng920_sdc_research_report.md`
- **Paper 1（ground truth）**：0101 `/home/sdc/wangxu/gem5-fi/docs/cases/core179-microarch-rootcause-synthesis/PAPER.md`

---

## 七、进展时间线

- 2026/08/27 ~17:00 — CSP 生成器原型（commit a144d82）
- 2026/08/27 ~17:30 — 多类型 CSP + C 工作负载 + 语料 C（commit 5cbe5d6）
- 2026/08/27 ~18:00 — A/B/C bit-flip 完成，**证伪**（C=3.7%<B=8.0%）
- 2026/08/27 ~18:30 — CHAOSLSQFwd patch + 结构 sweep 脚本（commit 79e5451, 6ec4174）
- 2026/08/27 ~18:40 — gem5 重编译启动（PID 5565），pty 耗尽阻塞 SSH
- 2026/08/27 ~19:30 — Paper 2 更新最终 A/B/C bit-flip 数字（commit 37e4b4b）
- 2026/08/27 — 结构故障 A/B/C 全量500次完成，**两度量都统计显著 C<B**（commit 3e69aa8）
- 2026/08/28 — gem5 重编译完成，structuralFault 参数可用
- 2026/08/28 — **进化引擎原型**：ADDS+普通操作数 T 8→70（8.8×），E=0.999（commit 81dd1f7）
- 2026/08/28 — **三算子完整 pipeline**：toggle 爬山 + 边界放大 + 上下文交叉（commit 909b21b）
- 2026/08/28 — **Paper 2 进化引擎 8 任务 TDD 计划**（commit 1973db7）；0103 Python unicorn+capstone 安装
- **当前**：T1-T8 TDD 计划已立，T6 A/B/C/D 对比是关键证据，**未完成**。下一步：T1 单测 → T2 长序列稳定性

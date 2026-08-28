# Paper 2 Best-Paper 攻坚计划与进展

> 本文档是 Paper 2（silifuzz 检测/部署方法论）冲击顶会顶刊 best paper 的全局计划、进展记录与待做事项。严格遵循诚实红线：所有结果基于真实命令输出，不谎称未完成的工作。
>
> 分支：`feat/sdc-detection-cases-kunpeng920`。Paper 1（gem5-fi 核心十七取证+结构故障注入，ASPLOS/MICRO/HPCA 目标）是独立论文，Paper 2 引其为 ground truth，零重叠。

---

## 一、目标

**核心目标**：Paper 2 达成 best-paper 级。A/B 实验证伪了朴素 operand 字典（全0/全1/交替/subnormal/NaN）在 bit-flip 注入下劣于随机（逻辑掩蔽）。攻坚方向：构建**数学指导的定向压力变异器**（CSP + Unicorn 覆盖率引导），站在 SiliFuzz/Unicorn 覆盖率导向模糊测试巨人肩上，在**两度量**上都击败 SiliFuzz 随机变异：
1. bit-flip diverge 率（已证伪朴素字典，CSP 配对待结构度量后定）
2. 结构故障（byte_lane_skew）diverge 率（CSP 定向的第二机会）

**用户执行指令**："必须完成所有工作。每步骤都踏实的做，保留全局目标、计划、安排，保存所有阶段性成果和进展，拆分成多个微小步骤稳步推进。永远符合事实，逻辑严密清晰。" → 多 session、微小步骤、保存进展、严格事实。

---

## 二、已完成（实证，截至 2026/08/27 19:30）

| # | 微小步骤 | 实证结果 | Commit |
|---|---------|---------|--------|
| 1 | CSP 定向配对生成器原型 | carry_chain 11 变体，cc64_full_nonzero end-state x0=0xFFFFFFFFFFFFFFFE（非零减掩蔽验证） | a144d82 |
| 2 | 多类型 CSP 生成器（carry/mul/toggle 配对） | 23 变体（e1:10+e2:7+e3:6），全 make+replay OK；e2 mul_max_max x0=0xFFFFFFFE00000001（0xFFFFFFFF² 精确） | 5cbe5d6 |
| 3 | C 工作负载（CSP 配对）+ 语料 C | golden SUM=1626623080976798388 CRC=79113488 numCycles=63343；语料 C 43 snapshot 221KB replay code:1 | 5cbe5d6 |
| 4 | **A/B/C bit-flip 最终对比** | A(朴素字典)=3.9%(18/458), B(随机)=8.0%(40/500), C(CSP配对)=3.7%(14/380); A/B=0.49×, C/B=0.46×, p≈0.0083 z=-2.64 **统计显著证伪** | 37e4b4b |
| 5 | 跨仓 patch 接 CHAOSLSQFwd | `scripts/patch_gem5fi_lsq_fwd.py` 给 two_level_taishan.py 加 add_chaos_lsq_fwd + --injector lsq_fwd + --structural-fault；基础实例化成功 numFaultsInjected=1 | 79e5451 |
| 6 | 结构故障 A/B/C sweep 脚本 | `scripts/gem5_sweep_structural_abc.py`（byte_lane_skew 注入 A/B/C 三组） | 6ec4174 |
| 7 | Paper 2 更新最终 A/B/C 数字 | 旧 4.3/9.6/0.45 → 最终 3.9/8.0/3.7/0.49/0.46；§5.2.1 结构 pending | 37e4b4b |
| 8 | **结构故障 A/B/C 50次探路** | A=0.0%(0/50), B=4.0%(2/50), C=2.0%(1/50); C/B=0.5× (与bit-flip一致, C未击败B) | (待提交) |

**A/B/C bit-flip 诚实结论**：CSP 定向配对在 bit-flip 注入度量下**未击败随机**（C=3.7% < B=8.0%），与朴素字典一样被逻辑掩蔽。减掩蔽假设（配对非零结果）未被验证——结构化操作数产生确定性结果，bit-flip 易被掩蔽；随机操作数无结构冗余更易 observable。

---

## 三、出现的问题（诚实诊断）

### 问题 1：bit-flip 度量 CSP 定向未击败随机（已诊断）
- **现象**：C=3.7% < B=8.0%（C/B=0.46×），与 A=3.9%（A/B=0.49×）持平
- **根因**：逻辑掩蔽效应稳健。operand-dict 极端值（0xFFFF+1→0, 0x5555^0xAAAA→全1）产生确定性结构化结果，bit-flip 命中后被逻辑/CRC 掩蔽；随机操作数无结构冗余，bit-flip 更易产生 observable diverge
- **解决方向**：bit-flip 是错误度量。转向**结构故障度量**（byte_lane_skew）——CSP 定向操作数激活 load-data-return 路径，结构故障打 forwarding datapath 可能 C>B

### 问题 2：CHAOSLSQFwd structuralFault 参数需 gem5 重编译
- **现象**：`Invalid assignment for parameter structuralFault`
- **根因**：gem5.opt 编于 2026-08-25 11:44，CHAOSLSQFwd.hh（含 structuralFault enum）修改于 2026-08-26 17:05——gem5.opt 早于参数加入
- **解决**：gem5 重编译在 0101 后台跑（scons -j8，PID 5565，~2h+）。编译占用全部 pty 致 SSH 查询持续 PTY_EXHAUSTED（40min+ 9 次检查全失败）。停止 0103 stalled 24h 扫描后 SSH 恢复，确认编译仍 COMPILING

### 问题 3：0103 24h 扫描 orchestrator stall
- **现象**：PID 392795 运行 10:14，orchestrator 0% CPU，scan.log 空（tee 缓冲）
- **根因**：系统过载（gem5 编译 + 4 板扫描 + 24h 扫描同跑）
- **解决**：已 pkill 停止 stalled 0103 扫描释放资源

### 问题 4：引用不可机器核实
- **现象**：WebFetch 全域名被封，WebSearch 返回冲突训练记忆（SiliFuzz: Genc 2022 vs Mousavi/Kasikci 2023）
- **解决**：所有引用标 [CITE TBD: verify]，投稿前人工核验原文

---

## 四、待做事项（按优先级）

### 🔴 高优先级（best paper 关键证据）

- [ ] **T1: 等 gem5 重编译完成**（0101，scons -j8，~2h+，pty 释放后可查）。编译完成是结构故障 A/B/C 的前置条件
- [~] **T2: 结构故障 A/B/C** — 50次探路: A=0%, B=4%, C=2% (C/B=0.5×, 未击败)。**全量500次确认中**(0101后台3组并行)。趋势: 与bit-flip一致C<B
- [ ] **T3: 根据 T2 结果定 Paper 2 主线**
  - 若 C>B（结构度量击败）：主线 = "CSP 定向在结构故障度量击败随机（bit-flip 度量失败但结构度量成功，证明定向压力的正确度量是结构故障而非 bit-flip）" → best paper 候选
  - 若 C≤B（结构也失败）：主线 = 诚实 negative result "operand-targeting 在两度量都未击败随机；逻辑掩蔽效应在模型级稳健" → DSN 级诚实方法论，不冲 best paper 但最诚实

### 🟡 中优先级（论文完善）

- [ ] **T4: 重写 Paper 2 主线**（根据 T2/T3 结果）。当前主线是旧"operand-targeting improves"（已证伪），需重构
- [ ] **T5: 掩蔽形式模型**（自建，不依赖外部引用）。定义 operand-determinism → result-redundancy → masking-probability，推导 A/B/C 期望比率，与实测 0.49×/0.46× 对比
- [ ] **T6: 引用核实**（WebFetch 被封，用 WebSearch 摘要 + 训练知识作 leads，标 [CITE TBD: verify]，投稿前人工核验）
- [ ] **T7: 24h 真机扫描重启 + 最终数据**（0103 stalled 已停；清理残留 orchestrator 后重启，或等 gem5 编译完后重启避免过载）
- [ ] **T8: 更新 docs/kunpeng920_sdc_research_report.md §7**（三档分类：已完成/进行中/待外部条件）

### 🟢 低优先级（待外部条件，如实记录）

- [ ] **T9: EDA Gate-level 覆盖率耦合**（鲲鹏商用 RTL 不开源，不可得）
- [ ] **T10: 老化烤机箱测试**（需 85°C 物理设备，无）
- [ ] **T11: Vmin 电压裕量扫描**（DVFS 接口存在但 sdc 无 sudo + 服务器锁频）
- [ ] **T12: 微架构脆弱性测绘/业务画像/学术发表**（长期调研）

---

## 五、诚实红线（不可违背）

1. **严格区分真 SDC（outcome 2/3/4）与 runaway(5)/misbehave(6) 噪声**——0201 满负载 2634 个 runaway 不是 SDC
2. **严格区分干净 diverge（SUM/CRC≠golden）与 gem5 异常退出**——结构故障 A/B/C 须按此分类
3. **未测出 C>B 绝不谎称"击败 SiliFuzz"**——bit-flip 度量已诚实标失败，结构度量 pending
4. **引用不可机器核实就标 [CITE TBD: verify]**，绝不伪造页码/卷号/作者列表
5. **gem5 O3 ≠ TSV110 RTL**（Paper 1 §7 已声明），所有 gem5 diverge 率是模型级非硅片级
6. **不谎称复现核心 179**（Paper 1 警告满载触发 watchdog 复位，禁止复现）

---

## 六、关键文件索引

- **Paper 2 正文**：`docs/paper/paper2_silifuzz_detection_deployment.md`（222 行，8 节）
- **CSP 生成器**：`tools/sdc_mutator/csp_targeted_generator.py`
- **C 工作负载**：`seeds/gem5/sdc_probe_workload_csp.c`
- **结构故障 sweep**：`scripts/gem5_sweep_structural_abc.py`
- **CHAOSLSQFwd patch**：`scripts/patch_gem5fi_lsq_fwd.py`
- **A/B/C bit-flip 数据**：0101 `/root/gem5-fi/smoke_test/{sdc_sweep_runs,ab_random_runs,ab_csp_runs}/`
- **研究报告**：`docs/kunpeng920_sdc_research_report.md`
- **Paper 1（ground truth）**：0101 `/home/sdc/wangxu/gem5-fi/docs/cases/core179-microarch-rootcause-synthesis/PAPER.md`

---

## 七、进展时间线

- 2026/08/27 ~17:00 — micro-step 1: CSP 生成器原型（commit a144d82）
- 2026/08/27 ~17:30 — micro-step 2-3: 多类型 CSP + C 工作负载 + 语料 C（commit 5cbe5d6）
- 2026/08/27 ~18:00 — A/B/C bit-flip 完成，**证伪**（C=3.7%<B=8.0%）
- 2026/08/27 ~18:30 — micro-step 4-5: CHAOSLSQFwd patch + 结构 sweep 脚本（commit 79e5451, 6ec4174）
- 2026/08/27 ~18:40 — gem5 重编译启动（PID 5565），pty 耗尽阻塞 SSH
- 2026/08/27 ~19:30 — Paper 2 更新最终 A/B/C 数字（commit 37e4b4b）；停止 0103 stalled 扫描，SSH 恢复，编译仍 COMPILING
- **当前**：等 gem5 编译完成 → 跑结构故障 A/B/C（T2）→ 定主线（T3）

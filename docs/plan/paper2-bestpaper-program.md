# Paper 2 Best-Paper 攻坚计划与进展

> 本文档是 Paper 2（silifuzz 检测/部署方法论）冲击顶会顶刊 best paper 的全局计划、进展记录与待做事项。严格遵循诚实红线：所有结果基于真实命令输出，不谎称未完成的工作。
>
> 分支：`feat/sdc-detection-cases-kunpeng920`。Paper 1（gem5-fi 核心十七取证+结构故障注入，ASPLOS/MICRO/HPCA 目标）是独立论文，Paper 2 引其为 ground truth，零重叠。

---

## 一、目标

**核心目标**：Paper 2 达成 best-paper 级。**关键 pivot（2026/08/27）**：A/B/C 两度量统计显著证伪了静态操作数字典（朴素/CSP 配对）后，转向**自适应进化引擎**——抛弃写死魔术数字，用遗传算法+梯度爬山的动态变异，三因子适应度函数（T(di/dt) 翻转量 + M(Path) 微架构深度 + E(AntiMasking) 反掩蔽高熵+雪崩），三个变异算子（toggle 梯度爬山、边界差异放大、上下文重组），从普通指令自动演化出高 SDC 激发概率操作数，在 bit-flip + 结构故障两度量上击败 SiliFuzz 随机变异。

**用户执行指令**："必须完成所有工作。每步骤都踏实的做，保留全局目标、计划、安排，保存所有阶段性成果和进展，拆分成多个微小步骤稳步推进。永远符合事实，逻辑严密清晰。" → 多 session、微小步骤、保存进展、严格事实。

---

## 二、已完成（实证，截至 2026/08/28）

### 阶段一：静态字典（已证伪，但奠定基础）

| # | 项 | 实证结果 | Commit |
|---|---|---------|--------|
| 1 | 19 个微架构压力模板 | MMU/L2C/LSU/OoO/IEX/FSU/IFU 全覆盖，全 make+replay OK | 多 |
| 2 | 操作数字典 + CSP 生成器 | carry/mul/toggle 三类，23 变体，全 make+replay OK | 5cbe5d6 |
| 3 | gem5-fi 500 次注入 | A(朴素字典)=3.9%(18/458)，最敏感寄存器 integer[9] | 多 |
| 4 | gem5 重编译 + CHAOSLSQFwd | structuralFault 参数生效，numStructuralByteLaneSkew=1 验证 | 79e5451 |
| 5 | **A/B/C bit-flip 全量 500 次** | A=3.9%, B=8.0%, C=3.7%, C/B=0.46×, p=0.0083 **统计显著证伪** | 3e69aa8 |
| 6 | **A/B/C 结构故障全量 500 次** | A=2.0%, B=8.4%, C=2.8%, C/B=0.33×, p=0.0001 **统计显著证伪** | 3e69aa8 |

**阶段一诚实结论**：静态操作数字典（朴素/CSP 配对）在 bit-flip + 结构故障两度量都统计显著地劣于随机（逻辑掩蔽效应在模型级稳健）。

### 阶段二：自适应进化引擎（当前进展）

| # | 项 | 实证结果 | Commit |
|---|---|---------|--------|
| 7 | 进化引擎原型 | `tools/sdc_mutator/evolution_engine.py`：适应度 Score=W1·T+W2·M+W3·E，三算子。从 ADDS X0,X1,X2+普通操作数，**T 8→70（8.8× 提升）**，演化操作数无规律但翻转量最大，E=0.999 高熵反掩蔽 | 81dd1f7 |
| 8 | 三算子完整 pipeline | 算子一爬山 T 8→20，算子二边界放大找到 11 突变点，算子三上下文重组 T 20→70。翻转量 8.8× 提升 | 909b21b |
| 9 | Python unicorn+capstone | 0103 阿里云镜像安装，进化引擎用 Python unicorn 直接执行（不依赖 silifuzz C++ proxy） | 81dd1f7 |
| 10 | 实现计划 | `docs/superpowers/plans/2026-08-27-sdc-evolutionary-engine-paper.md`（580 行，8 任务 TDD） | 1973db7 |

**阶段二诚实结论**：进化引擎原型验证了"从普通指令自动演化高压操作数"的核心机制（T 8.8× 提升，不依赖魔术数字）。**但高压≠高 SDC 激发率**——A/B/C/D 对比未做，不谎称击败 SiliFuzz。

---

## 三、出现的问题（诚实诊断）

### 问题 1：静态字典两度量证伪（已诊断，催生进化引擎）
- **现象**：bit-flip C/B=0.46×, 结构 C/B=0.33×，统计显著 C<B
- **根因**：逻辑掩蔽——静态字典极端值产生确定性结果（0xFFFF+1=0），bit-flip/byte_lane_skew 命中被掩蔽；随机无结构冗余更易 observable
- **解决**：转向自适应进化引擎（梯度爬山+反掩蔽高熵约束+雪崩测试）

### 问题 2：进化引擎单条指令雪崩有限（已诊断）
- **现象**：单条 ADDS 的 1bit 扰动只产生 1bit 输出差异（低雪崩）
- **解决**：实现计划 Task 2——长指令序列进化支持（多指令混合序列）

### 问题 3：gem5 编译 pty 耗尽（已解决）
- **现象**：scons -j8 占满 0101 pty，SSH 查询持续失败
- **解决**：停止 0103 stalled 24h 扫描释放 pty；编译完成后 SSH 恢复

### 问题 4：引用不可机器核实（已定位）
- **现象**：WebFetch 全域名被封，WebSearch 返回冲突训练记忆
- **解决**：所有引用标 [CITE TBD: verify]，投稿前人工核验

---

## 四、待做事项（按优先级，详见实现计划 8 任务）

### 🔴 高优先级（best paper 关键证据）

- [ ] **T1: 进化引擎单元测试**（TDD 基础：适应度函数/三算子/雪崩验证）
- [ ] **T2: 长指令序列进化支持**（count 自适应，多指令混合序列，解决雪崩有限）
- [ ] **T3: 业务指令序列采集**（算子三 crossover 源，从 silifuzz corpus 提取真实指令序列）
- [ ] **T4: 进化语料生成器**（批量生成高压操作数 .bin 语料 D）
- [ ] **T5: 语料 D 转 Snapshot + 打包**（snap_tool make → generate_corpus → SnapCorp）
- [ ] **T6: A/B/C/D 四组对比**（**核心证据**：D 是否击败 B，bit-flip + 结构两度量，预注册 D≥2×B=显著）
- [ ] **T7: Paper 2 重写**（主线根据 D 是否击败 B 定：击败→best paper 候选；未击败→诚实 negative result）
- [ ] **T8: 研究报告 + 计划文档更新**

### 🟡 中优先级（论文完善）

- [ ] **T9: 掩蔽形式模型**（自建，定义 operand-determinism→result-reduction→masking-probability）
- [ ] **T10: 引用核实**（WebFetch 被封，标 [CITE TBD: verify]，投稿前人工核验）
- [ ] **T11: 24h 真机扫描重启**（stalled 已停，清理后重启避免过载）

### 🟢 低优先级（待外部条件）

- [ ] **T12: EDA Gate-level 覆盖率耦合**（鲲鹏商用 RTL 不开源）
- [ ] **T13: 老化烤机箱测试**（需 85°C 物理设备）
- [ ] **T14: Vmin 电压裕量扫描**（DVFS 接口存在但无 sudo + 服务器锁频）
- [ ] **T15: 微架构脆弱性测绘/业务画像/学术发表**（长期调研）

---

## 五、诚实红线（不可违背）

1. **严格区分真 SDC（outcome 2/3/4）与 runaway(5)/misbehave(6) 噪声**
2. **严格区分干净 diverge（SUM/CRC≠golden）与 gem5 异常退出**
3. **未测出 D>B 绝不谎称"击败 SiliFuzz"**——静态字典两度量已证伪，进化引擎 A/B/C/D 待做
4. **引用不可机器核实就标 [CITE TBD: verify]**，绝不伪造页码/卷号/作者列表
5. **gem5 O3 ≠ TSV110 RTL**，所有 gem5 diverge 率是模型级非硅片级
6. **不谎称复现核心 179**（Paper 1 警告满载触发 watchdog 复位）

---

## 六、关键文件索引

- **Paper 2 正文**：`docs/paper/paper2_silifuzz_detection_deployment.md`（222 行，8 节）
- **进化引擎**：`tools/sdc_mutator/evolution_engine.py`（适应度函数+三算子+pipeline）
- **CSP 生成器（已证伪）**：`tools/sdc_mutator/csp_targeted_generator.py`
- **实现计划**：`docs/superpowers/plans/2026-08-27-sdc-evolutionary-engine-paper.md`（580 行，8 任务）
- **研究报告**：`docs/kunpeng920_sdc_research_report.md`
- **设计概念**：`docs/plan/kunpeng920_sdc_design_concept.md`（§3.3 进化引擎范式）
- **主方案**：`docs/plan/kunpeng920_sdc_plan.md`（1281 行，附录 A-E）
- **A/B/C 数据**：0101 `/root/gem5-fi/smoke_test/{sdc_sweep_runs,ab_random_runs,ab_csp_runs,struct_*_runs}/`
- **Paper 1（ground truth）**：0101 `/home/sdc/wangxu/gem5-fi/docs/cases/core179-microarch-rootcause-synthesis/PAPER.md`

---

## 七、进展时间线

- 2026/08/25-26 — 阶段一：19 模板 + 操作数字典 + CSP 生成器 + 分布式集群 + Paper 2 初稿
- 2026/08/27 ~17:00 — A/B/C bit-flip 全量 500 次完成，**统计显著证伪**（C/B=0.46×, p=0.0083）
- 2026/08/27 ~18:00 — gem5 重编译 + CHAOSLSQFwd 结构注入启用
- 2026/08/27 ~19:00 — A/B/C 结构故障全量 500 次完成，**两度量都证伪**（C/B=0.33×, p=0.0001）
- 2026/08/27 ~21:00 — **pivot 到自适应进化引擎**：原型 + 三算子完整 pipeline，T 8→70（8.8×）
- 2026/08/28 — 实现计划（8 任务 TDD）+ 全 docs 同步更新
- **当前**：执行实现计划 Task 1-8，核心是 Task 6 A/B/C/D 对比验证进化引擎是否击败随机

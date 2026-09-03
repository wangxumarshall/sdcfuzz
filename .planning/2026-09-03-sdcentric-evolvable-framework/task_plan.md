# Task Plan: sdcfuzz 可演进框架（AutoµSens + 操作数/RL 变异 + ACE/IBR/McPAT 评估 + CHAOS 检出率闭环）

## Goal
按 scheme.md §4.3/§5 思路，在本仓库现有工具链（tools/sdc_mutator + tools/sdc_experiment + gem5_config）之上，构建一个**可演进的 SDC 用例生成-评估-验证框架**：种子指令序列 → 指令/操作数变异 → 静态评估(ACE/IBR) + gem5 执行 + McPAT 功耗 → 筛选高功耗/高覆盖序列 → gem5+CHAOS 故障注入测检出率 → 结果回灌迭代。框架分层解耦、可增量演进（先启发式后 RL），不推倒现有代码。

## Next Step
Phase 5 收尾: 向用户交付最终汇报 (已完成 — 见下方 Phase 5 勾选)。

## Current Phase
All complete (Phase 1-5)

## Phases

### Phase 1: 源码深度理解与架构审视（研究，不改代码）
- [x] 深读 tools/sdc_mutator/ 全部引擎（evolution_engine / ace_fraction / ace_workload / operand_mutator / csp_targeted_generator / gem5_ace_hillclimb）
- [x] 深读 tools/sdc_experiment/（gem5_env / sim_sweep / experiment_config / devices）
- [x] 深读 gem5_config/configs/two_level_taishan.py（CHAOS 注入器全参数）
- [x] 审视架构演进违背点 → 重构清单 R1-R6（findings.md F3）
- [x] 调研 AutoµSens/RL 反屏蔽/功耗-SDC 落地方案（findings.md F4：演进路径映射）
- [x] 确认外部依赖：gem5-fi ✅本机、McPAT ❌未装（降级路径已定）、unicorn ✅
- [x] **Status:** complete

### Phase 2: 框架设计（可演进架构蓝图）
- [x] 定义框架分层：Gen → Assess → Filter → Validate → Feedback（plan 文档定稿）
- [x] 定义核心数据结构（Candidate + Vault JSONL 血缘）
- [x] 定义插件接口：Evaluator/Mutator/Filter/policy 均可替换（RL 接入口=Gym 语义 policy.choose_mutators）
- [x] R1-R6 重构边界逐项映射到 Task 1-6
- [x] 设计+实施 plan 已写：docs/superpowers/plans/2026-09-03-sdc-pipeline-framework.md（Task 1-9, one-patch-per-unit）
- [x] 用户决策：先轻后重（Unicorn 闭环先行，gem5 第二阶段）；功耗 Unicorn 代理+McPAT 插件化（**McPAT 后台安装中**，V110 配置依据 kunpeng.md）
- [x] **Status:** complete

### Phase 3: 实施（one-patch-per-unit，逐 commit）
- [ ] 3.1 Vault 数据结构 + 血缘记录（SQLite/JSONL，候选序列指标持久化）
- [ ] 3.2 种子层：现有 20 模板 + D13 接入统一种子接口
- [ ] 3.3 变异层整合：指令序列变异 + 操作数变异统一接口（复用 operand_mutator/evolution_engine 算子）
- [ ] 3.4 静态评估器：ACE/IBR 静态程序分析（Unicorn trace 基础上）
- [x] 3.5 gem5 执行评估器 (Task 6/7 完成); McPAT 评估器 = Task 8 (blocked, 后台安装中)
- [x] 3.6 筛选器 (Task 5)
- [x] 3.7 CHAOS 检出率验证器 (Task 6)
- [x] 3.8 闭环编排器 (Task 5/7)
- [x] 每步: build/测试通过 + commit + push（9 commits 已推 origin/feat/sdc-pipeline-framework）
- [ ] **Status:** pending

### Phase 4: 端到端验证
- [x] M1 轻量闭环 (Task 5): e1 种子 ace 0.70→0.80, 血缘深 3
- [x] M2 重层闭环 (Task 7): gem5 golden+CHAOS bit/struct 全链路
- [x] 单元测试: 82-86 项全绿 (sdc_pipeline+sdc_mutator+sdc_experiment)
- [x] E7 对照 (ecfce90): EVOLVE 4/60 vs RANDOM 3/60, OR=1.357 p=1
      → TIE/INSUFFICIENT (诚实阴性; 修复 CHAOS 注入单位/E7 终代选择两 bug)
- [x] **Status:** complete

### Phase 5: 交付与文档
- [x] README (04b4e0f): 架构图+演进路线+已知边界
- [x] scheme.md 4 处修订 (04b4e0f)
- [x] 最终汇报 (本会话)
- [x] **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 不推倒现有工具链，改造接入 | 现有 evolution_engine/ace_* 已实证可用（见 2026-09-03 合规评估），推倒违背演进原则 |
| 框架放 tools/sdc_pipeline/（新目录） | 与 sdc_mutator(变异)/sdc_experiment(实验) 分工清晰，避免污染 |
| 先启发式后 RL | RL 需要稳定的环境/奖励接口，先用现有三因子适应度占位，接口留换 RL |
| McPAT 若不可用则接口+降级 | 本机 McPAT 可用性未证实，不能假设（诚实原则） |

## Errors Encountered
| Error | Resolution |
|-------|------------|

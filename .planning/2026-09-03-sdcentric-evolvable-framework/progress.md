# Progress Log

## Session: 2026-09-03

### Current Status
- **Phase:** 1 - 源码深度理解与架构审视
- **Started:** 2026-09-03

### Actions Taken
- 任务发起：按 scheme.md 思路构建可演进 SDC 用例生成框架（AutoµSens/操作数变异/RL反屏蔽/功耗-SDC/ACE-IBR/CHAOS检出率闭环）
- 前置成果（本日早前会话完成的合规评估）：docs/experiments/2026-09-03-scheme-compliance-assessment.md
  - L1 基座✅/创新0%、L2 ~45%、L3 ~85%、L4 ~50%；三大创新点(AutoµSens/RL/功耗)实现度 0%
  - scheme.md 4 处过时陈述已识别（19→20模板、FlipRandomBit低估、多bit已有、4板实为3板）
- 初始化 .planning/2026-09-03-sdcentric-evolvable-framework/ 计划
- **Phase 3 进展 (Task 1-5 完成, M1 达成)**:
  - Task 1 Candidate 统一抽象 (81c234c) — .S/bytes 双形态+内容hash+血缘
  - Task 2 Vault JSONL 持久层 (b5f2921) — 幂等存储+lineage 回溯
  - Task 3 Unicorn 评估器池 (00d1a96) — ACE代理/IBR/功耗代理/雪崩
  - Task 4 变异器池 (6f2fbe6) — 位翻/字典/指令序列/功耗应力Type-I-II
  - Task 5 筛选器+闭环编排 (9fa0afb) — **M1: 轻量闭环全通, e1种子ace 0.70→0.80, 血缘深3**
  - 71 项测试全绿 (sdc_pipeline+sdc_mutator+sdc_experiment)
- **Phase 3 进展 (Task 6-7 完成, M2 达成)**:
  - Task 6 gem5_runner (69a7697): golden 自动注册(--mode baseline)+CHAOS bit/struct 注入+Wilson CI
    - 3 轮 SIGSEGV 调试全记录: rodata跳转/x9x10被覆盖/stp越帧(gdb定位PC=0x18,x19未恢复)
  - Task 7 重层闭环 (98a16e4): Pipeline validate_top_k + M2 端到端实证
    - **x2 污染关键修复**: 装载循环 temp 覆盖 x2 → gdb 实证 → 修复后 A/B SUM差8
    - 发现: dict 变异 x5 被 adds 覆写 = 逻辑掩蔽活教材 (读集分析列入后续)
    - M2 报告: output/experiments/sdc_pipeline_m2/e2e_report.md
  - **McPAT 后台 agent 仍在安装中**
- **Task 9 完成 (04b4e0f)**: README + scheme.md 4 处修订 + 能力清单状态注记; 分支已推送 origin/feat/sdc-pipeline-framework (8 commits)
- **Phase 4 complete (E7, ecfce90)**: EVOLVE 4/60 vs RANDOM 3/60 (OR=1.357, p=1, TIE)
  - 修复 3 个真实 bug: g_out 覆盖稀释/CHAOS first-clock 单位=CPU cycles (tick/385)/E7 终代选择
  - McPAT Task 8 完成 (9b5f20b): peak 功耗主指标, duty cycle 驱动 peak 非 runtime
- **Goal 补完 (700c8b6)**: RL bandit 实装 + E8 功耗-SDC 因果首检
  - EpsilonGreedyBanditPolicy (ε-greedy, Q 增量更新, Pipeline 零改动)
  - 10 种子对比: hill 5/bandit 3/tie 2 (bandit 1/3 预算打平, 诚实记录)
  - E8: A 0% < B Type-I 6.7% < C Type-II 13.3% 单调 (H2 方向一致),
    统计 INSUFFICIENT; McPAT duty 无组间区分度等三个诚实观察
- **论文 v2/v2.1 (dfa8806)**: docs/paper/v2/paper_v2_en.md
  - 全部成果囊括: D13核心 (3.00×/7.79×) + falsification 路径 + 五阶段框架
    + 读集分析 + bandit + McPAT/E8v2 + 舰队部署
  - 5维模拟评审 (Reject→整改路径): 3 大攻击点 (样本量自己算出不跑/
    E8混杂/新颖性空心化) → 13 项整改全落实
  - **E8v2 是关键新增实验**: 长度配平对照推翻 E8v1 自己的方向性信号
    (应力14% vs 等长NOP 12%, p=0.83) — 评审质疑被实验证实
  - 13 项数字 vs JSON 事实核对全过
- **Phase 2 complete**：设计定稿 + 实施 plan 落盘
  - 用户决策：先轻后重（Unicorn 闭环先行）；功耗 Unicorn 代理 + McPAT 插件化
  - **McPAT 安装 subagent 已后台启动**（装到 ~/wangxu/mcpat + tsv110.xml V110 配置，V110 参数取自 kunpeng.md：4-wide OoO/PRF/L1D 64KB 4-way/L2 512KB 10cyc/scheduler 33 entries）
  - 实施 plan：docs/superpowers/plans/2026-09-03-sdc-pipeline-framework.md（Task 1-9，one-patch-per-unit）
  - 框架目录 tools/sdc_pipeline/：candidate/vault/evaluators/mutators/filters/gem5_runner/mcpat_eval/pipeline



### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|

# Findings & Decisions

## Requirements（用户需求，逐条）
1. 深度理解项目源码；违背架构演进的需要重构
2. 研究 scheme.md 思路：AutoµSens、操作数变异、RL 反逻辑屏蔽变异、功耗应力与 SDC 因果关系
3. 实现指令序列种子；基于种子变异指令序列和操作数
4. 对新指令序列做：ACE/IBR 静态程序分析评估 + gem5 仿真执行 + mcpat 功耗计算
5. 筛选高功耗/高覆盖指令序列
6. gem5+CHAOS 故障注入验证检出率
7. 整个方案做成**可演进的框架**

## Research Findings

### F1 现有工具链实测接口（Phase 1 深读，2026-09-03）

**tools/sdc_mutator/（变异/进化层，全部基于 Unicorn 2.1.4 + capstone 5.0.7，本机可用）**：
- `evolution_engine.py`（245行）：`EvolutionEngine(code_bytes)` 类。核心方法 `run_once(regs)`→(final_regs, T, M, E, score)；`avalanche_test(regs, reg, bit)`→雪崩差异数；三算子 `toggle_hill_climb`（T+雪崩双约束爬山）、`boundary_amplify`（±1/位移突变点+精英池）、`context_crossover`（高功耗序列前置拼接）。**局限：写死 X0-X4 五寄存器、写死 64 条指令上限、只支持单条/短序列硬编码 hex**。
- `ace_fraction_engine.py`：`ACEFractionEngine(EvolutionEngine)`，`measure_ace_fraction(regs, n_probe)`=输入操作数 bit 翻转→输出 diverge 比例（Unicorn 级）。
- `ace_workload_engine.py`：`ACEWorkloadEngine`，`run_with_midflip(regs, flip_insn, flip_reg, flip_bit)` = 执行中翻转寄存器 bit（**直接模拟 gem5 注入语义**，比操作数级更准）。
- `operand_mutator.py`：模板 .S 文件 `// MUT: <slot>` 标记 + 字典（INT_DICT 10 种/FSU_DICT 6 种）笛卡尔积生成变体 .S。**与汇编模板体系（seeds/*.S → bin）打通**。
- `csp_targeted_generator.py`：CSP 定向操作数族（进位链全族），生成 .S 变体。
- `gem5_ace_hillclimb.py`：直接在 gem5 内测 ACE 爬山（依赖外部 gem5）。

**tools/sdc_experiment/（实验层）**：
- `gem5_env.py`：本机 gem5 定位 `~/wangxu/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt`（**已验证存在于 0103 本机**）+ `~/gem5-deps` 环境 + GROUPS 表（A/B/D13 二进制+golden+nc）。`check_env()` 自检。
- `sim_sweep.py`：`run_group(group, mode, n_runs, seed, cfg, jobs)` → diverge 率 + Wilson CI；`fisher_exact` 独立实现；mode=bit|struct（byte_lane_skew）；**MCE 红线 gem5 并行 ≤4**；fault-clock dispatch 前按 seed 抽完（可复现）。
- `experiment_config.py`：dataclass 配置，单事实来源。
- `devices/`：LocalDevice/RemoteDevice/DevicePool 抽象。
- `feedback.py`：真机结果提取→replay-confirm→reseed `seeds/evolved/`。
- `correlation.py`：Spearman+置换检验。

**gem5_config/configs/two_level_taishan.py（CHAOS 注入器，参数全量）**：
- `add_chaos`（CHAOSReg 架构寄存器）：first_clock/max_faults/probability/fault_type(bit_flip)/bits/reg_class(integer|float)/rng_seed/max_reg_idx(限制 X0-X30 防 zero-trap)
- `add_chaos_phys`（CHAOSPhysReg 物理寄存器）：injection_mode=phys|arch_frontend|arch_commit，target_phys_idx，fault_mask
- `add_chaos_lsq_fwd`（LSU 结构故障）：structural_fault=byte_lane_skew|all_zero，skew_bytes
- CLI: --binary --mode inject|golden --first-clock --max-faults --probability --rng-seed --injector reg|phys_reg|lsq_fwd --structural-fault

### F2 外部依赖可用性（2026-09-03 实测）
| 依赖 | 状态 |
|---|---|
| gem5-fi CHAOS (~/wangxu/gem5-fi) | ✅ 本机 0103 存在，gem5.opt 可用 |
| ~/gem5-deps | ✅ 存在（sim_sweep E1/E2 已跑通） |
| Unicorn 2.1.4 / capstone 5.0.7 | ✅ python3 可 import |
| McPAT | ❌ **本机未安装**（which mcpat / find 均无） |
| 交叉编译 aarch64 .S→bin | ✅ seeds/ 有 20 个已编译 .bin + build_seeds.sh |

### F3 架构演进违背点（重构清单）
| # | 违背点 | 证据 | 重构方向 |
|---|---|---|---|
| R1 | EvolutionEngine 写死 X0-X4/64条指令/硬编码hex，与模板 .S 体系（20模板+操作数字典）**两套体系互不相通** | evolution_engine.py:32 REG_MAP, :69 count=64 | 统一 Candidate 抽象：.S 文本或 bytes + 初始寄存器态，评估器通用化 |
| R2 | ACE 测量有三份平行实现（ace_fraction/ace_workload/gem5_ace_hillclimb），接口不一致 | 三个文件各自 measure_* | 统一 Evaluator 接口（evaluate(candidate)→metrics dict），三个实现变插件 |
| R3 | gem5_env.GROUPS 硬编码 A/B/D13，新候选序列无法进 gem5 验证（要 golden+nc 两个手工字段） | gem5_env.py:44-51 | Group 注册机制：新候选自动跑 golden 定基 → 注册 → 注入 |
| R4 | sim_sweep 只认 GROUPS 组名，检出率验证与生成/变异完全断链 | sim_sweep.py run_group(group=...) | Validate 阶段直接吃 Candidate 对象 |
| R5 | 无统一 Vault/血缘：evolution/ace 结果打印即丢，feedback 只存 seeds/evolved/*.bin | 全仓无 vault | Vault 雏形：候选+指标+血缘 JSONL/SQLite |
| R6 | 无 McPAT 集成，功耗只有 encode_high_power_alu() 硬编码经验序列 | evolution_engine.py:193 | Evaluator 接口留 mcpat 位置 + Unicorn 级翻转率功耗代理作降级 |

### F4 scheme.md 思路 → 可落地映射（关键研究结论）
- **AutoµSens（§5.1）**：完整版需 gem5 结构统计（执行端口/ROB/LSQ 占用），当前 gem5-fi 的 stats 可部分支撑；**演进路径**：第一版用「Unicorn 翻转量+指令类别→结构映射表」（19/20 模板已含结构标签）做结构靶向种子选择，第二版接 gem5 stats。不阻塞闭环。
- **操作数变异**：已有 operand_mutator（字典）+ csp_targeted_generator（进位链族）+ evolution_engine 爬山，缺的是统一接入框架。
- **RL 反逻辑屏蔽（§5.2）**：奖励函数三要素已可计算：SFI检测率(sim_sweep diverge率)、覆盖度(ACE/T/结构)、逻辑屏蔽惩罚(avalanche_test 已实现！evolution_engine.py:88)。**演进路径**：第一版用爬山/三因子（已有），接口按 Gym 风格（state/reward/action）设计，后续换 RL 不改框架。
- **功耗-SDC（§5.3）**：McPAT 本机未装。**演进路径**：第一版用 Unicorn 每指令寄存器翻转率作功耗代理（di/dt 代理，与 evolution_engine 的 T 同源），McPAT 作为 Evaluator 插件位（装好后即插即用）；Type-I/II/III 分类学生成器做成 Mutator 插件。
- **ACE/IBR 静态分析**：ACE 静态=Unicorn midflip（ace_workload_engine 已实现）；IBR（逻辑单元输入翻转率）= 逐指令输入 bit 翻转统计，Unicorn hook 可算（新 Evaluator，工作量小）。

### F5 端到端闭环数据流（框架核心设计，Phase 2 细化）
Seed(20模板+D13+evolved) → Mutator(指令变异/操作数变异/功耗应力注入) → Evaluator 池(Unicorn静态: ACE/IBR/T/E + 功耗代理; gem5: 执行+golden; McPAT: 可选) → Filter(多指标Pareto/加权) → Validator(gem5+CHAOS bit/struct 注入→diverge率+CI) → Vault(JSONL 持久+血缘) → Feedback(高分候选回灌种子池)

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 框架目录 tools/sdc_pipeline/ | 与 sdc_mutator(算子库)/sdc_experiment(实验驱动) 解耦，框架编排两者 |
| Vault 用 JSONL 追加式（非 SQLite） | 与现有实验 JSON 输出一致、可 git diff、无新依赖；血缘=parent_hash 链 |
| Candidate 统一抽象 = (.S 源 或 bytes, 初始寄存器, 结构标签, 血缘) | 打通 R1 两套体系；.S→bin 编译复用 build_seeds.sh 流程 |
| gem5 验证走「golden 先行注册」 | R3：任何候选先进 gem5 跑无注入 golden（定 SUM/CRC/nc），再进注入 sweep，全自动 |
| RL 接口按 Gym 语义（obs/reward/action）设计但第一版用爬山策略 | §5.2 演进要求：框架可演进=策略可替换，先有闭环再上 RL |
| McPAT Evaluator 插件位 + Unicorn 翻转率功耗代理降级 | F2：本机未装 McPAT，不诚实假装有；代理已有实证（T 因子） |
| IBR 定义=逐指令源操作数 bit 翻转率（输入位翻转/总输入位） | Harpocrates IBR 的 Unicorn 可计算近似；静态、快 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| `~/gem5-fi` 不存在（早期脚本硬编码） | gem5_env.py 已处理：实际在 `~/wangxu/gem5-fi`（HOME 嵌套），✅ 已确认 |

## Resources
- docs/experiments/2026-09-03-scheme-compliance-assessment.md（本日合规评估：差距 G1-G9）
- docs/superpowers/plans/2026-09-02-sdcfuzz-verification.md（E1-E6 验证方案）
- gem5_config/configs/two_level_taishan.py（CHAOS 注入器参数权威来源）

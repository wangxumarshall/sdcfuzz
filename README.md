# sdcfuzz — 面向 ARM64 的 SDC 检测用例生成与跨层验证系统

> Fork of Google [SiliFuzz](https://github.com/google/silifuzz), 原创性重构为**华为鲲鹏 920 (TaiShan V110) 上的静默数据破坏 (Silent Data Corruption, SDC) 定向检测系统**。
> 上游 SiliFuzz 只做"随机 fuzzing → 真机一致性比对"， 本项目在其工程基座之上叠加了**微架构靶向种子、定向变异、gem5-CHAOS 故障注入评分、多板分布式扫描与演化反馈闭环**， 目标是产出高 SDC 检出率的检测用例。

- 完整方案设计： [docs/scheme.md](docs/scheme.md)
- 部署运行手册： [docs/AArch64_Deployment.md](docs/AArch64_Deployment.md)
- 源码级架构合规评估（各组件实现状态）： [docs/experiments/2026-09-03-scheme-compliance-assessment.md](docs/experiments/2026-09-03-scheme-compliance-assessment.md)
- 闭环框架文档： [tools/sdc_pipeline/README.md](tools/sdc_pipeline/README.md)

## 1. 这是什么 / 解决什么问题

数据中心每万台 CPU 中就有几十颗以难以察觉的方式算错 (SDC)。SiliFuzz 的答案是"代理 fuzzing + 大规模真机执行比对"； 但其变异是 operand-blind 的随机翻转， 不针对微架构弱点。本项目 (sdcfuzz) 的核心主张是： **三因子定向生成**——

1. **模板 (骨架)**: 20 个手工微架构靶向种子 (进位链/乘法极端值/电压骤降/LSU 跨界/LSE 跨 die 等， 覆盖 8 个弱点模块)；
2. **操作数空间 (变异)**: 字典笛卡尔积 (确定性， 保覆盖下限) + Centipede 引导探索 (探索式， 提检出上限);
3. **环境应激 (放大)**: 满负载扫描 + stress-ng di/dt 带宽风暴， 逼近真实数据中心工况。

在此之上， `tools/sdc_pipeline/` 把上述流程重构为 **Gen → Assess → Filter → Validate → Feedback 五阶段闭环** (插件化， 启发式 ↔ RL 可替换， Vault 血缘持久化)， 是"持续产出高 SDC 检出率用例"的生成引擎。

**实测效果** (gem5-CHAOS 注入实验， 详细口径见 [docs/experiments](docs/experiments/) 各报告)：
- D13 directed-on-random 变异 vs 纯随机： bit-flip 检出 3.00×, 结构故障检出 7.79× (F4, 500-run); 独立复验 E2 为 3.143× (p=0.00429) / 12.8× (p=5.6e-20), 方向一致。
- 进化引擎 T 因子从 8 演化到 70, SDC 检测提升 8.8× (F5 历史证据)。
- E8 功耗-SDC: A 0% < Type-I 6.7% < Type-II 13.3% 单调 (H2 方向一致， 统计不足， 诚实标注)。
- E7 闭环 vs 纯随机： 4/60 vs 3/60, TIE (模板对操作数变异不敏感 + 注入单位修复后的实测， 揭示了逻辑掩蔽这一真实瓶颈)。

## 2. 系统架构

```
Layer 1 智能生成层        seeds/*.S (20 个微架构模板, // MUT: 可变异槽)
   │                       tools/sdc_mutator/ operand_mutator / csp_targeted_generator / evolution_engine
   │                       tools/sdc_pipeline/ mutators (位翻/字典/指令序列/功耗应力 Type-I/II)
   ▼
Layer 2 故障验证层        Unicorn 静态评估 (ACE 代理 / IBR / 翻转功耗代理 / 雪崩)
   │                       gem5-CHAOS bit/struct/多bit 注入 → 检出率 + Wilson CI
   │                       McPAT (tsv110) 功耗 Evaluator; readset 反逻辑屏蔽
   │                       Vault (JSONL): candidates/assessments + 血缘回溯
   ▼
Layer 3 硬件验证层        snap_tool make → Snap 语料 → Runner (nolibc + seccomp)
   │                       Orchestrator 满核轮转; RunSnapOutcome 2/3/4=SDC, 5/6=噪声
   │                       scripts/distributed_scan.py 3 板 (~446 核) 分布式扫描
   ▼
Layer 4 反馈闭环层        tools/sdc_experiment/feedback.py 三复跑确认 gate → seeds/evolved/ 回灌
                           tools/sdc_pipeline/pipeline.py policy (HillClimb / ε-greedy bandit)
                           → 再变异放大 → 再扫描 (loop)
```

四层的详细设计意图与差距清单见 [docs/scheme.md](docs/scheme.md) §4.3; 每个组件的 file:line 级实现证据见[合规评估报告](docs/experiments/2026-09-03-scheme-compliance-assessment.md)。

### 目录导览 (相对上游新增/重构部分)

| 路径 | 内容 |
|---|---|
| `seeds/` | 20 个微架构靶向汇编模板 (E/V/M/C/O/I/L/F 八类) + gem5 probe workload (D5–D13) + 演化产物 |
| `tools/sdc_pipeline/` | **五阶段闭环框架**： candidate/vault/mutators/evaluators/filters/readset/gem5_runner/mcpat_eval + 89 项单测 |
| `tools/sdc_mutator/` | 操作数变异器、CSP 定向生成器、三因子进化引擎、ACE 比例引擎 |
| `tools/sdc_experiment/` | 跨层实验框架： sim_sweep (gem5 注入) / hw_scan / correlation / feedback / devices |
| `scripts/` | 一键脚本 (见 §4) + 分布式扫描 + 板级部署 + D6–D13 sweep 脚本 |
| `gem5_config/` | gem5-CHAOS 注入配置 (two_level_taishan.py: CHAOSReg/CHAOSPhysReg/CHAOSLSQFwd byte_lane_skew) |
| `third_party/mcpat/` | McPAT submodule (Kunpeng920 支持), 配置 `tools/sdc_pipeline/mcpat_configs/tsv110.xml` |
| `docs/scheme.md` | 总体方案 (四层架构 + 三大创新方向 AutoµSens / RL 变异 / 功耗应力分类学) |
| `docs/experiments/` | 每个实验的完整记录 (E1–E8v2, McPAT, 合规评估) |

SiliFuzz 原生管线 (proxies → snapshot → runner → orchestrator) 保持上游结构不变， 详见 [docs/](docs/) (proxy_architecture / snap / what_makes_a_good_test) 与源码各目录; 上游 README 内容已浓缩至 §6。

## 3. 端到端数据流 (一条 Snapshot 的生命)

```
seeds/e1_carry_chain.S  ──as/objcopy──▶  seeds/bin/e1_carry_chain.bin
        │
        ├─ 阶段 A (确定性): operand_mutator 对 // MUT: 槽字典笛卡尔积
        │    → output/variants/*.S → output/bin_stage_a/*.bin
        │    → snap_tool --raw make → .pb → generate_corpus → sdc_stage_a.corpus
        │
        ├─ 阶段 B (探索式): Centipede --corpus_from_files=bin_stage_a/
        │    → /tmp/centipede_wd_guided/corpus.* → simple_fix_tool_main → sdc_stage_b.*
        │
        └─ 合并 shard_list + metadata
             │
             ▼
   reading_runner_main_nolibc (单核, nolibc+seccomp, 无 syscall 执行快照)
             │  orchestrator 每核一 runner, 轮转 shard
             ▼
   mismatch / SNAPSHOT_FAILED → RunSnapOutcome 2/3/4 = SDC 命中
             │
             ▼
   feedback.py: 三复跑确认 gate → 确认者回灌 seeds/evolved/<hash>.bin
             │
             ▼
   再变异放大 (run_guided_mutation.sh) → 再打包 → 再扫描   ⟲ 闭环
```

同一批候选在进入真机前， 可先过 `tools/sdc_pipeline` 的轻量评估 (Unicorn: ACE 代理/IBR/雪崩/翻转功耗) 和重层验证 (gem5 golden 自动注册 + CHAOS 注入检出率)， 只把高检出率候选推上真机。

## 3a. 代码架构 (面向读者/贡献者)

**上游继承的执行基座** (SiliFuzz, x86_64→AArch64 移植)：
- `proxies/` Unicorn CPU 模拟代理 (fuzz 目标)； `fuzzer/` Centipede 集成 + 指令变异器
- `common/` Snapshot proto + raw_insns_util; `snap/` 可重定位 Snap 格式 + 语料工具
- `runner/` 单核播放器 — nolibc, seccomp 沙箱, 汇编 trampoline 换寄存器态, **零 syscall**
- `orchestrator/` 进程调度器； `instruction/` 反汇编与静态指令过滤； `tracing/` 指令级 tracer
- `util/` 平台识别 (PlatformId 是支持微架构的唯一权威), `util/aarch64/` 寄存器保存/恢复 asm

**本项目新增的 SDC 智能层** (按数据流)：
- 生成： `seeds/*.S` 模板 + `tools/sdc_mutator/*` (operand_mutator 字典变异, csp_targeted_generator CSP 定向生成, evolution_engine 三因子爬山)
- 评估： `tools/sdc_pipeline/evaluators.py` (ACE 代理/IBR/翻转功耗/雪崩, 全部 Unicorn 静态) + `mcpat_eval.py` (指令构成→duty cycle→功耗) + `readset.py` (写前不读=变异无效的第一道防线)
- 验证： `tools/sdc_pipeline/gem5_runner.py` (候选自动包装 payload.S+main.c, golden 定基线, CHAOS bit/struct 注入 → 检出率+Wilson CI) + `tools/sdc_experiment/sim_sweep.py`
- 闭环： `tools/sdc_pipeline/pipeline.py` (Gen→Assess→Filter→Validate→Feedback, policy=HillClimb 或 ε-greedy bandit) + `vault.py` (JSONL 血缘) + `tools/sdc_experiment/feedback.py` (真机命中→确认→回灌)
- 部署： `scripts/distributed_scan.py` + `deploy_board.sh` + `ssh_lib.py` (3 板 ~446 核)

## 4. 一键式端到端 (快速开始)

以下脚本链覆盖"种子 → 变异 → 语料 → 真机 → 反馈”全流程。所有脚本已内置 MCE 红线 (build `--jobs=32`, fuzz/orchestrator `-j=10`/`--max_cpus`, gem5 并行 ≤4)。

前置 (一次性)： [docs/AArch64_Deployment.md](docs/AArch64_Deployment.md) §1–§3 — clang builtin 软链, MODULE.bazel 镜像改写, lss 本地 http 服务, Kunpeng→NeoverseN1 平台映射。验证平台被识别：

```bash
bazelisk build --jobs=32 -c opt //tools:silifuzz_platform_id
bazel-bin/tools/silifuzz_platform_id --short   # 鲲鹏 920 → arm-neoverse-n1
```

**Step 1 — 编译种子** (20 个模板 .S → .bin)：

```bash
bash scripts/build_seeds.sh
```

**Step 2 — 两阶段引导变异** (阶段 A 字典笛卡尔积保下限 + 阶段 B Centipede 探索提上限)：

```bash
bash scripts/run_guided_mutation.sh --all          # NUM_RUNS 环境变量可调, 默认 50000
```

**Step 3 — 打包 runner 可读语料** (两阶段输出合并为 SnapCorp shard)：

```bash
bash scripts/build_sdc_corpus.sh
# 产物: output/sdc_shard_list + output/sdc_corpus_metadata + shards
```

**Step 4 — 真机扫描**：

```bash
# 单机 (本机所有核)
orchestrator/silifuzz_orchestrator_main --duration=30s \
    --runner=runner/reading_runner_main_nolibc \
    --shard_list_file=output/sdc_shard_list \
    --corpus_metadata_file=output/sdc_corpus_metadata

# 或 3 板 ~446 核分布式 (deploy + 扫描 + 收结果)
bash scripts/deploy_board.sh --all
python3 scripts/distributed_scan.py --duration 60s     # --no-stress 可关 stress-ng
python3 scripts/collect_results.py
```

**Step 5 — 演化反馈闭环** (SDC 命中 → 确认 → 回灌 → 再变异 → 再扫描)：

```bash
# 跨层实验框架路径 (推荐): feedback.py 三复跑确认 gate
bash scripts/experiments/feedback_loop.sh <exp_dir> <corpus_dir>

# 或 legacy 路径 (读 output/distributed/results.json)
bash scripts/sdc_evolve.sh
```

**闭环生成引擎** (轻量 Unicorn 评估 + 可选 gem5 重层验证, 见 [tools/sdc_pipeline/README.md](tools/sdc_pipeline/README.md))：

```bash
python3 -m pytest tools/sdc_pipeline/ -q              # 框架单测
# Python API 用法见 tools/sdc_pipeline/README.md 快速上手节
```

**CI 不退化验证** (种子/变异器改动后)：

```bash
bash scripts/ci_verify.sh    # 编译/filter/make/replay/变体数≥基线 五项 gate
```

## 5. 高 SDC 检出率从哪里来 (机理)

1. **定向而非随机**： D13 `pick_high_toggle` (popcount 进位链代理) 的 directed-on-random 相比纯随机 bit-flip 检出提升 3.00×, 结构故障 7.79× (gem5-CHAOS 实测)。
2. **避开逻辑掩蔽**： M2/E7 实证变异目标被"写前不读"覆写则变异无效。`readset.py` 只在指令序列实际消费的寄存器上选变异目标； avalanche 评估器惩罚高掩蔽候选。
3. **功耗应力注入**： Type-I (持续高功耗)/Type-II (高低交替 di/dt) 变异器 + McPAT (tsv110) 功耗评估， E8 实测检出率单调性 A < Type-I < Type-II。
4. **故障注入预验证**： gem5-CHAOS (bit/byte_lane_skew/多bit) 在上真机前量化候选检出率， 只推高检出率候选； fault-clock 取候选自身 ROI [20%,80%]。
5. **真机环境应激**： 满负载 + stress-ng 制造 di/bandwidth 风暴， 逼近数据中心工况； RunSnapOutcome 区分真 SDC (2/3/4) 与噪声 (5/6, 如满负载 fork/mmap 资源耗尽 SIGSEGV)。
6. **闭环持续进化**： policy (HillClimb → ε-greedy bandit) 按上代各变异器表现调权； Vault 血缘可回溯任一候选的演化路径。

## 6. SiliFuzz 原生用法 (上游遗留, 浓缩版)

上游 x86_64 工作流保留可用， 按需查阅：
- 概念术语 (Snapshot/Snap/Runner/Orchestrator/Corpus): 原 README "Terminology" — [docs/proxy_architecture.md](docs/proxy_architecture.md)、[docs/snap.md](docs/snap.md)
- `snap_tool` make/print/play/generate_corpus, `fuzz_filter_tool`, `simple_fix_tool`, hashtest_generator: 原上游 README "Tools" 节
- Centipede + Unicorn x86_64 代理 fuzzing: 原上游 README "Prework"
- Trophies (AMD/ARM errata): 原上游 README "Trophies"

国内 openEuler/aarch64 环境的移植细节 (依赖镜像、CRC32 编译选项、Kunpeng 平台识别) 全部在 [docs/AArch64_Deployment.md](docs/AArch64_Deployment.md)。

## 7. 已知边界与诚实声明

以下是实测发现并如实记录的局限， 不掩饰：
1. **AutoµSens / RL 全流程 / 功耗应力 Type-III**： scheme 的三大创新组件截至 2026-09-03 实现度为 0, 当前只有 ε-greedy bandit (RL 第一步) 与 Type-I/II 变异器雏形。详见[合规评估报告 §7 差距清单](docs/experiments/2026-09-03-scheme-compliance-assessment.md)。
2. **E7 闭环 vs 纯随机 TIE**： 4/60 vs 3/60 — 现有自包含模板对操作数变异不敏感 (LOAD 宏自带常量构造), 需 D13 风格消费初值寄存器的种子或 `// MUT:` 槽改写。
3. **E5 Sim→HW 关联 NOT_SIGNIFICANT**: ρ=-0.2219, p=0.74733, 只有方法学骨架， 无阳性结果。
4. **0201 板不可达**： 实际 3 板可用 (0101/0102/0103), E4 仅单远程板 (0101) 全链路验证； "4 板 446 核" 的历史表述已收敛为 "3 板 ~446 核"。
5. **McPAT 绝对功耗高估**： 最低支持 22nm, 真实 V110 是 7nm; 指标名带 `power_mcpat_w` 且携带 `power_note` 近似声明, 相对比较可信。
6. **短序列 ACE 窗口小**： 5 指令序列 bit×10 注入 diverge=0 (CI 上界 0.28), 需更长序列/更多样本。
7. **满负载 SIGSEGV 噪声**： `--max_cpus=$(nproc)` 满载时偶发 fork/mmap 资源耗尽击中 snap 外路径, orchestrator 容错继续, 按噪声统计不按 SDC 计。
8. **MCE 红线**： 128 核服务器上满核并行构建/fuzzing 会触发内核 Machine Check Exception 物理重启, 所有脚本已内置 `--jobs=32`/`-j=10`/gem5 ≤4 上限。

## 8. 测试

```bash
# Python 框架 (闭环/变异/实验)
python3 -m pytest tools/sdc_pipeline/ tools/sdc_mutator/ tools/sdc_experiment/ -q   # 89 项

# C++ 基座 (上游测试, 按 package 跑)
bazelisk test --jobs=32 -c opt //util/...   # 单包示例; 全量 //... 同理
```

## 9. 引用

- SiliFuzz: Fuzzing CPUs by proxy — 上游论文 (本 fork 未携带 PDF, 见 google/silifuzz 仓库 `paper/silifuzz.pdf`)
- Harpocrates (ISCA'24) / Harpocrates++ (IEEE Micro'26): 最近的竞争工作, 差异化定位见 [docs/scheme.md](docs/scheme.md) §3
- gem5-fi (CHAOS 故障注入): `github.com/wangxumarshall/gem5-fi` (外部仓库, 配置入口 `gem5_config/configs/two_level_taishan.py`)

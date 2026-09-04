# 一键式端到端流程总控脚本实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 写一个总控脚本 `scripts/run_e2e.sh`，把"种子编译 → 两阶段引导变异 → 语料打包 → 真机扫描 → 结果收集 → 演化反馈"五步现有脚本串成单命令端到端流程，并支持 `--loop` 演化迭代与 MCE 红线防护。

**Architecture:** 纯 bash 编排层，只串联既有脚本不改其内部逻辑（不推倒现有代码原则）。执行模式三档：`--scan-mode local|distributed`（单机 orchestrator vs 3 板分布式）。反馈走双路径：legacy `sdc_evolve.sh`（读 `output/distributed/results.json`）或跨层框架 `feedback_loop.sh`（读 hw_*.json）。产物统一落 `output/e2e/<run_id>/`，run manifest 全程记录。

**Tech Stack:** bash + 既有脚本（build_seeds.sh / run_guided_mutation.sh / build_sdc_corpus.sh / deploy_board.sh / distributed_scan.py / collect_results.py / sdc_evolve.sh / experiments/feedback_loop.sh）。

**Spec:** README §4 一键式端到端（五步脚本链）；scripts/experiments/feedback_loop.sh 头注释（legacy 与框架双回灌路径的实测差异）。

## Global Constraints

- **one-patch-per-unit**：本计划 = 2 个 commit（Task 1 脚本本体，Task 2 README/文档接线）。verify 通过才 commit，push 到 `feat/sdc-pipeline-framework`。
- **MCE 红线**：脚本自身不新开任何并行；所有并行上限由下游脚本自带（build `--jobs=32`、centipede/orchestrator `-j=10`、`--max_cpus` 满核但单机 orchestrator 单进程、gem5 ≤4）。
- **诚实纪律**：脚本对每步真实退出码做硬校验（`set -euo pipefail`），失败即停不继续；skip 的步骤如实打印 SKIP 与原因。
- **不推倒现有代码**：总控只调用既有脚本/工具的**已验证接口**（本计划前已逐一源码取证），不复制其逻辑。

## 串联的下游接口（源码取证定稿）

| 步骤 | 命令 | 关键接口事实 |
|---|---|---|
| 1 种子 | `bash scripts/build_seeds.sh` | 产物 `seeds/bin/*.bin`；as/objcopy 本机原生 |
| 2 变异 | `bash scripts/run_guided_mutation.sh --all` | 阶段 A 产物 `output/variants/`+`output/bin_stage_a/`；阶段 B 产物 `/tmp/centipede_wd_guided/corpus.*`；`NUM_RUNS` 环境变量可调 |
| 3 打包 | `bash scripts/build_sdc_corpus.sh` | 产物 `output/sdc_shard_list`+`output/sdc_corpus_metadata`+`output/sdc_stage_*.corpus`；末尾自带 runner replay 自检 |
| 4a 本机扫描 | `silifuzz_orchestrator_main --duration=D --runner=... --shard_list_file=... --corpus_metadata_file=...` | 二进制位置 `bazel-bin/orchestrator/` 或 `/usr/local/bin/`；本机扫描不传 `--max_cpus`（用默认全核） |
| 4b 分布式 | `bash scripts/deploy_board.sh --all` → `python3 scripts/distributed_scan.py --duration D [--no-stress]` → `python3 scripts/collect_results.py` | deploy/scan 默认 4 板（0201 不可达会打印 error 但脚本容错继续）；collect 产物 `output/distributed/results.json`；SDC 命中数在 `results.json` 各板 `sdc_hits` 求和 |
| 5a legacy 反馈 | `bash scripts/sdc_evolve.sh`（`SCAN_ONLY` 环境变量可跳过重扫描） | 读 `output/distributed/results.json`；有命中→提取 hash 回灌 `seeds/evolved/`→centipede 放大→重新打包+部署 |
| 5b 框架反馈 | `bash scripts/experiments/feedback_loop.sh <exp_dir> <corpus_dir>` | 读 hw_*.json（来自 hw_scan.py），三复跑确认 gate；`feedback.py --exp-dir --corpus [--pb-dir]` |
| 回归 | `bash scripts/ci_verify.sh` | 五项 gate（编译/filter/make/replay/变体数≥150） |

## 已识别的设计决策

1. **默认单机模式**：distributed 模式依赖 3 板 SSH 可达 + root/sdc 密码（`ssh_lib.py`，密码在脚本内默认 `SDC@2026`），属于环境侵入操作，必须显式 `--scan-mode distributed` 才走。默认 `local`。
2. **反馈路径选择**：distributed 模式天然产 `output/distributed/results.json` → legacy `sdc_evolve.sh` 直接可用；local 模式无该文件 → 需用 hw_scan 框架路径（`hw_scan.py --device local --corpus output/sdc_stage_a.corpus --exp exp03` 产 hw_*.json → `feedback_loop.sh`）。为控首个版本复杂度，local 模式的反馈默认提示手动接 hw_scan（打印下一步命令），`--feedback hw` 时才自动执行。
3. **`--loop N`**：演化迭代次数。每轮 = 步骤 2-5（跳过 build_seeds，种子已含 evolved/）。轮间判据：`results.json` 的 sdc_hits 求和 >0 时 sdc_evolve.sh 自带回灌-重打包；=0 时打印"语料干净"诚实退出循环。
4. **`--duration` 透传**：`30s`/`60s`/`8h` 格式直接透传给 orchestrator/distributed_scan.py。
5. **run manifest**：`output/e2e/<ts>/manifest.json` 记录 run_id/mode/duration/loop/各步产物路径/退出码，用 python3 一行脚本写（bash 不便嵌 JSON）。
6. **不做 build**：总控不触发 bazel build（README §4 前置已声明一次性前置）。但做**工具存在性 preflight**：runner/orchestrator/snap_tool/simple_fix_tool/centipede 任一缺失即 fail-fast，并打印缺失工具与补建命令（README §4 前置节引用）。
7. **幂等性**：重复运行无害——每步脚本自身幂等（build_seeds 重编译、run_guided_mutation 重建 variants、build_sdc_corpus 重打包覆盖）。

## Task 1: `scripts/run_e2e.sh` 总控脚本

**文件**：`scripts/run_e2e.sh`（新建，chmod +x）

**功能清单**：
- 参数：`--scan-mode local|distributed`（默认 local）、`--duration D`（默认 60s）、`--loop N`（默认 1）、`--num-runs N`（透传 NUM_RUNS，默认 50000）、`--no-stress`、`--feedback auto|legacy|hw|none`（默认 auto：distributed→legacy、local→hw）、`--skip-mutation`（直接用现有语料扫描）、`--dry-run`（打印将执行的命令序列不执行）。
- preflight：工具存在性检查（`/usr/local/bin` 与 `bazel-bin` 双路径探测）+ `output/` 可写。
- Step 1-3 无条件执行（`--skip-mutation` 时跳过 2 仍执行 3）。
- Step 4 按 scan-mode 分支；distributed 先 deploy 再 scan 再 collect。
- Step 5 按反馈策略：auto 分派 + `sdc_evolve.sh` 或 `feedback_loop.sh` 或提示。
- `--loop N` 外层 for 循环包住 2-5，每轮写 manifest 分节。
- 日志：每步 stdout/stderr tee 到 `output/e2e/<run_id>/stepN_*.log`。
- 全程 `set -euo pipefail`；每步前后打时间戳与耗时。

**验证命令**（Task 1 完成时全部真实执行并引用输出）：
1. `bash -n scripts/run_e2e.sh` — 语法检查
2. `bash scripts/run_e2e.sh --dry-run` — dry-run 打印命令序列（不执行，无副作用）
3. `bash scripts/run_e2e.sh --scan-mode local --duration 10s --skip-mutation` — 真实小规模端到端（种子已编好、语料已在：build_seeds + build_sdc_corpus + 本机 orchestrator 10s）
4. 回归：`bash scripts/ci_verify.sh` — 五项 gate 不退化

**Commit**: `feat(scripts): run_e2e.sh 一键式端到端总控——五步脚本链单命令串联+loop+MCE红线防护`

## Task 2: README §4 接线 + 演进表更新

**文件**：`README.md`（§4 一键式节开头改为 run_e2e.sh 单命令，五步明细降为"内部步骤"）、`tools/sdc_pipeline/README.md`（演进表加一行）、`docs/superpowers/plans/2026-09-04-sdc-e2e-master-script.md`（勾选全部 checkbox）。

**验证命令**：
1. README 中引用的 `scripts/run_e2e.sh` 存在且可执行
2. `python3 -m pytest tools/sdc_pipeline/ -q` 不退化（89 项）

**Commit**: `docs(readme): 一键式端到端接线 run_e2e.sh——单命令流程+参数说明`

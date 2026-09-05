# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**北极星**：本仓库正从 "SiliFuzz AArch64 移植" 演进为 **sdcfuzz** —— 一个 ARM64 原生的 SDC（静默数据破坏）检测用例生成框架，目标架构见 [docs/scheme.md](docs/scheme.md)（四层架构 + 三大创新：AutoµSens 自动靶向生成 / RL 反逻辑屏蔽变异 / 功耗应力-SDC 因果分析）。scheme.md 是方向性的目标态描述，**不等于当前代码现状**；能力现状以本节末尾的状态注记为准。演进原则（scheme.md §4.1）：**承袭 SiliFuzz 工程基座，增量叠加，不推倒重写**。

SiliFuzz 基座：fuzzing software **proxies** (CPU emulators / disassemblers) 生成 **corpus**，在真实 CPU 上大规模执行并检查 divergent end states。见 [paper](paper/silifuzz.pdf) 和 [docs/proxy_architecture.md](docs/proxy_architecture.md)。

The core data unit is a **Snapshot** (`silifuzz.proto.Snapshot`): a short instruction sequence plus an initial register/memory state, executed deterministically. A **Snap** is the relocatable in-memory form a Runner loads from disk. Each Snap carries exactly one expected end state, so Snaps are microarchitecture-specific.

This checkout is an **active AArch64 port** targeting Huawei Kunpeng CPUs on openEuler — the upstream is x86_64-first. `README_AArch64_Deployment.md` is the canonical end-to-end runbook for this port (dependency fixes, build, Centipede corpus generation). Treat x86_64-only assumptions in comments and code as porting targets, not ground truth.

### 四层架构 ↔ 仓库目录映射（sdcfuzz 视角）

| Layer (scheme.md §4.3) | 仓库位置 |
|---|---|
| **L1 智能生成层**（种子/变异/未来 RL） | `seeds/`（20 个微架构靶向 .S 模板 + operand_dict.md）、`tools/sdc_mutator/`（D1-D13 进化引擎、操作数字典、CSP 定向生成）、`tools/sdc_pipeline/mutators.py` + `pipeline.py` policy（变异器池 + ε-greedy bandit）、`fuzzer/`（ISA 感知指令 mutator，已接入 build_fuzz.sh） |
| **L2 故障验证层**（评估/注入/功耗/持久化） | `tools/sdc_pipeline/evaluators.py`（ACE 代理/IBR）、`gem5_runner.py`（golden vs CHAOS 注入差分）、`mcpat_eval.py`（功耗近似）、`vault.py`（候选+血缘持久化）、`gem5_config/`（two_level_taishan.py CHAOS 注入配置）、`tools/sdc_experiment/`（gem5_env/sim_sweep）、`third_party/mcpat/` |
| **L3 硬件验证层**（真机执行/分布式/关联） | `orchestrator/`、`tools/minimizer/`、`tools/sdc_experiment/`（hw_scan/devices 多板扫描/correlation Sim→HW 关联/feedback 命中回灌）、`scripts/distributed_scan.py` + `deploy_board.sh` |
| **L4 在线部署层**（Runner/未来调度） | `runner/`（nolibc/seccomp 裸金属执行）、`scripts/run_e2e.sh`（生产链总控：编译种子→引导变异→打包→真机扫描→反馈回灌） |

上游 SiliFuzz 基座目录（`proxies/ common/ snap/ runner/ orchestrator/ fuzzer/ instruction/ tracing/ util/ player/ proto/ tool_libs/ build_defs/`）见下文 Directory map——它们是四层架构的地基，不是待重构对象。

### 能力现状注记（2026-09-05，对照 scheme.md §4.2 六项补齐能力）

1. **ACE/IBR 评估**：部分落地（Unicorn 级代理，`sdc_pipeline/evaluators.py`）；ACE lifetime / AutoµSens 未实现。
2. **gem5 golden vs 注入差分**：已落地（`gem5_runner.py`，M2/E7 实证）。gem5 本体在 `~/wangxu/gem5-fi-wangxu/`（HOME=/home/sdc 下用户目录嵌套），路径解析经 `tools/sdc_experiment/gem5_env.py`。
3. **McPAT 功耗**：近似口径已落地（`mcpat_eval.py`，tsv110.xml，22nm 近似 7nm 诚实标注；E8 实证）。
4. **ISA 感知变异**：部分落地（指令级 `fuzzer/program_aarch64.cc` 已入产线；操作数级字典/位翻/功耗应力已入 sdc_pipeline 变异器池）。
5. **负载感知在线调度**：未实现（零代码）。
6. **RL 变异**：接口 + ε-greedy bandit 已实装（`pipeline.py` EpsilonGreedyBanditPolicy + `bandit_bench.py`），超出 scheme.md 旧注记；reward 仍是 Unicorn 代理指标，非 gem5 检出率。

已知边界（诚实记录）：Vault 目前仅 sdc_pipeline 内部读写（无外部消费者）；sim→hw 关联在组粒度（E5 verdict NOT_SIGNIFICANT）；Layer 4 的 PMU 风险评分/自适应调度未动工。sdcbench 1000 序列生产线（`tools/sdc_experiment/sdcbench_*.py`）是独立交付线，未并入 pipeline 闭环。

## Build & run

Bazel with bzlmod (`bazelisk`). Toolchain is clang; `.bazelrc` forces `-std=c++20`, `-fno-exceptions`, `lld`. The build is self-hosted (host config matches target config).

Core targets:
```bash
bazel build -c opt //tools:{snap_corpus_tool,fuzz_filter_tool,snap_tool,silifuzz_platform_id,simple_fix_tool_main} \
    //runner:reading_runner_main_nolibc \
    //orchestrator:silifuzz_orchestrator_main
```
Tests: `bazel test -c opt //...` (or scope to a package, e.g. `//util/...`). Run a single target: `bazel test -c opt //util:crc32c_test`.

**AArch64 / openEuler porting prerequisites** (from `README_AArch64_Deployment.md` — required, not optional, on this host):
- `compiler-rt` builtin path: symlink the openEuler-named `libclang_rt.builtins.a` into `/usr/lib64/clang/17/lib/linux/libclang_rt.builtins-aarch64.a`.
- `MODULE.bazel` dependency mirrors are rewritten to reach China-friendly mirrors (`ghproxy.net` for fuzztest/cityhash/etc., `gitee.com/mirrors/Unicorn.git` for unicorn). `lss` is fetched from a local `http://127.0.0.1:8000/lss.tar.gz` server — start that or the build hangs on `http_archive`.
- CRC32 hardware builtins need `-march=armv8-a+crc` on the `crc32c` target (already patched in `util/BUILD`).
- Huawei Kunpeng 920 has its own PlatformId `kArmKunpeng920` (part-number matched in `util/platform.cc` `ArmPlatformIdFromMainId`). ⚠️ All corpus/snapshots generated before 2026-09-05 carry `arm-neoverse-n1` end states and are **incompatible** — regenerate with `--target_platform=arm-kunpeng920`. Also: `/usr/local/bin/snap_tool` (deployed 2026-08-25) predates the new enum and rejects `arm-kunpeng920`; prefer `bazel-bin/tools/snap_tool`.

**⚠️ MCE / hardware-reset warning**: this is a many-core (128c) server. Do **not** run full-core parallel Bazel builds or high-parallelism fuzzing — it triggers kernel Machine Check Exceptions and physically reboots the box. Cap with `--jobs=32` for builds and `-j=10` for Centipede. `build_fuzz.sh` already enforces these caps; follow it as the reference for any new build/fuzz script.

End-to-end fuzzing + corpus generation (the `build_fuzz.sh` flow):
1. Build `//proxies:unicorn_aarch64` with Centipede coverage flags via `--per_file_copt`.
2. Build `@fuzztest//centipede:centipede`.
3. Run centipede against the unicorn proxy (`-j=10 --num_runs=...`) → raw `corpus.*`.
4. `simple_fix_tool_main` converts raw inputs → sharded relocatable corpus runnable by `reading_runner_main_nolibc`.
5. Orchestrator cycles shards across all cores: `silifuzz_orchestrator_main --shard_list_file=... --corpus_metadata_file=...`.

Inspect snapshots with `snap_tool print|make|play|generate_corpus` (see README "How to" section).

**sdcfuzz 生产链路**（SDC 研究，与上面 build_fuzz.sh 的通用 fuzzing 链并存）：`scripts/run_e2e.sh` = build_seeds（模板 .S → .bin）→ run_guided_mutation（操作数字典变异 + Centipede 探索）→ build_sdc_corpus（.bin → SnapCorpus）→ 真机扫描（local 或 4 板分布式）→ feedback（SDC 命中三复跑确认 → 回灌 `seeds/evolved/`）。研究闭环（Gen→Assess→Filter→Validate→Feedback，含 gem5/McPAT/Vault）在 `tools/sdc_pipeline/`（README 有架构图）。两套链路独立运行，尚未互连。

## Architecture

Pipeline: **proxy fuzzing** (Centipede + Unicorn) → **corpus** (sharded relocatable Snaps) → **runner** (one per core, plays Snaps) → **orchestrator** (drives runners, collects failures).

Directory map (big picture — each is a Bazel package):
- `proxies/` — Unicorn-based CPU emulators per arch (`unicorn_aarch64.cc`, `unicorn_x86_64.cc`). Fuzz targets that Centipede mutates.
- `common/` — `Snapshot` proto representation, `HarnessTracer`, memory mapping/state, `raw_insns_util` (raw bytes → Snapshot). Shared by tools and runner.
- `snap/` — relocatable in-memory Snap format: `snap.h`, `snap_relocator`, `snap_corpus_util`, per-arch `exit_sequence` + `gen/` (relocatable generator). On-disk format = in-memory with pointers→offsets.
- `runner/` — single-core player. `runner.cc`/`runner.h` core; `snap_maker` builds Snaps from Snapshots; per-arch dirs (`aarch64/`, `x86_64/`) hold the assembly trampolines (`snap_exit.S`, `start.S` under `util/aarch64/`) that swap register state and jump into the snapshot with **no syscalls** (seccomp-sandboxed). `driver/` is the runner-as-library entry.
- `orchestrator/` — process supervisor: `silifuzz_orchestrator.cc` spawns/cycles runners, `result_collector` aggregates, `corpus_util`/`corpus_metadata.proto` manage shards.
- `fuzzer/` — Centipede integration: `silifuzz_centipede_main.cc`, `program_*` mutators (`program_aarch64.cc`/`program_x86_64.cc` per-arch instruction mutators).
- `instruction/` — disassembly layer behind `default_disassembler` (xed on x86, capstone on aarch64), `static_insn_filter` (banned/non-deterministic instruction exclusion, e.g. CPUID).
- `tracing/` — instruction-level tracers used to compute end states: `native_tracer` (real CPU), `unicorn_tracer_*` (emulator), `disassembling_snap_tracer`, `extension_registers`.
- `util/` — platform/CPU detection (`platform.cc`/`platform.h` `PlatformId` enum is the source of truth for supported uarches), `cpu_id`, `crc32c`, `arch.h` arch dispatch. Per-arch `util/aarch64/` holds register save/restore asm (`save_register_groups_to_buffer.S`, `clear_register_groups.S`, `sve.*`) and arch-specific `platform.cc`.
- `player/`, `proto/`, `tools/`, `tool_libs/`, `tracing/`, `build_defs/` — supporting.

**nolibc**: the runner is a freestanding, seccomp-sandboxed binary with no libc and no global static initializers (enforced by `runner/global_static_initializers_test.sh` checking for absence of `.init_array`). Build macros `cc_binary_nolibc` / `cc_library_nolibc` / `cc_library_plus_nolibc` / `cc_test_nolibc` live in `util/nolibc.bzl`. A target must use the `_plus_nolibc` / `_nolibc` variants if it links into the runner — regular `cc_library`/`cc_test` will not. `integer_instructions_only` is an AArch64 nolibc build flag restricting to integer instructions.

`PlatformId` (`util/platform.h`) is the single enum naming supported microarchitectures and is mirrored into `proto/snapshot.proto`; `common/snapshot_proto.cc` cross-checks the two stay in sync. New uarches require touching both plus `ArmPlatformIdFromMainId`/`x86` detection.

## Patch discipline (feature/porting/bug/adapter)

This repository enforces a strict one-patch-per-unit workflow. Apply it to **every** change, including ARM64 porting points, feature development, bug fixes, and architecture adapters.

### One patch per unit

Each feature, functionality point, bug, or adaptation point is its own commit. Never bundle unrelated changes into one commit. A "unit" means a single coherent item from a work list (e.g. "#13 uncore frequency exit bug" is one patch; "#12 thermal monitor" is the next). When a task spans several numbered points, solve them **one at a time, sequentially** — finish one (verify → commit → push) before starting the next. Do not parallelize or batch.

### Self-verification before commit (mandatory, 100% real)

After writing code and before committing, the AI **must verify itself** with real commands — no claims based on "it should work" or reading the diff. Specifically:

1. **Build clean**: any warning/error introduced by the change is a failure.
2. **Functional verification**: run the actual affected behavior with real commands and capture real output. Quote the real observed output as proof, not a prediction.
3. **Regression check**: run at least one unaffected test and confirm `exit: pass`, zero SIGSEGV, to prove no collateral breakage.

Do **not** commit if any of these fail. If a verification step fails, fix and re-verify until it passes. Skipping verification or fabricating results ("assumed to pass") is strictly forbidden — every claim in the commit message must correspond to a command the AI actually ran.

### Auto-push to a non-main branch after verification

Once a patch is committed and verified, **push it automatically to the remote** — do not wait to be asked, and do not push to `main`. Work on a feature branch (e.g. `fix/mce-check-arm64-null-test-run`) and `git push` after each commit. If on `main` when starting work, create/switch to a feature branch first (`git checkout -b <branch>`) before committing.

Commit message must not end with:
```
Co-Authored-By: Claude <noreply@anthropic.com>
```
### Plan-driven workflow (mandatory for every non-trivial change)

All non-trivial work — feature development, porting, refactors, multi-step fixes, anything beyond a single obvious line — **must** be executed via a written plan using the `superpowers:writing-plans` skill, not ad-hoc. "Trivial" means a typo or a one-line obvious fix the change itself describes completely.

1. **Plan first**: before writing any code, invoke `superpowers:writing-plans` and save the plan to `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`. The plan defines one-patch-per-unit decomposition, exact files, real test commands, and per-step checkboxes (`- [ ]`).
2. **Plan == the work list**: each plan task maps to exactly one commit, satisfying "One patch per unit" above. Do not bundle multiple plan tasks into one commit, and do not commit work not in the plan.
3. **Track progress visibly**: implement via `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Check off each `- [ ]` as it completes; the live plan file is the single source of truth for what is done vs pending. If the scope changes mid-execution, edit the plan file first, then proceed.
4. **Verify against the plan, not the diff**: the self-verification above applies per task; a task is not "done" until its plan-specified verification command's real output is quoted and its checkbox is checked.
5. **Provenance**: keep plan files in the repo under `docs/superpowers/plans/` (they document *why* a change was made one unit at a time, complementing git history).

If a request would produce more than one commit, write the plan first. No plan, no code.

### Placeholder-test honesty

When porting a feature that cannot be fully implemented yet (e.g. SMI counting on ARM, IST backend), the test must report a clean skip with reason `"to be implemented (placeholder): <what's missing>"` (return `EXIT_SKIP` from `test_init`, **not** `EXIT_SUCCESS`). A no-op test that returns success is a bug — it falsely reports `pass`. The `mce_check` test, by contrast, is a *real* EDAC-backed test on ARM64 and should `pass`.
### 必须诚实、不能说谎、必须100%服从事实、所有工作和结果必须基于事实并且经过严格的逻辑推理或实证，永远尊重事实、永远真诚。 用人类读懂的语言，消除AI味，深入浅>出、循序渐进、言简意赅、推理严密

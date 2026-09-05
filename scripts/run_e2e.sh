#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# run_e2e.sh — 一键式端到端 SDC 检测流程总控
#
# 串联五步既有脚本 (只编排不改其内部逻辑):
#   1. build_seeds.sh           20 个微架构模板 .S → .bin
#   2. run_guided_mutation.sh   阶段 A 字典笛卡尔积(保下限) + 阶段 B Centipede(提上限)
#   3. build_sdc_corpus.sh      两阶段产物合并 → runner 可读 SnapCorp shard
#   4. 真机扫描                 local: 本机 orchestrator / distributed: 3 板部署+扫描+收集
#   5. 演化反馈                 SDC 命中 → 回灌 seeds/evolved/ → (loop 时) 再变异再扫描
#
# 用法:
#   bash scripts/run_e2e.sh                                    # 本机 60s 扫描
#   bash scripts/run_e2e.sh --scan-mode distributed --duration 5m
#   bash scripts/run_e2e.sh --loop 3 --duration 2m             # 3 轮演化迭代
#   bash scripts/run_e2e.sh --skip-mutation --duration 10s     # 用现有语料直接扫
#   bash scripts/run_e2e.sh --dry-run                          # 只打印命令序列
#
# MCE 红线: 本脚本不开新并行; 并行上限全部由下游脚本自带
#   (bazel --jobs=32 / centipede -j=10 / orchestrator 单进程 / gem5 ≤4)。
# 前置 (一次性, 见 README §4): 依赖镜像 + bazel build 核心目标。
set -euo pipefail
cd "$(dirname "$0")/.."

# ---------------- 参数 ----------------
SCAN_MODE="local"          # local | distributed
DURATION="60s"             # 透传 orchestrator/distributed_scan.py
LOOP=1                     # 演化迭代轮数 (每轮 = 步骤2-5)
NUM_RUNS="${NUM_RUNS:-50000}"  # centipede 阶段 B 变异数
NO_STRESS=""               # 空 = 开 stress-ng 环境毒化 (distributed)
FEEDBACK="auto"            # auto | legacy | hw | none
SKIP_MUTATION=""           # 跳过步骤 2 (直接扫现有语料)
DRY_RUN="${DRY_RUN:-}"    # 保留环境变量形式 (DRY_RUN=1); --dry-run flag 亦设 1

usage() { sed -n '4,20p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --scan-mode)   SCAN_MODE="${2:?}"; shift 2 ;;
    --duration)    DURATION="${2:?}"; shift 2 ;;
    --loop)        LOOP="${2:?}"; shift 2 ;;
    --num-runs)    NUM_RUNS="${2:?}"; shift 2 ;;
    --no-stress)   NO_STRESS="--no-stress"; shift ;;
    --feedback)    FEEDBACK="${2:?}"; shift 2 ;;
    --skip-mutation) SKIP_MUTATION="1"; shift ;;
    --dry-run)     DRY_RUN="1"; shift ;;
    -h|--help)     usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done
case "$SCAN_MODE" in local|distributed) ;; *) echo "--scan-mode 须为 local|distributed" >&2; exit 1 ;; esac
case "$FEEDBACK" in auto|legacy|hw|none) ;; *) echo "--feedback 须为 auto|legacy|hw|none" >&2; exit 1 ;; esac

# ---------------- 工具定位 (双路径探测) ----------------
# /usr/local/bin: deploy 脚本部署的规范位置; bazel-bin: 刚构建未部署时。
find_tool() {
  if [ -x "/usr/local/bin/$1" ]; then echo "/usr/local/bin/$1"
  elif [ -x "bazel-bin/${2:-$1}" ]; then echo "bazel-bin/${2:-$1}"
  else echo ""; fi
}
RUNNER=$(find_tool reading_runner_main_nolibc runner/reading_runner_main_nolibc)
ORCH=$(find_tool silifuzz_orchestrator_main orchestrator/silifuzz_orchestrator_main)
SNAP_TOOL=$(find_tool snap_tool tools/snap_tool)
CENTIPEDE="bazel-bin/external/fuzztest+/centipede/centipede"

preflight() {
  local missing=0
  for t in "$RUNNER" "$ORCH" "$SNAP_TOOL" "$CENTIPEDE"; do
    if [ -z "$t" ] || [ ! -x "$t" ]; then
      echo "  缺失: $t"
      missing=1
    fi
  done
  if [ "$missing" -eq 1 ]; then
    echo "FAIL: 工具不齐。补建 (README §4 前置):" >&2
    echo "  bazelisk build --jobs=32 -c opt //tools/{snap_corpus_tool,fuzz_filter_tool,snap_tool,silifuzz_platform_id,simple_fix_tool_main} \\" >&2
    echo "       //runner:reading_runner_main_nolibc //orchestrator:silifuzz_orchestrator_main" >&2
    echo "  并/或: sudo cp bazel-bin/tools/snap_tool bazel-bin/runner/... /usr/local/bin/ (docs/AArch64_Deployment.md §3)" >&2
    return 1
  fi
  echo "  runner:     $RUNNER"
  echo "  orchestrator: $ORCH"
  echo "  snap_tool:  $SNAP_TOOL"
  echo "  centipede:  $CENTIPEDE"
  return 0
}

# ---------------- 执行包装: 日志 + 计时 + dry-run ----------------
RUN_ID="e2e_$(date +%Y%m%d_%H%M%S)"
E2E_DIR="output/e2e/$RUN_ID"
log() { echo "[run_e2e $(date +%H:%M:%S)] $*"; }

run_step() {
  # run_step <step_name> <cmd...>  — cmd 为简单命令时直接跑; 复杂管道由调用方 bash -c
  local name="$1"; shift
  local log_f="$E2E_DIR/${name}.log"
  if [ -n "$DRY_RUN" ]; then
    echo "[dry-run] [$name] $*"
    return 0
  fi
  local t0=$SECONDS elapsed rc
  log "STEP $name 开始: $*"
  if "$@" > >(tee "$log_f") 2>&1; then
    elapsed=$(_elapsed "$t0")
    log "STEP $name 完成 ($elapsed)"
    return 0
  else
    rc=$?
    log "STEP $name 失败 (rc=$rc), 日志: $log_f — fail-fast 停止"
    return $rc
  fi
}
_elapsed() { echo "$(($SECONDS - $1))s"; }

_dur_s() {  # '60s'->60 '5m'->300 '8h'->28800; 无单位按秒; 带默认值
  local d="${1:-$2}" n unit
  n=$(echo "$d" | grep -oE '^[0-9]+'); unit=$(echo "$d" | grep -oE '[smh]$' || true)
  [ -z "$n" ] && n="$2"
  case "$unit" in s) echo $((n)) ;; m) echo $((n*60)) ;; h) echo $((n*3600)) ;; *) echo $((n)) ;; esac
}

_hw_max_cpus() {  # hw_scan 用本机核数, 上限 64 (experiment_config.MAX_CPUS_HARD_LIMIT MCE 红线)
  local n; n=$(nproc); [ "$n" -gt 64 ] && echo 64 || echo "$n"
}

# dry-run 模式下 run_step 只打印; bash -c 的复杂命令统一走 run_sh
run_sh() {  # run_sh <step_name> <shell 字符串>
  local name="$1" cmd="$2"
  if [ -n "$DRY_RUN" ]; then echo "[dry-run] [$name] $cmd"; return 0; fi
  local log_f="$E2E_DIR/${name}.log"
  local t0=$SECONDS elapsed rc
  log "STEP $name 开始: $cmd"
  if bash -c "$cmd" > >(tee "$log_f") 2>&1; then
    elapsed=$(_elapsed "$t0")
    log "STEP $name 完成 ($elapsed)"
    return 0
  else
    rc=$?
    log "STEP $name 失败 (rc=$rc), 日志: $log_f — fail-fast 停止"
    return $rc
  fi
}

manifest_add() {  # manifest_add <key> <value> — 追加 JSON 行, 末尾统一由 python 合成
  [ -n "$DRY_RUN" ] && return 0
  echo "$1=$2" >> "$E2E_DIR/manifest.kv"
}

# ---------------- 主流程 ----------------
if [ -z "$DRY_RUN" ]; then
  mkdir -p "$E2E_DIR"
  echo "run_id=$RUN_ID" > "$E2E_DIR/manifest.kv"
  echo "scan_mode=$SCAN_MODE" >> "$E2E_DIR/manifest.kv"
  echo "duration=$DURATION" >> "$E2E_DIR/manifest.kv"
  echo "loop=$LOOP" >> "$E2E_DIR/manifest.kv"
fi

log "===== 一键式端到端 SDC 流程 (run_id=$RUN_ID) ====="
log "参数: scan-mode=$SCAN_MODE duration=$DURATION loop=$LOOP num-runs=$NUM_RUNS feedback=$FEEDBACK skip-mutation=${SKIP_MUTATION:-no} dry-run=${DRY_RUN:-no}"

log "[preflight] 工具与目录检查"
if [ -z "$DRY_RUN" ]; then
  preflight || exit 1
else
  echo "[dry-run] [preflight] RUNNER=$RUNNER ORCH=$ORCH SNAP_TOOL=$SNAP_TOOL CENTIPEDE=$CENTIPEDE"
fi

# ---- Step 1: 编译种子 (每轮都跑: 演化轮可能新增 seeds/evolved/*.bin 邻近物, 幂等) ----
run_step 01_build_seeds bash scripts/build_seeds.sh

# ---- 步骤 2-5 按轮循环 ----
for round in $(seq 1 "$LOOP"); do
  log "===== 第 $round/$LOOP 轮 ====="
  [ "$LOOP" -gt 1 ] && manifest_add "round_${round}_start" "$(date +%s)"

  # Step 2: 两阶段引导变异
  if [ -n "$SKIP_MUTATION" ] && [ "$round" -eq 1 ]; then
    log "STEP 02_mutation SKIP (--skip-mutation, 直接用现有语料)"
  else
    run_sh 02_mutation "NUM_RUNS=$NUM_RUNS bash scripts/run_guided_mutation.sh --all"
  fi

  # Step 3: 打包 runner 可读语料 (自带 replay 自检)
  run_step 03_build_corpus bash scripts/build_sdc_corpus.sh

  # Step 4: 真机扫描
  if [ "$SCAN_MODE" = "local" ]; then
    # 本机 orchestrator 单进程满核 (不加 --max_cpus 即默认全核; 不开新并行)。
    # timeout 余量 +60s (hw_scan.py 实测口径: 满负载收尾/日志落盘需要余量,
    # 裸 duration 会误杀 rc=124)。
    dur_s=$(_dur_s "$DURATION" 60)
    scan_to=$((dur_s + 60))
    run_sh 04_scan_local \
      "timeout $scan_to '$ORCH' --duration='$DURATION' --runner='$RUNNER' --shard_list_file=output/sdc_shard_list --corpus_metadata_file=output/sdc_corpus_metadata"
  else
    run_sh 04a_deploy "bash scripts/deploy_board.sh --all"
    run_sh 04b_scan_distributed "python3 scripts/distributed_scan.py --duration '$DURATION' $NO_STRESS"
    run_sh 04c_collect "python3 scripts/collect_results.py"
  fi

  # Step 5: 演化反馈
  feedback_mode="$FEEDBACK"
  if [ "$feedback_mode" = "auto" ]; then
    if [ "$SCAN_MODE" = "distributed" ]; then feedback_mode="legacy"
    else feedback_mode="hw"; fi
  fi
  case "$feedback_mode" in
    legacy)
      # 读 output/distributed/results.json (distributed 模式天然产出)
      run_sh 05_feedback_legacy "bash scripts/sdc_evolve.sh"
      ;;
    hw)
      # local 模式: hw_scan 框架路径。先跑 local 设备扫描产 hw_*.json,
      # 再 feedback_loop 三复跑确认 gate。语料取最新打包的单 shard (阶段A)。
      run_sh 05a_hw_scan \
        "python3 tools/sdc_experiment/hw_scan.py --device local --corpus output/sdc_stage_a.corpus --duration $(_dur_s "$DURATION" 60) --max-cpus $(_hw_max_cpus) --exp exp03"
      run_sh 05b_feedback_loop \
        "bash scripts/experiments/feedback_loop.sh output/experiments/exp03 output/sdc_stage_a.corpus"
      ;;
    none)
      log "STEP 05_feedback SKIP (--feedback none)"
      ;;
  esac

  [ "$LOOP" -gt 1 ] && manifest_add "round_${round}_end" "$(date +%s)"
done

# ---------------- 收尾: 合成 manifest.json + 总结 ----------------
if [ -z "$DRY_RUN" ]; then
  python3 - "$E2E_DIR" <<'PYEOF'
import json, sys, os
d = sys.argv[1]
kv = {}
with open(os.path.join(d, "manifest.kv")) as f:
    for line in f:
        if "=" in line:
            k, v = line.rstrip("\n").split("=", 1)
            kv[k] = v
with open(os.path.join(d, "manifest.json"), "w") as f:
    json.dump(kv, f, indent=2, ensure_ascii=False)
print(f"manifest: {d}/manifest.json")
PYEOF
  log "===== 端到端完成 ====="
  log "产物目录: $E2E_DIR (各步日志 + manifest)"
  log "语料: output/sdc_shard_list ($(wc -l < output/sdc_shard_list) shards)"
  if [ "$SCAN_MODE" = "distributed" ] && [ -f output/distributed/results.json ]; then
    total_sdc=$(python3 -c "
import json
r = json.load(open('output/distributed/results.json'))
print(sum(v.get('sdc_hits', 0) for v in r.values()))" 2>/dev/null || echo "?")
    log "分布式扫描总 SDC 命中 (outcome 2/3/4): $total_sdc — 详见 output/distributed/results.json"
  fi
else
  log "===== dry-run 完成 (未执行任何命令) ====="
fi

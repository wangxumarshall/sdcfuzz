#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# sdc_evolve.sh — 演化反馈闭环: 压测 → 分布式检出 → 回灌 → 再压测
#
# 设计概念第四部分"演化反馈闭环"落地:
#   1. 读取 collect_results.py 的 results.json, 检查是否有 SDC 命中
#   2. 若有: 从扫描日志提取触发 SDC 的 Snapshot hash ( Snapshot [hash] failed )
#      → 用 snap_tool get_instructions 提取原始指令 → 回灌 seeds/evolved/ 高权重
#      → 重跑 run_guided_mutation.sh 局部变异放大 → 重新部署分布式扫描
#   3. 若无: 报告当前语料干净, 可增加操作数变异密度或延长扫描
#
# 用法: sdc_evolve.sh [--duration 60s] [--scan-only]
set -euo pipefail
cd "$(dirname "$0")/.."

DURATION="${DURATION:-60s}"
RESULTS=output/distributed/results.json
EVOLVED_SEEDS=seeds/evolved

# 1. 读取 SDC 命中数
if [ ! -f "$RESULTS" ]; then
  echo "无 results.json, 先跑 distributed_scan.py + collect_results.py"; exit 1
fi
total_sdc=$(python3 -c "
import json
r=json.load(open('$RESULTS'))
print(sum(v.get('sdc_hits',0) for v in r.values()))
" 2>/dev/null || echo 0)
echo "=== 演化闭环: 当前 SDC 命中数 = $total_sdc ==="

if [ "$total_sdc" -eq 0 ]; then
  echo "语料干净 (无 SDC 检出)。建议: 增加操作数变异密度 (operand_mutator --max-variants) 或延长扫描。"
  echo "可选: bash scripts/run_guided_mutation.sh --all (重跑阶段B Centipede 探索更多操作数空间)"
  exit 0
fi

# 2. 有 SDC: 提取触发 hash 回灌种子
echo "=== 检出 $total_sdc 个 SDC, 提取触发 snapshot 回灌种子 ==="
mkdir -p "$EVOLVED_SEEDS"
hashes=$(grep -ohE 'Snapshot \[[0-9a-f]+\] failed' output/distributed/logs/*.scan.log 2>/dev/null \
         | grep -oE '[0-9a-f]{20,}' | sort -u || true)
if [ -z "$hashes" ]; then
  echo "WARN: 无法从日志提取 hash (满负载交织日志可能损坏)。回退: 整体语料作为高权重种子。"
  cp output/bin_stage_a/*.bin "$EVOLVED_SEEDS/" 2>/dev/null || true
else
  for h in $hashes; do
    echo "  触发 SDC snapshot: $h"
    # 尝试用 snap_tool 从语料提取该 snapshot 的指令 (若语料含此 hash)
    # snap_tool get_instructions <corpus> --snap_id <hash> 可提取原始指令
    for corpus in output/sdc-corpus.* output/sdc_stage_a.corpus; do
      [ -f "$corpus" ] || continue
      if bazel-bin/tools/snap_tool get_instructions "$corpus" --snap_id="$h" \
          --out="$EVOLVED_SEEDS/${h}.bin" >/dev/null 2>&1; then
        echo "    提取成功 → $EVOLVED_SEEDS/${h}.bin"
        break
      fi
    done
  done
fi

echo "=== 回灌种子数: $(ls $EVOLVED_SEEDS/*.bin 2>/dev/null | wc -l) ==="

# 3. 局部变异放大 (基于已证明有杀伤力的种子)
echo "=== 局部变异放大 (Centipede 基于回灌种子探索邻近操作数空间) ==="
mkdir -p /tmp/centipede_wd_evolve
bazel-bin/external/fuzztest+/centipede/centipede \
  --binary=bazel-bin/proxies/unicorn_aarch64 \
  --workdir=/tmp/centipede_wd_evolve \
  --corpus_from_files="$EVOLVED_SEEDS/" \
  -j=10 --num_runs=20000 2>&1 | tail -10 || true

# 4. 重新打包 + 重新部署分布式扫描
echo "=== 重新打包语料 + 重新部署 ==="
bash scripts/build_sdc_corpus.sh 2>&1 | tail -5
bash scripts/deploy_board.sh --all 2>&1 | tail -4

echo "=== 重新启动分布式扫描 (duration=$DURATION) ==="
if [ -z "${SCAN_ONLY:-}" ]; then
  python3 scripts/distributed_scan.py --duration "$DURATION" 2>&1 | tail -8
  python3 scripts/collect_results.py 2>&1 | tail -6
fi
echo "=== 演化闭环完成 ==="

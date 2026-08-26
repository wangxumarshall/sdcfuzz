#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# build_sdc_corpus.sh — 合并两阶段输入 → runner 可读 Snap 语料
#
# 两阶段输入格式不同, 用不同工具打包:
#   阶段 A (确定性变体 .bin → .pb): snap_tool generate_corpus 直接产 SnapCorp
#     (runner 可读), 单 shard。
#   阶段 B (Centipede corpus.* blob): simple_fix_tool_main 转 sharded SnapCorp。
#   两者都是 SnapCorp 格式 (runner 直接读), 合并 shard_list。
#
# 实测: generate_corpus 输出 runner replay code:1 (OK)。
#       simple_fix_tool 对 Centipede blob corpus 工作 (726→104 有效 snapshot)。
set -euo pipefail
cd "$(dirname "$0")/.."

STAGE_A_BIN=output/bin_stage_a
PB_DIR=output/pb_stage_a
CENT_WORKDIR=/tmp/centipede_wd_guided
RUNNER=/usr/local/bin/reading_runner_main_nolibc
NUM_SHARDS="${NUM_SHARDS:-10}"

mkdir -p output

echo "=== 阶段 A: .bin → .pb → generate_corpus (SnapCorp, runner 可读) ==="
mkdir -p "$PB_DIR"
pb_count=0
if [ -d "$STAGE_A_BIN" ]; then
  for bin in "$STAGE_A_BIN"/*.bin; do
    [ -e "$bin" ] || continue
    name=$(basename "$bin" .bin)
    if bazel-bin/tools/snap_tool --raw --runner="$RUNNER" --out="$PB_DIR/${name}.pb" make "$bin" >/dev/null 2>&1; then
      pb_count=$((pb_count+1))
    fi
  done
fi
echo "  阶段 A .pb 数: $pb_count"

STAGE_A_CORPUS=output/sdc_stage_a.corpus
if [ "$pb_count" -gt 0 ]; then
  bazel-bin/tools/snap_tool --target_platform=arm-neoverse-n1 \
    generate_corpus "$PB_DIR"/*.pb --out="$STAGE_A_CORPUS" >/dev/null 2>&1
  echo "  阶段 A corpus: $STAGE_A_CORPUS ($(stat -c%s "$STAGE_A_CORPUS") bytes)"
fi

echo "=== 阶段 B: Centipede corpus.* → simple_fix_tool (sharded SnapCorp) ==="
STAGE_B_PREFIX=output/sdc_stage_b
has_b=0
if ls "$CENT_WORKDIR"/corpus.* >/dev/null 2>&1; then
  bazel-bin/tools/simple_fix_tool_main \
    --num_output_shards="$NUM_SHARDS" \
    --output_path_prefix="$(pwd)/$STAGE_B_PREFIX" \
    --runner="$RUNNER" \
    "$CENT_WORKDIR"/corpus.* 2>&1 | tail -5
  has_b=1
  echo "  阶段 B shards: $(ls "$STAGE_B_PREFIX".* 2>/dev/null | wc -l)"
fi

echo "=== 合并 shard_list + metadata ==="
SHARD_LIST=output/sdc_shard_list
METADATA=output/sdc_corpus_metadata
: > "$SHARD_LIST"
[ -f "$STAGE_A_CORPUS" ] && echo "$(pwd)/$STAGE_A_CORPUS" >> "$SHARD_LIST"
if [ "$has_b" -eq 1 ]; then
  for s in "$STAGE_B_PREFIX".*; do [ -e "$s" ] && echo "$(pwd)/$s" >> "$SHARD_LIST"; done
fi
echo "version: \"local_corpus\"" > "$METADATA"

echo "=== 验证: 阶段 A corpus replay ==="
if [ -f "$STAGE_A_CORPUS" ]; then
  r=$(timeout 5 bazel-bin/runner/reading_runner_main_nolibc --num_iterations=20 "$STAGE_A_CORPUS" 2>/dev/null | grep -o 'code:[0-9]' | head -1)
  echo "  $STAGE_A_CORPUS → $r (code:1 = OK)"
fi

echo "=== SDC 语料打包完成 ==="
echo "  shard_list: $SHARD_LIST ($(wc -l < "$SHARD_LIST") shards)"
echo "  metadata: $METADATA"

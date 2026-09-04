#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# run_guided_mutation.sh — 两阶段操作数空间引导变异
#
# 设计概念落地（"下限保覆盖 + 上限靠激发"）:
#   阶段 A (确定性, 保覆盖下限): 操作数字典对模板可变异槽做笛卡尔积替换,
#     生成 N 个变体 .bin, 直接经 snap_tool --raw make 转 Snapshot。
#     覆盖率下限由此保证——系统性遍历操作数组合, 非随机。
#   阶段 B (探索式, 提检出上限): 以全部模板 .bin 为 centipede --corpus_from_files
#     种子, Centipede 变异器在模板骨架上进一步探索操作数/指令组合。
#     功能检出率上限由此提升。
#   两阶段 .bin 合并 → build_sdc_corpus.sh 打包。
#
# 用法: run_guided_mutation.sh [--stage-a|--stage-b|--all] [--num_runs N]
set -euo pipefail
cd "$(dirname "$0")/.."

STAGE="${1:---all}"
NUM_RUNS="${NUM_RUNS:-50000}"
MUTATOR=tools/sdc_mutator/operand_mutator.py
SEED_DIR=seeds
VAR_DIR=output/variants      # 阶段 A 变体
BIN_DIR_A=output/bin_stage_a # 阶段 A 编译后 .bin
CENT_WORKDIR=/tmp/centipede_wd_guided

mkdir -p "$VAR_DIR" "$BIN_DIR_A"

run_stage_a() {
  echo "=== 阶段 A: 确定性操作数字典笛卡尔积变异 (保覆盖下限) ==="
  # 对所有带 // MUT: 标记的模板生成变体
  total=0
  for src in "$SEED_DIR"/*.S; do
    if grep -q '// MUT:' "$src"; then
      n=$(python3 "$MUTATOR" "$src" "$VAR_DIR" 2>&1 | grep -oP 'Generated \K\d+')
      echo "  $(basename "$src"): $n variants"
      total=$((total+n))
    fi
  done
  echo "  阶段 A 变体总数: $total"
  # 编译变体为 .bin
  echo "  编译变体..."
  for v in "$VAR_DIR"/*.S; do
    [ -e "$v" ] || continue
    name=$(basename "$v" .S)
    as -I "$SEED_DIR" -o /tmp/${name}.o "$v" 2>/dev/null && \
      objcopy -O binary -j .text /tmp/${name}.o "$BIN_DIR_A/${name}.bin" || true
  done
  # 加入原始模板 .bin (无 MUT 标记的也算种子)
  cp "$SEED_DIR"/bin/*.bin "$BIN_DIR_A"/ 2>/dev/null || true
  echo "  阶段 A .bin 数: $(ls "$BIN_DIR_A"/*.bin 2>/dev/null | wc -l)"
}

run_stage_b() {
  echo "=== 阶段 B: Centipede 引导式探索 (提检出上限) ==="
  local bin_dir="$BIN_DIR_A"
  [ -d "$bin_dir" ] || bin_dir="$SEED_DIR/bin"
  rm -rf "$CENT_WORKDIR"; mkdir -p "$CENT_WORKDIR"
  # Centipede 以模板 .bin 为种子做真实 fuzzing。
  # 修复 (2026-09-04 全量 e2e 验证发现): 原用 --corpus_from_files, 该 flag 是
  # "Export a corpus ... into the sharded remote corpus" 的纯导出操作 —
  # strace 实证 0 次 fuzz 进程 fork (execve 总数=1, 即 centipede 自身),
  # 50000 runs 2 秒"完成"实为静默空转, corpus.* 只是种子原样分片。
  # 正确 flag 是 --corpus_dir (启动时导入 + while fuzzing 新元素写回)。
  # 实证: --corpus_dir 2000 runs 真实执行 (end-fuzz: ft 25712, corp 205/205,
  # exec/s 160, 10 shards 各 200-271 元素, 从 176 种子增长)。
  # -j=10 限制并发防 MCE (128 核服务器红线)
  bazel-bin/external/fuzztest+/centipede/centipede \
    --binary=bazel-bin/proxies/unicorn_aarch64 \
    --workdir="$CENT_WORKDIR" \
    --corpus_dir="$bin_dir/" \
    -j=10 --num_runs="$NUM_RUNS" 2>&1 | tail -20
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "  WARN: centipede 退出码 $rc (corpus.* 可能不完整, 如实保留)"
  fi
  echo "  阶段 B corpus 数 (shards): $(ls "$CENT_WORKDIR"/corpus.* 2>/dev/null | wc -l)"
}

case "$STAGE" in
  --stage-a) run_stage_a ;;
  --stage-b) run_stage_b ;;
  --all)     run_stage_a; run_stage_b ;;
  *) echo "Usage: $0 [--stage-a|--stage-b|--all]"; exit 1 ;;
esac
echo "=== 引导变异完成 ==="

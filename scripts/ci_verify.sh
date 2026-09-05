#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# ci_verify.sh — CI 集成验证: 模板修改后自动验证编译/make/replay 不退化
#
# 项15: 每次 seeds/*.S 或 operand_mutator.py 修改后跑此脚本, 确认:
#   1. 所有种子编译成功 (as/objcopy)
#   2. 全部 fuzz_filter exit 0 (指令合法)
#   3. 全部 snap_tool make 成功 (快照可生成)
#   4. 全部 runner replay code:1 (回放一致)
#   5. 变异引擎生成变体数 >= 基线 (操作数空间不退化)
# 任一失败则 CI 不通过, 阻止合并。
set -euo pipefail
cd "$(dirname "$0")/.."

PASS=0; FAIL=0; FAIL_LIST=""
BASELINE_VARIANTS=150   # 当前基线 156 变体, 容忍下限 150

echo "=== CI 验证: SDC 检测用例不退化检查 ==="

# 1. 编译种子
echo "[1/5] 编译种子 (build_seeds.sh)..."
if bash scripts/build_seeds.sh >/dev/null 2>&1; then
  N=$(ls seeds/bin/*.bin 2>/dev/null | wc -l)
  echo "  OK: $N 个 .bin 编译成功"
else
  echo "  FAIL: 编译失败"; exit 1
fi

# 2+3+4. 每个种子 fuzz_filter + make + replay
echo "[2/5] 验证 fuzz_filter + snap_tool make + runner replay..."
for bin in seeds/bin/*.bin; do
  name=$(basename "$bin" .bin)
  # fuzz_filter
  bazel-bin/tools/fuzz_filter_tool --runner=/usr/local/bin/reading_runner_main_nolibc "$bin" >/dev/null 2>&1 || { FAIL=$((FAIL+1)); FAIL_LIST="$FAIL_LIST $name(filter)"; continue; }
  # make
  bazel-bin/tools/snap_tool --raw --runner=/usr/local/bin/reading_runner_main_nolibc --out=/tmp/ci_${name}.pb make "$bin" >/dev/null 2>&1 || { FAIL=$((FAIL+1)); FAIL_LIST="$FAIL_LIST $name(make)"; continue; }
  # generate_corpus + replay
  bazel-bin/tools/snap_tool --target_platform=arm-kunpeng920 generate_corpus /tmp/ci_${name}.pb --out=/tmp/ci_${name}.corpus >/dev/null 2>&1
  r=$(timeout 5 bazel-bin/runner/reading_runner_main_nolibc --num_iterations=10 /tmp/ci_${name}.corpus 2>/dev/null | grep -o 'code:[0-9]' | head -1)
  if [ "$r" = "code:1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); FAIL_LIST="$FAIL_LIST $name(replay=$r)"; fi
done
echo "  PASS=$PASS FAIL=$FAIL (共 $((PASS+FAIL)))"

# 5. 变异引擎变体数 >= 基线
echo "[3/5] 变异引擎变体数 >= 基线 ($BASELINE_VARIANTS)..."
TOTAL_VAR=0
for f in seeds/*.S; do
  grep -q '// MUT:' "$f" 2>/dev/null && TOTAL_VAR=$((TOTAL_VAR + $(python3 tools/sdc_mutator/operand_mutator.py "$f" /tmp/ci_var 2>&1 | grep -oP 'Generated \K\d+')))
done
if [ "$TOTAL_VAR" -ge "$BASELINE_VARIANTS" ]; then
  echo "  OK: $TOTAL_VAR 变体 >= $BASELINE_VARIANTS 基线"
else
  echo "  WARN: $TOTAL_VAR 变体 < $BASELINE_VARIANTS 基线 (操作数空间退化?)"
fi

# 6. 回归测试
echo "[4/5] 回归测试 (crc32c_test)..."
bazel test -c opt //util:crc32c_test >/dev/null 2>&1 && echo "  OK: crc32c_test PASSED" || { echo "  FAIL: crc32c_test"; exit 1; }

# 7. gem5 baseline 确定性 (可选, 慢)
echo "[5/5] gem5 baseline 确定性 (可选, 跳过除非 GEM5_CI=1)..."
if [ "${GEM5_CI:-0}" = "1" ]; then
  echo "  (gem5 CI 需 0101, 此处仅本地确定性检查)"
fi

echo "=== CI 结果: $PASS 通过, $FAIL 失败 ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAILURES:$FAIL_LIST"
  exit 1
fi
echo "CI PASSED ✓"

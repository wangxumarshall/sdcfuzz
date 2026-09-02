#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# scripts/experiments/feedback_loop.sh — 反馈迭代闭环编排 (E4 延伸)
# 用法: bash scripts/experiments/feedback_loop.sh <exp_dir> <corpus_dir>
#
# 流程: feedback.py 提取 hw_*.json 的 SDC 命中 → 无命中: 空转结束 (健康硅片
# 预期); 有命中: 回灌种子 + 变异放大 + 提示重扫描 (迭代闭环)。
#
# 已核对的下游脚本真实接口 (2026/09/02, 与 brief 原文的差异如实注明):
#   - scripts/sdc_evolve.sh 不解析任何命令行 flag (用法注释里的 --scan-only
#     未实现), 扫描跳过只认环境变量 SCAN_ONLY=1 → 此处用
#     `SCAN_ONLY=1 bash scripts/sdc_evolve.sh` 而非 `--scan-only`。
#     它读的是 legacy 分布式管线 output/distributed/results.json (非本框架
#     hw_*.json), 回灌语义一致, 仅作种子回灌的 best-effort 调用。
#   - scripts/run_guided_mutation.sh --all 是真实接口 (STAGE="${1:---all}"),
#     内部 -j=10 已遵守 MCE 红线; NUM_RUNS 可环境变量覆盖。
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP_DIR="${1:?需要实验目录}"; CORPUS="${2:?需要语料目录}"

python3 tools/sdc_experiment/feedback.py --exp-dir "$EXP_DIR" --corpus "$CORPUS"

# 有确认命中时: 回灌 + 变异放大 + 再扫描 (sdc_evolve.sh 语义, 编排到本框架)
TOTAL_HITS=$(python3 -c "
import json
rep = json.load(open('output/experiments/feedback/hits.json'))
print(rep['total_hits'])
")
if [ "$TOTAL_HITS" -gt 0 ]; then
  echo "=== 有 $TOTAL_HITS 个命中, 进入回灌-变异-再扫描迭代 ==="
  # 1. 提取命中指令回灌 seeds/evolved/ (sdc_evolve.sh 已实现该逻辑, 直接调用;
  #    真实接口: 环境变量 SCAN_ONLY=1 跳过其末尾的分布式重扫描)
  SCAN_ONLY=1 bash scripts/sdc_evolve.sh || true
  # 2. 变异放大 (真实接口: 位置参数 --all; MCE 红线 -j=10 脚本内部已限)
  bash scripts/run_guided_mutation.sh --all || true
  echo "=== 迭代后语料重新生成 corpus, 手动触发 exp04 重扫描 ==="
else
  echo "无命中, 闭环结束 (健康硅片预期)"
fi

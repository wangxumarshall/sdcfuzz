#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# scripts/experiments/feedback_loop.sh — 反馈迭代闭环编排 (E4 延伸)
# 用法: bash scripts/experiments/feedback_loop.sh <exp_dir> <corpus_dir>
#
# 流程 (fix round 1 实化后的强制顺序):
#   1. feedback.py: 提取 hw_*.json 的 SDC 命中 → 无命中: 空转结束 (健康硅片
#      预期);
#   2. 有命中: feedback.py 内部强制 replay-confirm gate — 每命中 .pb 先
#      generate_corpus 打包成 runner 可读语料 (exp03 已验证管线), 再复跑 3 次,
#      只有 reproduced==3 的确认命中回灌 seeds/evolved/<hash>.bin (直接回灌,
#      不再依赖 legacy sdc_evolve.sh); transient/不可复现/quarantine 如实
#      标注且不回灌 (诚实红线: 不可复现的不放大);
#   3. 有确认回灌时: 变异放大 (run_guided_mutation.sh --all 真实位置参数,
#      内部 -j=10 遵守 MCE 红线) + 提示重扫描。
#
# 已核对的下游脚本真实接口 (与原 brief 的差异如实注明):
#   - legacy scripts/sdc_evolve.sh 读 output/distributed/results.json (legacy
#     分布式管线, 永远看不到本框架 hw_*.json 的命中 — 回灌对它是死路), 且不
#     解析任何命令行 flag (用法注释里的 --scan-only 未实现, 只认 SCAN_ONLY=1
#     环境变量)。故本框架回灌走 feedback.py 直接路径 (reseed); sdc_evolve.sh
#     仅在有确认命中后作为附带调用保留 (其自身读 legacy results.json)。
#   - scripts/run_guided_mutation.sh --all 是真实接口 (STAGE="${1:---all}")。
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP_DIR="${1:?需要实验目录}"; CORPUS="${2:?需要语料目录}"

# Step 1+2: 提取 + (有命中时) 打包复跑三连 gate + 直接回灌 — 全在 feedback.py
python3 tools/sdc_experiment/feedback.py --exp-dir "$EXP_DIR" --corpus "$CORPUS"

TOTAL_HITS=$(python3 -c "
import json
rep = json.load(open('output/experiments/feedback/hits.json'))
print(rep['total_hits'])
")
CONFIRMED=$(python3 -c "
import json
rep = json.load(open('output/experiments/feedback/hits.json'))
print(rep.get('confirmed_hits', 0))
")
RESEEDED=$(python3 -c "
import json
rep = json.load(open('output/experiments/feedback/hits.json'))
print(len(rep.get('reseeded', [])))
")

if [ "$TOTAL_HITS" -gt 0 ]; then
  echo "=== 命中 $TOTAL_HITS 条, 复跑确认 $CONFIRMED 条, 回灌 $RESEEDED 条 (seeds/evolved/) ==="
  if [ "$CONFIRMED" -eq 0 ]; then
    echo "全部命中未通过三复跑确认 (transient/not-reproduced) — 不回灌不放大 (诚实红线)"
    exit 0
  fi
  # 附带: legacy 演化闭环 (读 legacy results.json, best-effort; 主回灌已在上面完成)
  SCAN_ONLY=1 bash scripts/sdc_evolve.sh || true
  # 变异放大 (真实接口: 位置参数 --all; MCE 红线 -j=10 脚本内部已限)
  bash scripts/run_guided_mutation.sh --all || true
  echo "=== 迭代后语料重新生成 corpus, 手动触发 exp04 重扫描 ==="
else
  echo "无命中, 闭环结束 (健康硅片预期)"
fi

#!/bin/bash
# scripts/experiments/exp01_baseline_repro.sh — E1: 基线复现 (A/B bit-flip 各100次, 本机 gem5)
# 判定(预注册): B/A diverge率 ≥ 1.5× 且方向与 F3 (B=8.0% > A=3.9%) 一致
# 注: --jobs 3 并行 (控制器裁决, MCE 红线 ≤4); fault-clock 在 dispatch 前按 run 序
#     由 Random(seed) 抽完, 每 run rng-seed=seed+i, 并行不改变 run 参数 (冒烟已验证)。
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp01-baseline-repro
for G in A B; do
  python3 tools/sdc_experiment/sim_sweep.py --group $G \
      --mode bit --runs 100 --seed 42 --exp $EXP --jobs 3
done
python3 - "$EXP" <<'EOF'
import json, sys, os
sys.path.insert(0, ".")
from tools.sdc_experiment.sim_sweep import fisher_exact
exp = sys.argv[1]
A = json.load(open(f"output/experiments/{exp}/sim_A_bit.json"))
B = json.load(open(f"output/experiments/{exp}/sim_B_bit.json"))
ratio = B["diverge_rate"] / A["diverge_rate"] if A["diverge_rate"] else float("inf")
_, p = fisher_exact(B["clean_diverge"], B["n"] - B["clean_diverge"],
                    A["clean_diverge"], A["n"] - A["clean_diverge"])
verdict = "REPRODUCED" if ratio >= 1.5 else "NOT_REPRODUCED(诚实记录)"
summary = {"A": A, "B": B, "B_over_A_ratio": round(ratio, 3),
           "fisher_p": round(p, 5), "verdict": verdict,
           "note": "gem5 O3 model, not TSV110 RTL; 对照 F3: A=3.9%, B=8.0%"}
json.dump(summary, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=2))
EOF

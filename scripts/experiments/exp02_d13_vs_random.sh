#!/bin/bash
# scripts/experiments/exp02_d13_vs_random.sh — E2: D13 vs B (bit+struct 各100次, 本机 gem5)
# 判定(预注册): D13/B ≥ 1.5× 记为击败; 对照 F4 (bit 3.00×, struct 7.79×)
# 注: --runs 100 (控制器裁决按计划风险登记降档: "降 --runs 100, 判定阈值不变");
#     --jobs 3 并行 (MCE 红线 ≤4); 并行不改变 run 参数 (冒烟已验证)。
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp02-d13-vs-random
for MODE in bit struct; do
  for G in B D13; do
    python3 tools/sdc_experiment/sim_sweep.py --group $G \
        --mode $MODE --runs 100 --seed 42 --exp $EXP --jobs 3
  done
done
python3 - "$EXP" <<'EOF'
import json, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.sim_sweep import fisher_exact
exp = sys.argv[1]
out = {}
for mode in ["bit", "struct"]:
    B = json.load(open(f"output/experiments/{exp}/sim_B_{mode}.json"))
    D = json.load(open(f"output/experiments/{exp}/sim_D13_{mode}.json"))
    ratio = D["diverge_rate"] / B["diverge_rate"] if B["diverge_rate"] else float("inf")
    _, p = fisher_exact(D["clean_diverge"], D["n"] - D["clean_diverge"],
                        B["clean_diverge"], B["n"] - B["clean_diverge"])
    out[mode] = {"B": B, "D13": D, "D_over_B": round(ratio, 3), "fisher_p": round(p, 5),
                 "verdict": "BEAT" if ratio >= 1.5 and p < 0.05 else
                            ("MARGINAL" if ratio >= 1.5 else "NOT_BEAT(诚实记录)")}
json.dump(out, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(out, ensure_ascii=False, indent=2))
EOF

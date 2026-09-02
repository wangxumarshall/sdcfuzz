#!/bin/bash
# scripts/experiments/exp05_crosslayer.sh — E5: Sim→HW 组粒度关联
# Sim面: A/B/D13 各 30 次 bit-flip gem5 sweep (本机 gem5, --jobs 3)
#        + 12 个模板组的 Unicorn T(di/dt) 代理指标 (gem5 跑 ELF 跑不了裸指令 bin,
#          诚实边界: 模板组 sim 指标是代理, 输出中 proxy 字段标注)
# HW面: 每个模板组语料单独 10min 本机扫描 — 复用 hw_scan
#        (实测修正: snap_tool make 出的 .pb 是 Snapshot proto, orchestrator 读
#         SnapCorp 语料格式 (bad magic 错误实测) → 每组需再过
#         snap_tool generate_corpus 转成单 shard corpus, 与 E3/exp03 管线一致)
# 关联: Spearman + 置换检验 (≥10 组); verdict 如实记录
# MCE 红线: hw max_cpus=8, gem5 jobs=3 (合计 ~11 核, 同 exp02/exp03 并存先例)
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp05-crosslayer
SNAP_TOOL=/usr/local/bin/snap_tool
RUNNER=/usr/local/bin/reading_runner_main_nolibc
DUR="${DUR:-600}"
MAXCPUS="${MAXCPUS:-8}"
SIMRUNS="${SIMRUNS:-30}"
mkdir -p output/experiments/$EXP

# 组清单: 20 模板中取字典序前 12 个 + A/B/D13 (gem5 组用入仓 gem5_config/workloads)
# 诚实边界: gem5 workload 覆盖 A/B/D13 (入仓); 20 模板的 .bin 无法直接进 gem5
#   (gem5 跑 ELF, 模板是裸指令) → sim 面对模板组用"Unicorn T(di/dt) 值"作代理指标,
#   在输出中用 proxy="unicorn_T" 字段明确标注该代理性质。
python3 - "$EXP" "$SNAP_TOOL" "$RUNNER" "$DUR" "$MAXCPUS" "$SIMRUNS" <<'EOF'
import json, os, subprocess, sys
sys.path.insert(0, ".")
exp = sys.argv[1]
SNAP_TOOL, RUNNER = sys.argv[2], sys.argv[3]
DUR, MAXCPUS, SIMRUNS = int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])

# ---- Sim 面: A/B/D13 各 30 次 bit-flip (本机 gem5, jobs=3 并行, MCE 红线≤4) ----
from tools.sdc_experiment.experiment_config import default_config
from tools.sdc_experiment.sim_sweep import run_group
cfg = default_config(exp)
sim_rows = []
for grp in ["A", "B", "D13"]:
    r = run_group(grp, "bit", SIMRUNS, seed=7, cfg=cfg, jobs=3)
    sim_rows.append({"group": grp, "sim_diverge_rate": r["diverge_rate"],
                     "sim_masked_rate": round(r["masked"] / max(1, r["n"]), 4)})
    print("sim:", sim_rows[-1], flush=True)

# ---- Sim 面: 模板组 Unicorn T 值 (进化引擎代理指标, proxy 字段注明) ----
# run_once(regs_init) 返回 5 元组 (final_vals, T, M, E, score);
# regs_init 键 = int 0..4 (REG_MAP 键为 int, evolution_engine.py:32 实测)。
sys.path.insert(0, "tools/sdc_mutator")
from evolution_engine import EvolutionEngine
import glob
for b in sorted(glob.glob("seeds/bin/*.bin"))[:12]:
    code = open(b, "rb").read()[:256]
    try:
        eng = EvolutionEngine(code)
        _, T, M, E, _ = eng.run_once({i: 0x1234567890ABCDEF for i in range(5)})
        sim_rows.append({"group": os.path.basename(b)[:-4],
                         "sim_diverge_rate": round(T / 200, 4),   # 归一化代理 (计划指定)
                         "sim_masked_rate": 0.0, "proxy": "unicorn_T"})
    except Exception as e:
        print(f"skip {b}: {e}", flush=True)
json.dump(sim_rows, open(f"output/experiments/{exp}/sim_rows.json", "w"),
          indent=2, ensure_ascii=False)

# ---- HW 面: 每模板组单独 10min 本机扫描 ----
# 管线 (与 exp03 一致, brief Step5 单 .pb 直扫实测 bad magic 失败后的修正):
#   .bin → snap_tool make → .pb (Snapshot) → snap_tool generate_corpus → 单 shard
#   SnapCorp 语料 → hw_scan (shard_list 单行, E4 已验证该路径)
from tools.sdc_experiment.devices.local_device import LocalDevice
from tools.sdc_experiment.hw_scan import hw_scan
local = LocalDevice()
hw_rows = []
pb_dir = f"/tmp/sdc_experiment/e5"
os.makedirs(pb_dir, exist_ok=True)
for b in sorted(glob.glob("seeds/bin/*.bin"))[:12]:
    name = os.path.basename(b)[:-4]
    pb = f"{pb_dir}/{name}.pb"
    corpus = f"{pb_dir}/{name}.corpus"
    subprocess.run([SNAP_TOOL, "--raw", f"--runner={RUNNER}",
                    f"--out={pb}", "make", b], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([SNAP_TOOL, "--target_platform=arm-neoverse-n1",
                    "generate_corpus", pb, f"--out={corpus}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    r = hw_scan(local, corpus, duration_s=DUR, max_cpus=MAXCPUS)
    hw_rows.append({"group": name,
                    "hw_runnable_rate": round((r["v1_summary"] or {}).get("play_count", 0)
                                              / max(1, DUR), 4),
                    "hw_runaway_rate": r["runaway_noise"] / DUR,
                    "hw_misbehave_rate": r["misbehave_noise"] / DUR,
                    "hw_sdc": r["sdc_hits"],
                    "play_count": (r["v1_summary"] or {}).get("play_count"),
                    "orch_rc": r["orch_rc"],
                    "total_failed": r["total_failed"]})
    print("hw:", hw_rows[-1], flush=True)
    json.dump(hw_rows, open(f"output/experiments/{exp}/hw_rows.json", "w"),
              indent=2, ensure_ascii=False)

# ---- 关联 (预注册判定: Spearman + 置换 p<0.05; 不事后修改) ----
from tools.sdc_experiment.correlation import analyze
res = analyze(sim_rows, hw_rows)
json.dump({"sim_rows": sim_rows, "hw_rows": hw_rows, "analysis": res},
          open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(res, ensure_ascii=False, indent=2))
EOF

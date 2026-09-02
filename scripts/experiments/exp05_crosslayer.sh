#!/bin/bash
# scripts/experiments/exp05_crosslayer.sh — E5: Sim→HW 组粒度关联
# 用法: bash exp05_crosslayer.sh            # 全量真跑 (~2h: 90 gem5 + 12×10min hw)
#       bash exp05_crosslayer.sh --rederive # 从已归档证据重导 artifacts (幂等, 不重跑)
# Sim面: A/B/D13 各 30 次 bit-flip gem5 sweep (本机 gem5, --jobs 3)
#        + 12 个模板组的 Unicorn T(di/dt) 代理指标 (gem5 跑 ELF 跑不了裸指令 bin,
#          诚实边界: 模板组 sim 指标是代理, 输出中 proxy 字段标注)
# HW面: 每个模板组语料单独 10min 本机扫描 — 复用 hw_scan
#        (实测修正: snap_tool make 出的 .pb 是 Snapshot proto, orchestrator 读
#         SnapCorp 语料格式 (bad magic 错误实测) → 每组需再过
#         snap_tool generate_corpus 转成单 shard corpus, 与 E3/exp03 管线一致)
# 字段语义 (评审修正): hw_throughput_per_s = play_count/DUR 是吞吐, 不是 brief
#        定义的 runnable 率(1−失败率) — v1 汇总无迭代总数, 该率无法从现有证据
#        诚实计算 → 只给吞吐 + hw_failure_count 原始失败数, 不虚构率。
# 关联: Spearman + 置换检验 (≥10 组); verdict 如实记录
# MCE 红线: hw max_cpus=8, gem5 jobs=3 (合计 ~11 核, 同 exp02/exp03 并存先例)
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp05-crosslayer

# --rederive: 不重跑实验, 从已归档原始证据 (12 份 scan log + sim_rows.json)
# 重导 hw_rows.json / summary.json (字段更名 + 注记自含化)。所有计数值从 log
# 重新解析并与真跑记录逐项断言一致 (runaway/misbehave/sdc/failed/play_count);
# 分析块 n/sim_key/hw_key/spearman_rho/permutation_p/verdict 必须与真跑逐项
# 相同, 任一漂移立即失败退出 — 更名只改字段名, 不改任何统计语义。
if [ "${1:-}" = "--rederive" ]; then
python3 - "$EXP" <<'EOF'
import glob, json, sys
sys.path.insert(0, ".")
exp = sys.argv[1]
outdir = f"output/experiments/{exp}"
DUR = 600

from tools.sdc_experiment.hw_scan import parse_log, parse_v1_summary
from tools.sdc_experiment.correlation import analyze

sim_rows = json.load(open(f"{outdir}/sim_rows.json"))
old_rows = json.load(open(f"{outdir}/hw_rows.json"))
old_sum = json.load(open(f"{outdir}/summary.json"))

# 组↔log 映射: 用真跑记录的 play_count 匹配各 log 的 v1 终态汇总行
# (12 组 play_count 全互异: 480..1968; exp03 的 log play=3840 自然落选)。
# c1 (唯一有失败行的组) 另用 log 内 Corpus 标签直接自证。
logs = {}
for lp in glob.glob("output/experiments/hw_scan_logs/local-0103_*.scan.log"):
    t = open(lp, errors="replace").read()
    v1 = parse_v1_summary(t)
    if v1:
        logs[lp] = (t, v1)
by_play = {}
for lp, (t, v1) in logs.items():
    by_play.setdefault(v1["play_count"], []).append(lp)
for r in old_rows:
    pc = r["play_count"]
    cands = by_play.get(pc, [])
    assert len(cands) == 1, f"play_count={pc} 匹配 {len(cands)} 份 log, 无法唯一定位"
    r["_log"] = cands[0]
assert len({r["_log"] for r in old_rows}) == len(old_rows), "log 被多组复用"

c1 = next(r for r in old_rows if r["group"] == "c1_l2_eviction")
assert "Corpus   [c1_l2_eviction.corpus]" in open(c1["_log"], errors="replace").read(), \
    "c1 log Corpus 标签不符"

# 重导: 计数值全部从 log 重解析, 与真跑记录逐项断言 (证明更名未改语义)
new_rows = []
for r in old_rows:
    t, v1 = logs[r["_log"]]
    p = parse_log(t)
    assert p["runaway_noise"] / DUR == r["hw_runaway_rate"], f'{r["group"]} runaway 不符'
    assert p["misbehave_noise"] / DUR == r["hw_misbehave_rate"], f'{r["group"]} misbehave 不符'
    assert p["sdc_hits"] == r["hw_sdc"], f'{r["group"]} sdc 不符'
    old_failed = r.get("hw_failure_count", r.get("total_failed"))
    assert p["total_failed"] == old_failed, f'{r["group"]} failure count 不符'
    assert v1["play_count"] == r["play_count"], f'{r["group"]} play_count 不符'
    new_rows.append({"group": r["group"],
                     "hw_throughput_per_s": round(r["play_count"] / DUR, 4),
                     "hw_runaway_rate": p["runaway_noise"] / DUR,
                     "hw_misbehave_rate": p["misbehave_noise"] / DUR,
                     "hw_sdc": p["sdc_hits"],
                     "play_count": v1["play_count"],
                     "hw_failure_count": p["total_failed"],
                     # orch_rc 由 timeout 外壳 echo ORCH_RC, 不落 scan.log →
                     # 沿用真跑记录; log 含完整 v1 终态汇总行即扫描完整结束旁证
                     "orch_rc": r["orch_rc"]})

res = analyze(sim_rows, new_rows)
res["note"] = ("12 组 sim 值为 Unicorn T 代理指标(T/200, 计划指定), 非 gem5 diverge 率; "
               + res.get("note", ""))
old_a = old_sum["analysis"]
for k in ("n", "sim_key", "hw_key", "spearman_rho", "permutation_p", "verdict"):
    assert res[k] == old_a[k], f"analysis.{k} 漂移: {res[k]} != {old_a[k]}"

json.dump(new_rows, open(f"{outdir}/hw_rows.json", "w"), indent=2, ensure_ascii=False)
json.dump({"sim_rows": sim_rows, "hw_rows": new_rows, "analysis": res},
          open(f"{outdir}/summary.json", "w"), indent=2, ensure_ascii=False)
print("rederive OK: analysis unchanged:", json.dumps(
    {k: res[k] for k in ("n", "spearman_rho", "permutation_p", "verdict")},
    ensure_ascii=False))
EOF
exit 0
fi
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
                    "hw_throughput_per_s": round((r["v1_summary"] or {}).get("play_count", 0)
                                                 / max(1, DUR), 4),
                    "hw_runaway_rate": r["runaway_noise"] / DUR,
                    "hw_misbehave_rate": r["misbehave_noise"] / DUR,
                    "hw_sdc": r["sdc_hits"],
                    "play_count": (r["v1_summary"] or {}).get("play_count"),
                    "hw_failure_count": r["total_failed"],
                    "orch_rc": r["orch_rc"]})
    print("hw:", hw_rows[-1], flush=True)
    json.dump(hw_rows, open(f"output/experiments/{exp}/hw_rows.json", "w"),
              indent=2, ensure_ascii=False)

# ---- 关联 (预注册判定: Spearman + 置换 p<0.05; 不事后修改) ----
from tools.sdc_experiment.correlation import analyze
res = analyze(sim_rows, hw_rows)
# 自含化注记: artifact 单独被读时也能看到代理混用边界
res["note"] = ("12 组 sim 值为 Unicorn T 代理指标(T/200, 计划指定), 非 gem5 diverge 率; "
               + res.get("note", ""))
json.dump({"sim_rows": sim_rows, "hw_rows": hw_rows, "analysis": res},
          open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(res, ensure_ascii=False, indent=2))
EOF

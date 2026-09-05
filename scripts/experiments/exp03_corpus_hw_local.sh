#!/bin/bash
# scripts/experiments/exp03_corpus_hw_local.sh — E3: 模板语料(seeds/bin/*.bin 全量,
#       数量动态, 实测 20)在本机(0103)真机验证
# 前置: seeds/bin/*.bin 存在 (生成步骤内联, 管线依据 memory
#       sdc-snapshot-from-raw-insns-pipeline + scripts/build_sdc_corpus.sh 实测 flag)
# 判定: 扫描完成无 crash (orch_rc=0); SDC=0(健康硅片预期) 或 SDC 命中有 hash 证据;
#       噪声全分类 (sdc+runaway+misbehave == total_failed) 且 v1 交叉校验 match
#       (match=false → CLASSIFICATION_INCOMPLETE, 不容自相矛盾)
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp03-corpus-hw-local
SNAP_TOOL=/usr/local/bin/snap_tool
RUNNER=/usr/local/bin/reading_runner_main_nolibc
DUR="${DUR:-1800}"
MAXCPUS="${MAXCPUS:-8}"
mkdir -p output/experiments/$EXP/pb

# 1. 全部模板 .bin → snapshot .pb (数量动态 $N, 实测 flag: --raw --runner= --out=)
N=0
for BIN in seeds/bin/*.bin; do
  NAME=$(basename "$BIN" .bin)
  "$SNAP_TOOL" --raw --runner="$RUNNER" \
      --out=output/experiments/$EXP/pb/$NAME.pb make "$BIN" >/dev/null 2>&1
  N=$((N+1))
done
echo "[1/4] $N 个模板 .pb 生成完成"

# 2. snapshot → relocatable corpus (实测 flag: generate_corpus ... --out=)
"$SNAP_TOOL" --target_platform=arm-kunpeng920 \
    generate_corpus output/experiments/$EXP/pb/*.pb \
    --out=output/experiments/$EXP/corpus >/dev/null 2>&1
echo "[2/4] corpus 生成: output/experiments/$EXP/corpus ($(stat -c%s output/experiments/$EXP/corpus) bytes)"

# 2b. 回放冒烟 (code:1 = OK, 同 build_sdc_corpus.sh 验证步骤)
R=$(timeout 20 "$RUNNER" --num_iterations=20 output/experiments/$EXP/corpus 2>/dev/null | grep -o 'code:[0-9]' | head -1)
echo "[2b] 语料回放冒烟: $R (code:1 = OK)"
[ "$R" = "code:1" ] || { echo "FAIL: 语料回放不是 code:1"; exit 1; }

# 3. 本机真机扫描 (MCE 红线: max_cpus=8; 3 个 gem5 后台作业并存, 合计 ~11 核, 安全)
echo "[3/4] orchestrator 扫描 ${DUR}s, max_cpus=$MAXCPUS ..."
python3 tools/sdc_experiment/hw_scan.py --device local \
    --corpus output/experiments/$EXP/corpus --duration "$DUR" --max-cpus "$MAXCPUS" --exp $EXP

# 4. 汇总判定
python3 - "$EXP" <<'EOF'
import json, sys, glob
exp = sys.argv[1]
f = sorted(glob.glob(f"output/experiments/{exp}/hw_local-0103.json"))[-1]
r = json.load(open(f))
ok = r.get("orch_rc") == 0
v1 = r.get("v1_summary") or {}
# v1 交叉校验 (两个独立来源: ResultCollector 内存计数 vs 日志文本解析):
#   issues_detected 默认不含 runaway (report_runaways_as_errors=false 时
#   num_runaway_snapshots++ 后提前 return, 不进 num_failed_snapshots) →
#   v1.issues_detected == total_failed - runaway_noise;
#   v1.runaway_count  == runaway_noise。
#   若 8 路并发下日志行交织损坏了 parse 计数, 此处 mismatch 会如实暴露。
parse_failed_minus_runaway = r["total_failed"] - r["runaway_noise"]
v1_side = v1.get("issues_detected")
v1_runaway = v1.get("runaway_count")
cross_ok = None
if v1_side is not None:
    cross_ok = (v1_side == parse_failed_minus_runaway and v1_runaway == r["runaway_noise"])
# v1 交叉校验 gate verdict: match=false (两来源矛盾, 如满负载交织损坏 parse 计数)
#   → 判 CLASSIFICATION_INCOMPLETE; match=true 或 v1 不可得 (None, 无汇总行) 不否决。
ok = ok and (cross_ok is not False)
ok = ok and (r["sdc_hits"] + r["runaway_noise"] + r["misbehave_noise"] + r["sigsegv_noise"]) == r["total_failed"] + r["sigsegv_noise"]
summary = {
    "result": r,
    "noise_fully_classified": ok,
    "v1_cross_check": {"parse_failed_minus_runaway": parse_failed_minus_runaway,
                       "v1_issues_detected": v1_side,
                       "parse_runaway": r["runaway_noise"],
                       "v1_runaway_count": v1_runaway,
                       "match": cross_ok},
    "verdict": "HW_SCAN_OK" if ok else "CLASSIFICATION_INCOMPLETE",
}
if r.get("sdc_hits", 0) > 0:
    print(f"!!! SDC 命中 {r['sdc_hits']} 个: {r['sdc_details']} — 需逐个 hash 复查 (复跑确认非偶发)")
json.dump(summary, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=2))
EOF

#!/bin/bash
# scripts/experiments/exp04_remote_device.sh — E4: 远程设备全链路验证
# 用法: bash exp04_remote_device.sh --name board-X --host <IP> --port 22 \
#         --user root --password-env SDC_PASSWORD --duration 1800 --max-cpus 8
# 全链路: 注册→probe→deploy(工具+E3语料)→远程语料回放冒烟→hw_scan→结果回收→summary
# 判定 (链路完整性优先, gate 与 E3/afc7819 同构): 先验 error/orch_rc=0/噪声全分类/
#       v1交叉校验, 任一不过 → REMOTE_CHAIN_BROKEN(reason) 退出 1 —— SDC 命中不掩盖
#       断链 (如 timeout 击杀 orch_rc=124 前已 log 出的 SDC 行); 链路完好才分:
#       SDC=0 → REMOTE_CHAIN_OK; SDC>0 → REMOTE_SDC_N_RECHECK (退出 0, 真发现需复查)。
# 凭据红线: 密码只经 --password-env 指名的环境变量或设备清单 (gitignored), 绝不落本文件。
# MCE 红线: --max-cpus 默认 8 (hw_scan 侧另有 MAX_CPUS_HARD_LIMIT=64 硬限兜底)。
set -euo pipefail
cd "$(dirname "$0")/../.."

NAME="" HOST="" PORT=22 USER=root PWENV=SDC_PASSWORD DUR=1800 CPUS=8
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="${2:?}"; shift 2;;
    --host) HOST="${2:?}"; shift 2;;
    --port) PORT="${2:?}"; shift 2;;
    --user) USER="${2:?}"; shift 2;;
    --password-env) PWENV="${2:?}"; shift 2;;
    --duration) DUR="${2:?}"; shift 2;;
    --max-cpus) CPUS="${2:?}"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[[ -z "$NAME" || -z "$HOST" ]] && { echo "need --name --host"; exit 1; }
# 密码前置检查 (不回显): 缺密码时注册步骤会静默失败, 链路却断在 probe (KeyError),
# 报错位置远离根因 → 提前按 $PWENV 断链
[[ -n "${!PWENV:-}" ]] || { echo "FAIL: 未设 \$$PWENV 环境变量 (设备密码)"; exit 1; }

EXP=exp04-remote-$NAME
OUT=output/experiments/$EXP
CORPUS_LOCAL=output/experiments/exp03-corpus-hw-local/corpus   # E3 产物 (brief 指定)
mkdir -p "$OUT"

# 0. 前置: E3 语料必须存在 (链路最早的失败要最早报)
[[ -e "$CORPUS_LOCAL" ]] || { echo "FAIL: E3 语料不存在: $CORPUS_LOCAL (先跑 exp03)"; exit 1; }

# 1. 注册 (幂等: 仅容忍"已注册"这一重复注册情形; 其他注册错误如实断链。
#    密码读 $PWENV 环境变量)
echo "[1/5] register $NAME -> $HOST:$PORT (幂等, 已注册则跳过)"
if ! python3 scripts/register_device.py --name "$NAME" --host "$HOST" --port "$PORT" \
    --user "$USER" --password-env "$PWENV" 2>"$OUT/register.err"; then
  if grep -q "已注册" "$OUT/register.err"; then
    echo "  已注册 (幂等跳过)"
  else
    echo "FAIL: 注册失败 (非重复注册):"; cat "$OUT/register.err"; exit 1
  fi
fi

# 2. probe → probe.json (结构化留档; 不可达即断链)
echo "[2/5] probe $NAME"
python3 - "$NAME" "$OUT" <<'EOF'
import json, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.devices.device_pool import DevicePool
name, out = sys.argv[1], sys.argv[2]
p = DevicePool().load().get(name).probe()
json.dump(p, open(f"{out}/probe.json", "w"), indent=2, ensure_ascii=False)
assert p["reachable"], f"设备不可达: {p}"
print("probe OK:", json.dumps(p, ensure_ascii=False))
EOF

# 3. 部署工具 + 推送 E3 语料; deploy 输出留档 deploy.json, 并逐项 gate:
#    任一工具非 deployed/skip(md5 match) → 断链, 不进入扫描。
#    语料推送真实校验放 3b (md5 往返): deploy.py 的 corpus.ok 走 scp 目录语义
#    (test -d <dir>/<basename>), 对 E3 的单文件语料恒 False (文件落地为
#    <dir>/corpus 文件), 不作为 gate —— 已实测 md5 一致 (8adb709c)。
echo "[3/5] deploy tools + corpus -> remote:$NAME"
python3 tools/sdc_experiment/deploy.py --device "remote:$NAME" \
    --corpus "$CORPUS_LOCAL" > "$OUT/deploy.json"
python3 - "$OUT/deploy.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
bad = {t: s for t, s in r["tools"].items() if s not in ("deployed", "skip(md5 match)")}
assert not bad, f"工具部署失败: {bad}"
print(f"deploy OK: {len(r['tools'])} 工具就绪, corpus -> {r['corpus']['remote']}")
EOF

# 远端语料路径 (与 deploy.py 的推导一致): dirname(tools_dir)/sdc_corpus/<basename>。
# 注意: 不传父目录 (如 /sdc_corpus) —— hw_scan 的目录分支会 glob 父目录下全部普通文件,
# 设备上的历史语料 (0101 上有 sdc_stage_* 等) 会被一并扫入, E4 结果将不可归因。
CORPUS_REMOTE=$(python3 - "$NAME" "$CORPUS_LOCAL" <<'EOF'
import os, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.devices.device_pool import DevicePool
name, local = sys.argv[1], sys.argv[2]
dev = DevicePool().load().get(name)
print(os.path.join(os.path.dirname(dev.tools_dir.rstrip("/")), "sdc_corpus",
                   os.path.basename(local.rstrip("/"))))
EOF
)

# 3b. 远程语料完整性 + 回放冒烟:
#     md5 往返 == deploy 推送的真实校验 (deploy 的 corpus.ok 对文件语料恒 False,
#     见上); 回放 code:1 = OK (proto OK=1, 镜像 exp03 步骤 2b), 传输损坏在此拦截
python3 - "$NAME" "$CORPUS_LOCAL" "$CORPUS_REMOTE" <<'EOF'
import hashlib, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.devices.device_pool import DevicePool
name, local, remote = sys.argv[1], sys.argv[2], sys.argv[3]
dev = DevicePool().load().get(name)
h = hashlib.md5()
with open(local, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
_, out = dev.run(f"md5sum {remote} 2>&1", timeout=60)
# 远端输出混有 profile.d 噪声行, 且 md5 行是 "HASH  path" → 取行首 token 再验 32-hex
# (deploy.py 的裸 32 字符过滤配了 awk '{print $1}', 这里无 awk, 须按 token 解)
remote_md5s = [tok for l in out.splitlines() if l.split() for tok in [l.split()[0]]
               if len(tok) == 32 and all(c in "0123456789abcdef" for c in tok)]
assert h.hexdigest() in remote_md5s, \
    f"语料 md5 不一致: local={h.hexdigest()} remote={remote_md5s} (推送失败/损坏)"
runner = dev.tool_path("reading_runner_main_nolibc")
rc, out = dev.run(f"timeout 30 {runner} --num_iterations=20 {remote} 2>/dev/null "
                  f"| grep -o 'code:[0-9]' | head -1", timeout=60)
lines = [l.strip() for l in out.splitlines() if l.strip()]
assert lines and lines[-1] == "code:1", \
    f"远程语料回放非 code:1 (rc={rc}, 输出尾行={lines[-3:]}): 语料可能传输损坏"
print(f"remote corpus OK: md5 match + replay code:1 ({remote})")
EOF

# 4. 远程扫描 (hw_scan 在设备上组 shard_list/metadata, 跑 orchestrator,
#    拉回并解析 scan.log, 结果落 $OUT/hw_$NAME.json, 日志存档 hw_scan_logs/)
echo "[4/5] hw_scan: device=remote:$NAME corpus=$CORPUS_REMOTE duration=${DUR}s max_cpus=$CPUS"
python3 tools/sdc_experiment/hw_scan.py --device "remote:$NAME" \
    --corpus "$CORPUS_REMOTE" --duration "$DUR" --max-cpus "$CPUS" --exp "$EXP"

# 5. 汇总 (v1 交叉校验 gate 与 E3 判定一致) + 扫描日志归档进实验目录
#    (exp03 先例: hw_scan_logs/ 不入库, 实验目录内 scan.log 入库)
python3 - "$NAME" "$EXP" <<'EOF'
import glob, json, os, shutil, sys
name, exp = sys.argv[1], sys.argv[2]
f = sorted(glob.glob(f"output/experiments/{exp}/hw_{name}*.json"))[-1]
r = json.load(open(f))

arch = r.get("archived_log")
if arch and os.path.exists(arch):
    shutil.copy(arch, f"output/experiments/{exp}/scan.log")

# 判定 gate (与 E3/summary 同构): v1.issues_detected == total_failed - runaway_noise,
# v1.runaway_count == runaway_noise; v1 不可得 (None) 不否决。
v1 = r.get("v1_summary") or {}
parse_fmr = r["total_failed"] - r["runaway_noise"]
cross = None
if v1.get("issues_detected") is not None:
    cross = (v1["issues_detected"] == parse_fmr and
             v1.get("runaway_count") == r["runaway_noise"])
classified = (r["sdc_hits"] + r["runaway_noise"] + r["misbehave_noise"]) == r["total_failed"]

# 链路完整性优先: SDC 分支不得绕过 orch_rc/分类/v1 校验 ——
# orch 挂死被 timeout 击杀 (orch_rc=124) 前已 log 出的 SDC 行, 若先判 sdc_hits
# 会误报 RECHECK(退出0) 并断言"链路通"; 必须先判链路, 断链时如实带上原因。
if r.get("error"):
    verdict = f"REMOTE_CHAIN_BROKEN(hw_scan error: {r['error']})"
elif r.get("orch_rc") != 0:
    verdict = f"REMOTE_CHAIN_BROKEN(orch_rc={r.get('orch_rc')})"
elif not classified:
    verdict = "CLASSIFICATION_INCOMPLETE(noise not fully classified)"
elif cross is False:
    verdict = "CLASSIFICATION_INCOMPLETE(v1 cross-check mismatch)"
elif r["sdc_hits"] > 0:
    verdict = f"REMOTE_SDC_{r['sdc_hits']}_RECHECK"
else:
    verdict = "REMOTE_CHAIN_OK"

summary = {"result": r, "verdict": verdict,
           "noise_fully_classified": classified,
           "v1_cross_check": {"parse_failed_minus_runaway": parse_fmr,
                              "v1_issues_detected": v1.get("issues_detected"),
                              "parse_runaway": r["runaway_noise"],
                              "v1_runaway_count": v1.get("runaway_count"),
                              "match": cross},
           "probe": json.load(open(f"output/experiments/{exp}/probe.json")),
           "deploy": json.load(open(f"output/experiments/{exp}/deploy.json"))}
json.dump(summary, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps({"verdict": verdict, "sdc_hits": r["sdc_hits"],
                  "sdc_details": r.get("sdc_details", []),
                  "orch_rc": r.get("orch_rc"),
                  "v1_summary": r.get("v1_summary")},
                 ensure_ascii=False, indent=2))
# 链路验证失败 (扫描未完成/分类矛盾) → 非零退出;
# SDC 命中 = 链路通 + 真发现 (RECHECK), 不算链路失败。
sys.exit(0 if verdict in ("REMOTE_CHAIN_OK",) or verdict.startswith("REMOTE_SDC_") else 1)
EOF

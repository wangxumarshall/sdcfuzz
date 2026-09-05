#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""feedback.py — 真机结果→用例生成 反馈闭环 (E4 延伸)。

从 hw_scan 实验输出 (hw_*.json, 见 hw_scan.py) 提取 SDC 命中 (hash+outcome),
生成处置报告 + 强制 replay-confirm 三复跑 gate + 直接回灌:
  1. extract_hits: 扫描 hw_*.json (E3/E4 dict schema + E5 组粒度 list schema);
  2. build_feedback_report: 每命中一条 — 有 hash 的标 replay-confirm (复跑
     ≥3 次可复现才计入 SDC); E5 组粒度无 hash 证据的标 quarantine (无法定位
     到单 snapshot, 只能隔离复测, 不可回灌放大);
  3. replay_gate (闭环强制): 对 replay-confirm 命中, 先 snap_tool
     generate_corpus 把单 .pb 打包成 runner 可读语料 (exp03 已验证管线),
     再 runner 复跑 n=3 — reproduced==n 才算确认; transient/不可复现 →
     不回灌, 如实标注;
  4. reseed (直接回灌, 替代 legacy sdc_evolve.sh 死路): 把确认命中的原始
     指令字节写 seeds/evolved/<hash>.bin — get_instructions 输出与源
     seeds/bin/*.bin 逐字节一致 (实测 cmp 通过), 无损可重打包 (build_sdc_
     corpus.sh 阶段A 消费同格式)。legacy sdc_evolve.sh 读的是
     output/distributed/results.json, 永远看不到本框架命中 — 只作附带调用。

边界 (实测, 诚实记录):
  - snap_tool get_instructions 只接受单个 Snapshot .pb (无 --hash/--snap_id
    按 hash 从 SnapCorpus 挑选的能力; sdc_evolve.sh 注释里的 --snap_id 是
    从未生效的假 flag)。hash→pb 靠遍历 pb/*.pb 的 print Id 比对。
  - snap_tool print 的输出走 stderr (rc=0), 两路都拼上再匹配。
  - runner 只认 SnapCorpus 格式: 单 .pb 直接喂 → code=5 拒载; 必须
    generate_corpus 打包后复跑 (与 exp03 冒烟同一管线)。
"""
import argparse
import glob
import json
import os
import re
import subprocess

# snap_tool 优先 bazel-bin 新构建 (认识 arm-kunpeng920 枚举);
# /usr/local/bin 的 2026-08-25 部署版先于专属 PlatformId (2d04539), 会拒绝
# --target_platform=arm-kunpeng920 (实测 Illegal value), 仅作 fallback。
_BAZEL_SNAP_TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bazel-bin/tools/snap_tool")
SNAP_TOOL = _BAZEL_SNAP_TOOL if os.path.isfile(_BAZEL_SNAP_TOOL) \
    else "/usr/local/bin/snap_tool"
RUNNER = "/usr/local/bin/reading_runner_main_nolibc"

# sdc_details 行形态 (runner.cc:687, 与 hw_scan.py parse_log 同源):
#   Snapshot [<40位hex>] failed, outcome = <2|3|4>
_HASH_RE = re.compile(r"Snapshot \[([0-9a-f]+)\]")
_OUTCOME_RE = re.compile(r"outcome = (\d+)")


def extract_hits(exp_dir: str) -> list:
    """扫描 exp_dir 下 hw_*.json, 提取 SDC 命中条目。

    两种真实 schema (实测):
      1) E3/E4 设备扫描 dict: {"sdc_hits": N, "sdc_details": [...], "device": ...}
         → 每文件一条 {file, device, count, hashes, outcomes};
         sdc_hits=0 (健康硅片, E3/E4 实测) 的文件跳过 — sdc_details 为空表。
      2) E5 组粒度行 list: [{"group": ..., "hw_sdc": N, ...}, ...]
         (hw_rows.json) → hw_sdc>0 的组一条 {file, group, count, hashes: []}
         (组粒度无 hash 证据, hashes 留空, 不与 schema-1 混淆)。
    """
    hits = []
    for f in sorted(glob.glob(os.path.join(exp_dir, "hw_*.json"))):
        with open(f) as fh:
            r = json.load(fh)
        if isinstance(r, list):
            # E5 组粒度行 (hw_rows.json): 无 hash, 仅组级 SDC 计数
            for row in r:
                if isinstance(row, dict) and row.get("hw_sdc", 0) > 0:
                    hits.append({"file": f, "device": None,
                                 "group": row.get("group"),
                                 "count": row["hw_sdc"],
                                 "hashes": [], "outcomes": []})
        elif isinstance(r, dict) and r.get("sdc_hits", 0) > 0:
            details = "\n".join(r.get("sdc_details") or [])
            hashes = _HASH_RE.findall(details)
            outcomes = [int(o) for o in _OUTCOME_RE.findall(details)]
            hits.append({"file": f, "device": r.get("device"),
                         "count": r["sdc_hits"], "hashes": hashes,
                         "outcomes": outcomes})
    return hits


def snapshot_id_of_pb(pb_file: str, snap_tool: str = SNAP_TOOL):
    """读单个 Snapshot .pb 的 Id (print 输出 'Id: <hash>' 行)。失败返回 None。

    实测: snap_tool print 的输出走 stderr 而非 stdout — 两路都拼上再匹配。
    """
    try:
        p = subprocess.run([snap_tool, "print", pb_file],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^  Id: ([0-9a-f]+)$", p.stdout + p.stderr, re.M)
    return m.group(1) if m else None


def instructions_of_pb(pb_file: str, snap_tool: str = SNAP_TOOL,
                       out: str = None):
    """snap_tool get_instructions <pb> --out=<file> → 原始指令字节 (hex)。"""
    out = out or pb_file + ".insns.bin"
    try:
        p = subprocess.run(
            [snap_tool, f"--out={out}", "get_instructions", pb_file],
            capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None
        with open(out, "rb") as fh:
            return fh.read().hex()
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if os.path.exists(out):
            os.remove(out)


def build_feedback_report(hits: list, corpus_dir: str,
                          pb_dir: str = None) -> dict:
    """每命中一条: hash, outcome, 指令(hex), 处置建议。

    action 语义:
      replay-confirm — 有 hash, 可定位到单 snapshot: 打包复跑≥3次,
                       可复现才计入 SDC 并回灌;
      quarantine     — 无 hash (E5 组粒度) 或无法定位 pb: 无法复跑确认,
                       只能隔离复测, 不计入 SDC, 不回灌。
    pb_dir 给定时 (E3 布局 output/experiments/exp03-.../pb/), 逐 .pb 匹配
    snapshot Id == 命中 hash, 提取原始指令; 否则 instructions=null。
    """
    # 预建 hash→pb 映射 (每个 pb 只 print 一次)
    hash_to_pb = {}
    if pb_dir and os.path.isdir(pb_dir):
        for pb in sorted(glob.glob(os.path.join(pb_dir, "*.pb"))):
            sid = snapshot_id_of_pb(pb)
            if sid:
                hash_to_pb[sid] = pb
    items = []
    for h in hits:
        pairs = list(zip(h["hashes"], h["outcomes"])) or [(None, None)]
        for hash_, outcome in pairs:
            pb = hash_to_pb.get(hash_) if hash_ else None
            items.append({
                "hash": hash_, "outcome": outcome, "device": h.get("device"),
                "group": h.get("group"),
                "source": h["file"], "pb": pb,
                "instructions": instructions_of_pb(pb) if pb else None,
                "action": "replay-confirm" if pb else "quarantine",
                "note": ("复跑≥3次可复现才计入SDC; 否则标transient隔离"
                         if pb else
                         "无hash或无对应pb, 无法定位单snapshot复跑确认 — "
                         "隔离复测, 不回灌")})
    return {"total_hits": len(items), "items": items,
            "corpus_dir": corpus_dir,
            "next_step": "确认命中→回灌seeds/evolved/→run_guided_mutation.sh→再扫描"}


def package_pb_as_corpus(pb_file: str, work_dir: str,
                         snap_tool: str = SNAP_TOOL,
                         platform: str = "arm-kunpeng920"):
    """单 .pb → runner 可读单 snapshot SnapCorpus (exp03 已验证管线)。

    snap_tool --target_platform=arm-kunpeng920 generate_corpus <pb>
              --out=<work_dir>/<basename>.corpus
    返回 corpus 路径; 失败返回 None (如 end state 无该 platform 位)。
    """
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir,
                       os.path.splitext(os.path.basename(pb_file))[0] + ".corpus")
    try:
        p = subprocess.run(
            [snap_tool, f"--target_platform={platform}",
             "generate_corpus", pb_file, f"--out={out}"],
            capture_output=True, text=True, timeout=120)
        if p.returncode != 0 or not os.path.exists(out) or \
                os.path.getsize(out) == 0:
            return None
        return out
    except (OSError, subprocess.TimeoutExpired):
        return None


def replay_confirm(corpus_file: str, runner: str = RUNNER,
                   n: int = 3) -> dict:
    """单 snapshot 语料复跑 n 次确认可复现 (诚实红线: 不可复现不计入 SDC)。

    corpus_file 必须是 SnapCorpus 格式 (package_pb_as_corpus 产物); runner 对
    裸 .pb 会 code=5 拒载。判定: 输出含 'failed'/'mismatch' → 该次复现 SDC
    (runner.cc:687 'Snapshot [id] failed, outcome = N')。
    """
    repro = 0
    for _ in range(n):
        try:
            p = subprocess.run([runner, "--num_iterations=5", corpus_file],
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            break
        out = p.stdout + p.stderr
        if "failed" in out or "mismatch" in out.lower():
            repro += 1
    return {"corpus": corpus_file, "runs": n, "reproduced": repro,
            "confirmed": repro == n,
            "verdict": "SDC_CONFIRMED" if repro == n
            else ("TRANSIENT" if repro > 0 else "NOT_REPRODUCED")}


def replay_gate(report: dict, work_dir: str = "output/experiments/feedback",
                n: int = 3) -> dict:
    """闭环强制 gate: 对 replay-confirm 命中逐个打包+复跑, 只放行确认命中。

    就地把每条 item 补上 replay 结果:
      replay: {corpus, runs, reproduced, confirmed, verdict} (失败补 {error})
      confirmed: bool — True 才回灌; transient/不可复现 False 且
                 verdict 如实标注 (TRANSIENT / NOT_REPRODUCED), 不计入。
      action: replay-confirm → confirmed / transient / not-reproduced
    quarantine 条目 (无 pb) 不动 — 无法复跑确认, 保持隔离语义。
    """
    for item in report["items"]:
        if item["action"] != "replay-confirm" or not item.get("pb"):
            continue
        corpus = package_pb_as_corpus(item["pb"], work_dir)
        if not corpus:
            item["replay"] = {"error": "generate_corpus 打包失败 "
                                       "(end state 无该 platform 位?)"}
            item["confirmed"] = False
            item["action"] = "transient"
            continue
        r = replay_confirm(corpus, n=n)
        item["replay"] = r
        item["confirmed"] = r["confirmed"]
        if r["confirmed"]:
            item["action"] = "confirmed"
        elif r["reproduced"] > 0:
            item["action"] = "transient"
        else:
            item["action"] = "not-reproduced"
    report["confirmed_hits"] = sum(1 for i in report["items"]
                                   if i.get("confirmed"))
    return report


def reseed(report: dict, seeds_dir: str = "seeds/evolved") -> list:
    """直接回灌: 确认命中的原始指令 → seeds/evolved/<hash>.bin。

    只回灌 confirmed==True 的条目 (replay gate 之后); transient/not-
    reproduced/quarantine 一律不回灌 (诚实红线: 不可复现的不放大)。
    .bin = get_instructions 原始指令字节, 与源 seeds/bin/*.bin 同格式
    (实测逐字节一致), build_sdc_corpus.sh 阶段A / run_guided_mutation.sh
    消费同格式 — 无损可重打包。
    返回写入的文件路径列表。
    """
    written = []
    for item in report["items"]:
        if not item.get("confirmed") or not item.get("hash"):
            continue
        insns_hex = item.get("instructions")
        if not insns_hex:
            continue
        os.makedirs(seeds_dir, exist_ok=True)
        path = os.path.join(seeds_dir, f"{item['hash']}.bin")
        with open(path, "wb") as f:
            f.write(bytes.fromhex(insns_hex))
        written.append(path)
    report["reseeded"] = written
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--pb-dir", default=None,
                    help="单 Snapshot .pb 目录 (如 exp03/pb/), 用于 hash→指令提取")
    ap.add_argument("--replay-n", type=int, default=3,
                    help="replay-confirm 复跑次数 (默认3, 诚实红线)")
    ap.add_argument("--no-reseed", action="store_true",
                    help="只出报告不回灌 (默认回灌到 seeds/evolved/)")
    a = ap.parse_args()
    hits = extract_hits(a.exp_dir)
    pb_dir = a.pb_dir or os.path.join(a.exp_dir, "pb")
    rep = build_feedback_report(hits, a.corpus, pb_dir=pb_dir)
    if hits:
        rep = replay_gate(rep, n=a.replay_n)   # 强制 gate: 复跑确认才计入
        if not a.no_reseed:
            reseed(rep)                        # 只回灌 confirmed
    os.makedirs("output/experiments/feedback", exist_ok=True)
    with open("output/experiments/feedback/hits.json", "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not hits:
        print("无 SDC 命中 (健康硅片预期) — 反馈闭环空转, 无需迭代")
    else:
        print(f"命中 {rep['total_hits']} 条, 复跑确认 {rep.get('confirmed_hits', 0)} 条, "
              f"回灌 {len(rep.get('reseeded', []))} 条 → seeds/evolved/")


if __name__ == "__main__":
    main()

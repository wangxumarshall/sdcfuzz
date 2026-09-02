#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""feedback.py — 真机结果→用例生成 反馈闭环 (E4 延伸)。

从 hw_scan 实验输出 (hw_*.json, 见 hw_scan.py) 提取 SDC 命中 (hash+outcome),
生成处置报告:
  replay-confirm: 单 snapshot 复跑≥3次, 可复现才计入 SDC 结论
  quarantine:     复现失败 → 标 transient, 不计入
确认命中回灌 seeds/evolved/ → run_guided_mutation.sh 变异放大 → 再部署扫描。
(语义与 scripts/sdc_evolve.sh 一致, 移植到实验框架。)

边界 (2026/09/02 实测, 诚实记录):
  snap_tool get_instructions 只接受单个 Snapshot .pb 文件 (输出原始指令字节,
  经 --out 落盘), 没有 --hash/--snap_id 按 hash 从 SnapCorpus 语料里挑 snapshot
  的能力 (sdc_evolve.sh 注释里的 --snap_id 假 flag 从未生效, 其回灌靠日志 hash
  提取失败时整体语料回退)。E3 语料是单文件 SnapCorpus 格式 (20 snapshot 打包,
  runner 实测: corpus 文件 code:1 OK, 单 .pb 不是 corpus → code=5 拒载),
  hash→单个 .pb 反解需遍历 20 个 pb/*.pb 的 print Id 比对 — 本工具实现了这一
  逐 pb 匹配 (snapshot_id_of_pb), 匹配不到时如实标 instructions=null。
"""
import argparse
import glob
import json
import os
import re
import subprocess

# sdc_details 行形态 (runner.cc:687, 与 hw_scan.py parse_log 同源):
#   Snapshot [<40位hex>] failed, outcome = <2|3|4>
_HASH_RE = re.compile(r"Snapshot \[([0-9a-f]+)\]")
_OUTCOME_RE = re.compile(r"outcome = (\d+)")


def extract_hits(exp_dir: str) -> list:
    """扫描 exp_dir 下 hw_*.json, 提取 SDC 命中条目。

    两种真实 schema (2026/09/02 实测):
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


def snapshot_id_of_pb(pb_file: str, snap_tool: str = "/usr/local/bin/snap_tool"):
    """读单个 Snapshot .pb 的 Id (print 输出 'Id: <hash>' 行)。失败返回 None。

    实测 (2026/09/02): snap_tool print 的输出走 stderr 而非 stdout —
    两路都拼上再匹配。
    """
    try:
        p = subprocess.run([snap_tool, "print", pb_file],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^  Id: ([0-9a-f]+)$", p.stdout + p.stderr, re.M)
    return m.group(1) if m else None


def instructions_of_pb(pb_file: str, snap_tool: str = "/usr/local/bin/snap_tool"):
    """snap_tool get_instructions <pb> --out=<tmp> → 原始指令字节 (hex)。"""
    out = pb_file + ".insns.bin"
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
                "action": "replay-confirm",
                "note": "复跑≥3次可复现才计入SDC; 否则标transient隔离"})
    return {"total_hits": len(items), "items": items,
            "corpus_dir": corpus_dir,
            "next_step": "确认命中→回灌seeds/evolved/→run_guided_mutation.sh→再扫描"}


def replay_confirm(pb_file: str,
                   runner: str = "/usr/local/bin/reading_runner_main_nolibc",
                   n: int = 3) -> dict:
    """单 snapshot 复跑 n 次确认可复现 (诚实红线: 不可复现不计入 SDC 结论)。

    pb_file 必须是单 Snapshot .pb 逐个打包的可执行语料 (runner 只认 corpus
    格式); 判定: 输出含 failed/mismatch → 该次复现 SDC。
    注意: runner 对非 corpus 文件会 LOG_FATAL 退出 (code=5), 不算复现。
    """
    repro = 0
    for _ in range(n):
        try:
            p = subprocess.run([runner, "--num_iterations=5", pb_file],
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            break
        out = p.stdout + p.stderr
        if "failed" in out or "mismatch" in out.lower():
            repro += 1
    return {"pb": pb_file, "runs": n, "reproduced": repro,
            "confirmed": repro == n,
            "verdict": "SDC_CONFIRMED" if repro == n
            else ("TRANSIENT" if repro > 0 else "NOT_REPRODUCED")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--pb-dir", default=None,
                    help="单 Snapshot .pb 目录 (如 exp03/pb/), 用于 hash→指令提取")
    a = ap.parse_args()
    hits = extract_hits(a.exp_dir)
    pb_dir = a.pb_dir or os.path.join(a.exp_dir, "pb")
    rep = build_feedback_report(hits, a.corpus, pb_dir=pb_dir)
    os.makedirs("output/experiments/feedback", exist_ok=True)
    with open("output/experiments/feedback/hits.json", "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not hits:
        print("无 SDC 命中 (健康硅片预期) — 反馈闭环空转, 无需迭代")


if __name__ == "__main__":
    main()

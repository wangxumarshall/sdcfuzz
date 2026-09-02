#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""feedback 单元测试。运行: python3 tools/sdc_experiment/test_feedback.py

extract_hits: 从实验输出 hw_*.json 提取 SDC 命中 (hash + outcome);
build_feedback_report: 每命中一条处置建议 (replay-confirm / quarantine);
replay_gate: 强制三复跑 gate — 只放行 reproduced==n 的确认命中;
reseed: 只回灌 confirmed 条目 → seeds/evolved/<hash>.bin。
真实 sdc_details 行形态 (runner.cc:687, 见 hw_scan.py parse_log):
  "Snapshot [<40位hex>] failed, outcome = <2|3|4>"

confirmed-path 真实化说明: 用 snap_tool set_bytes 把健康 snapshot 的首条
指令 NOP 化构造确定性 outcome=3 失败 (无 mock/无 forcing) — 与真机 SDC 的
复跑判定走完全相同的 runner 输出路径。跳过条件: 宿主缺 snap_tool/runner。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.feedback import (  # noqa: E402
    build_feedback_report,
    extract_hits,
    replay_gate,
    reseed,
)

SNAP_TOOL = "/usr/local/bin/snap_tool"
RUNNER = "/usr/local/bin/reading_runner_main_nolibc"
# E3 已入库的健康 snapshot (真实硅片上按预期执行)
HEALTHY_PB = ("output/experiments/exp03-corpus-hw-local/pb/"
              "e1_carry_chain.pb")


def _have_tools():
    return (os.path.isfile(SNAP_TOOL) and os.path.isfile(RUNNER)
            and os.path.isfile(HEALTHY_PB))


def _snapshot_id(pb_file):
    """读 .pb 的 snapshot Id (print 输出走 stderr, 两路都拼)。"""
    p = subprocess.run([SNAP_TOOL, "print", pb_file],
                       capture_output=True, text=True, timeout=60)
    m = re.search(r"^  Id: ([0-9a-f]+)$", p.stdout + p.stderr, re.M)
    return m.group(1) if m else None


def test_extract_hits():
    with tempfile.TemporaryDirectory() as d:
        # 一个实验文件, 2 条 SDC 命中 (真实行形态, 40 位 hash)
        json.dump({"sdc_hits": 2, "sdc_details": [
            "Snapshot [abc123] failed, outcome = 2",
            "Snapshot [def456] failed, outcome = 3"],
            "device": "local-0103"},
            open(os.path.join(d, "hw_local-0103.json"), "w"))
        hits = extract_hits(d)
        assert len(hits) == 1          # 一个实验文件, 2 条命中
        assert hits[0]["count"] == 2
        assert hits[0]["hashes"] == ["abc123", "def456"]
        assert hits[0]["outcomes"] == [2, 3]
        assert hits[0]["device"] == "local-0103"
        print("PASS test_extract_hits")


def test_extract_hits_zero_hit_files_skipped():
    """sdc_hits=0 (E3/E4 真实健康输出) → 不产生 hit 条目。"""
    with tempfile.TemporaryDirectory() as d:
        json.dump({"sdc_hits": 0, "sdc_details": [], "device": "0101"},
                  open(os.path.join(d, "hw_0101.json"), "w"))
        assert extract_hits(d) == []
        print("PASS test_extract_hits_zero_hit_files_skipped")


def test_build_report():
    with tempfile.TemporaryDirectory() as d:
        json.dump({"sdc_hits": 1, "sdc_details": [
            "Snapshot [abc123] failed, outcome = 2"],
            "device": "hw_x"},
            open(os.path.join(d, "hw_x.json"), "w"))
        hits = extract_hits(d)
        rep = build_feedback_report(hits, corpus_dir="/nonexistent")
        assert rep["total_hits"] == 1
        # 无 pb_dir → 无法定位 pb → quarantine (隔离复测, 不回灌)
        assert rep["items"][0]["action"] == "quarantine"
        assert rep["items"][0]["hash"] == "abc123"
        print("PASS test_build_report")


def test_build_report_empty():
    """无命中 (健康硅片) → total_hits=0, items 空 — 闭环空转依据。"""
    rep = build_feedback_report([], corpus_dir="/nonexistent")
    assert rep["total_hits"] == 0
    assert rep["items"] == []
    print("PASS test_build_report_empty")


def test_extract_hits_e5_group_rows():
    """E5 hw_rows.json (list schema, 组粒度无 hash) 不崩溃且如实提取。"""
    with tempfile.TemporaryDirectory() as d:
        json.dump([
            {"group": "c1_l2_eviction", "hw_sdc": 0},
            {"group": "e1_carry_chain", "hw_sdc": 2, "orch_rc": 0}],
            open(os.path.join(d, "hw_rows.json"), "w"))
        hits = extract_hits(d)
        assert len(hits) == 1
        assert hits[0]["group"] == "e1_carry_chain"
        assert hits[0]["count"] == 2
        assert hits[0]["hashes"] == []   # 组粒度无 hash 证据
        # 无 hash → 无法定位单 snapshot → quarantine 而非 replay-confirm
        rep = build_feedback_report(hits, corpus_dir="/nonexistent")
        assert rep["items"][0]["action"] == "quarantine"
        print("PASS test_extract_hits_e5_group_rows")


def test_replay_gate_synthetic_hit_not_reproducible_not_reseeded():
    """合成命中指向健康 snapshot: 复跑 3 次无失败 → 不确认 → 不回灌。

    诚实红线的核心测试: 命中条目存在, 但真机复现不出 → not-reproduced
    → seeds 目录必须保持为空。
    """
    if not _have_tools():
        print("SKIP test_replay_gate_synthetic_hit_not_reproducible_"
              "not_reseeded: to be implemented (placeholder): 宿主缺 "
              "snap_tool/runner/E3 pb, 无法真实复跑")
        return
    with tempfile.TemporaryDirectory() as d:
        # 健康 pb 复制进临时 pb_dir, 用其真实 Id 造一条合成命中
        pb_dir = os.path.join(d, "pb")
        os.makedirs(pb_dir)
        shutil.copy(HEALTHY_PB, pb_dir)
        h = _snapshot_id(HEALTHY_PB)
        assert h, "无法读取健康 pb 的 snapshot Id"
        json.dump({"sdc_hits": 1, "sdc_details": [
            f"Snapshot [{h}] failed, outcome = 2"], "device": "local-0103"},
            open(os.path.join(d, "hw_local-0103.json"), "w"))
        hits = extract_hits(d)
        rep = build_feedback_report(hits, corpus_dir=d, pb_dir=pb_dir)
        assert rep["items"][0]["action"] == "replay-confirm"
        # gate: 打包 + 三复跑 (真机健康 → 必然无 failed)
        rep = replay_gate(rep, work_dir=os.path.join(d, "work"), n=3)
        item = rep["items"][0]
        assert item["replay"]["reproduced"] == 0
        assert item["replay"]["verdict"] == "NOT_REPRODUCED"
        assert item["confirmed"] is False
        assert item["action"] == "not-reproduced"
        assert rep["confirmed_hits"] == 0
        # 回灌必须为零 (目录都不应被创建)
        seeds_dir = os.path.join(d, "seeds", "evolved")
        written = reseed(rep, seeds_dir=seeds_dir)
        assert written == []
        assert not os.path.exists(seeds_dir)
        print("PASS test_replay_gate_synthetic_hit_not_reproducible_"
              "not_reseeded")


def test_reseed_confirmed_only():
    """reseed 单元测试: 只有 confirmed 条目落盘, .bin 与指令 hex 一致。"""
    with tempfile.TemporaryDirectory() as d:
        seeds = os.path.join(d, "seeds", "evolved")
        rep = {"items": [
            {"hash": "aa" * 20, "confirmed": True,
             "instructions": "00112233"},
            {"hash": "bb" * 20, "confirmed": False,   # transient 不回灌
             "instructions": "44556677"},
            {"hash": "cc" * 20, "confirmed": True,
             "instructions": None},                   # 无指令不回灌
        ]}
        written = reseed(rep, seeds_dir=seeds)
        assert written == [os.path.join(seeds, "aa" * 20 + ".bin")]
        with open(written[0], "rb") as f:
            assert f.read() == bytes.fromhex("00112233")
        assert rep["reseeded"] == written
        print("PASS test_reseed_confirmed_only")


def test_replay_gate_confirmed_path_with_real_failing_snapshot():
    """确认路径 (真实失败 snapshot, 无 mock/无 forcing): set_bytes NOP 化
    首条指令 → 确定性 outcome=3 → 三复跑 reproduced==3 → confirmed → 回灌。
    证明 gate 放行分支真实可用, 而非只有拒绝分支。
    """
    if not _have_tools():
        print("SKIP test_replay_gate_confirmed_path_with_real_failing_"
              "snapshot: to be implemented (placeholder): 宿主缺 "
              "snap_tool/runner/E3 pb")
        return
    with tempfile.TemporaryDirectory() as d:
        pb_dir = os.path.join(d, "pb")
        os.makedirs(pb_dir)
        # 构造确定性失败: 健康 snapshot 首 4 字节指令 (mov x1,#...) 换成 NOP
        # (0x1f2003d5 little-endian: 1f 20 03 d5)。end states 保留 → 可打包;
        # 寄存器终态必然不符 → runner 报 outcome=3。
        failing = os.path.join(pb_dir, "failing.pb")
        p = subprocess.run(
            [SNAP_TOOL, "--out=" + failing, "set_bytes", HEALTHY_PB,
             "0x7e7f3000", r"\x1f\x20\x03\xd5"],
            capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"set_bytes 失败: {p.stderr}"
        h = _snapshot_id(failing)
        assert h, "无法读取失败 pb 的 snapshot Id"
        json.dump({"sdc_hits": 1, "sdc_details": [
            f"Snapshot [{h}] failed, outcome = 3"], "device": "local-0103"},
            open(os.path.join(d, "hw_local-0103.json"), "w"))
        hits = extract_hits(d)
        rep = build_feedback_report(hits, corpus_dir=d, pb_dir=pb_dir)
        rep = replay_gate(rep, work_dir=os.path.join(d, "work"), n=3)
        item = rep["items"][0]
        assert item["replay"]["runs"] == 3
        assert item["replay"]["reproduced"] == 3
        assert item["replay"]["verdict"] == "SDC_CONFIRMED"
        assert item["confirmed"] is True
        assert item["action"] == "confirmed"
        assert rep["confirmed_hits"] == 1
        # 确认 → 回灌; .bin 是被 NOP 化后的指令 (真实提取, 含 1f2003d5)
        seeds = os.path.join(d, "seeds", "evolved")
        written = reseed(rep, seeds_dir=seeds)
        assert len(written) == 1
        with open(written[0], "rb") as f:
            data = f.read()
        assert data[:4] == bytes.fromhex("1f2003d5")   # NOP 化生效
        print("PASS test_replay_gate_confirmed_path_with_real_failing_"
              "snapshot")


if __name__ == "__main__":
    test_extract_hits()
    test_extract_hits_zero_hit_files_skipped()
    test_build_report()
    test_build_report_empty()
    test_extract_hits_e5_group_rows()
    test_replay_gate_synthetic_hit_not_reproducible_not_reseeded()
    test_reseed_confirmed_only()
    test_replay_gate_confirmed_path_with_real_failing_snapshot()
    print("ALL PASS")

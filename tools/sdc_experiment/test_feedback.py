#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""feedback 单元测试。运行: python3 tools/sdc_experiment/test_feedback.py

extract_hits: 从实验输出 hw_*.json 提取 SDC 命中 (hash + outcome);
build_feedback_report: 每命中一条处置建议 (replay-confirm / quarantine)。
真实 sdc_details 行形态 (runner.cc:687, 见 hw_scan.py parse_log):
  "Snapshot [<40位hex>] failed, outcome = <2|3|4>"
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.feedback import (  # noqa: E402
    build_feedback_report,
    extract_hits,
)


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
        assert rep["items"][0]["action"] in ("replay-confirm", "quarantine")
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
        print("PASS test_extract_hits_e5_group_rows")


if __name__ == "__main__":
    test_extract_hits()
    test_extract_hits_zero_hit_files_skipped()
    test_build_report()
    test_build_report_empty()
    test_extract_hits_e5_group_rows()
    print("ALL PASS")

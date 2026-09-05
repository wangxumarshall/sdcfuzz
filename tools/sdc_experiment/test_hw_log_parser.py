#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_log_parser 单一权威解析测试。
运行: python3 -m pytest tools/sdc_experiment/test_hw_log_parser.py -q"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.hw_log_parser import parse_log, HASH_RE, OUTCOME_RE  # noqa: E402

FAKE_LOG = """Snapshot [abc123def456abc123def456abc123def456abcd] failed, outcome = 2
Snapshot [def456] failed, outcome = 5
Snapshot [789abc] failed, outcome = 3
Snapshot [aaa000] failed, outcome = 6
Received signal SIGSEGV while outside of snap
Received signal SIGSEGV while outside of snap
SIGTERM received
"""


def test_parse_log_counts():
    r = parse_log(FAKE_LOG)
    assert r["sdc_hits"] == 2          # outcome 2+3
    assert r["runaway_noise"] == 1     # outcome 5
    assert r["misbehave_noise"] == 1   # outcome 6
    assert r["sigsegv_noise"] == 2
    assert r["sigterm"] == 1
    assert r["total_failed"] == 4
    assert len(r["sdc_details"]) == 2


def test_parse_log_empty():
    r = parse_log("")
    assert r == {"sigsegv_noise": 0, "sigterm": 0, "runaway_noise": 0,
                 "misbehave_noise": 0, "sdc_hits": 0, "sdc_details": [],
                 "total_failed": 0}


def test_regexes_feedback_shape():
    """feedback.py 消费的 hash/outcome 提取正则。"""
    m = HASH_RE.search("Snapshot [abc123] failed, outcome = 2")
    assert m and m.group(1) == "abc123"
    m = OUTCOME_RE.search("Snapshot [abc123] failed, outcome = 2")
    assert m and m.group(1) == "2"

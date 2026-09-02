#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_scan 单元测试。运行: python3 tools/sdc_experiment/test_hw_scan.py

parse_log 解析规则与 scripts/collect_results.py 逐字符一致 (移植自 Task 7 brief
Step 1, 正则原样); 另含 v1-compat 汇总行交叉校验 (orchestrator --enable_v1_compat_logging
输出的 issues_detected/runaway_count/play_count, 用于 E3 真跑日志的完整性交叉验证)。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.hw_scan import parse_log, parse_v1_summary  # noqa: E402

FAKE_LOG = """Snapshot [abc123] failed, outcome = 2
Snapshot [def456] failed, outcome = 5
Snapshot [789abc] failed, outcome = 3
Received signal SIGSEGV while outside of snap
Received signal SIGSEGV while outside of snap
SIGTERM received
Snapshot [aaa111] failed, outcome = 6
"""

# orchestrator --enable_v1_compat_logging 实测输出形态 (2026/09/02 本机 0103 探针,
# /tmp/orch_probe/v1c.log, 15s/2cpu 冒烟):
V1_LINES = """Silifuzz Checker Result:{issues_detected = 0, num_cores = 128, elapsed_time = 3s, user_time = 6s, system_time = 0, batch_count = ?, play_count = 1, snapshot_execution_errors = 0, runaway_count = 0, max_rss_kb = 0, had_checker_misconfigurations = false}
Silifuzz Checker Result:{issues_detected = 0, num_cores = 128, elapsed_time = 15s, user_time = 28s, system_time = 0, batch_count = ?, play_count = 10, snapshot_execution_errors = 0, runaway_count = 0, max_rss_kb = 0, had_checker_misconfigurations = false}
Silifuzz Checker Result:{issues_detected = 2, num_cores = 128, elapsed_time = 15s, user_time = 28s, system_time = 0, batch_count = ?, play_count = 10, snapshot_execution_errors = 0, runaway_count = 1, max_rss_kb = 0, had_checker_misconfigurations = false}
"""

# 健康日志形态: orchestrator 默认 (无 --enable_v1_compat_logging, 无失败) 完全静默,
# 日志 0 行 (实测 2026/09/02, 10s/2cpu, rc=0)。空文本是合法输入。
EMPTY_LOG = ""


def test_parse_log():
    r = parse_log(FAKE_LOG)
    assert r["sdc_hits"] == 2, f"outcome 2/3 是 SDC, got {r['sdc_hits']}"
    assert r["runaway_noise"] == 1
    assert r["misbehave_noise"] == 1
    assert r["sigsegv_noise"] == 2
    assert r["sigterm"] >= 1
    assert len(r["sdc_details"]) == 2
    assert r["total_failed"] == 4, f"4 行 failed (2/5/3/6), got {r['total_failed']}"
    print(f"PASS test_parse_log: {r}")


def test_parse_log_empty():
    """健康硅片 + 默认日志级别 → orchestrator 静默 (0 行日志, rc=0, 实测)。"""
    r = parse_log(EMPTY_LOG)
    assert r["sdc_hits"] == 0 and r["total_failed"] == 0
    assert r["sigsegv_noise"] == 0 and r["sigterm"] == 0
    assert r["runaway_noise"] == 0 and r["misbehave_noise"] == 0
    print(f"PASS test_parse_log_empty: 健康静默日志 -> {r}")


def test_parse_log_platform_mismatch_is_not_sdc():
    """outcome 1 (kPlatformMismatch) 不是 SDC (红线: 只有 2/3/4 是)。"""
    r = parse_log("Snapshot [abc123] failed, outcome = 1\n")
    assert r["sdc_hits"] == 0
    assert r["total_failed"] == 1
    print("PASS test_parse_log_platform_mismatch_is_not_sdc: outcome=1 不计入 SDC")


def test_parse_v1_summary():
    """v1-compat 汇总行解析: 取最后一条 (终态), 供 E3 交叉校验。"""
    v = parse_v1_summary(V1_LINES)
    assert v is not None, "至少一条 v1 汇总行"
    assert v["issues_detected"] == 2
    assert v["play_count"] == 10
    assert v["runaway_count"] == 1
    v0 = parse_v1_summary("no summary here\n")
    assert v0 is None
    print(f"PASS test_parse_v1_summary: 终态 {v}")


def test_parse_real_log_if_exists():
    p = "output/distributed/logs/0103.scan.log"
    if not os.path.exists(p):
        print("SKIP test_parse_real_log: 无历史日志")
        return
    r = parse_log(open(p, errors="replace").read())
    print(f"PASS test_parse_real_log (历史真实日志): sdc={r['sdc_hits']}, "
          f"noise(segv={r['sigsegv_noise']},runaway={r['runaway_noise']},"
          f"misbehave={r['misbehave_noise']})")


if __name__ == "__main__":
    test_parse_log()
    test_parse_log_empty()
    test_parse_log_platform_mismatch_is_not_sdc()
    test_parse_v1_summary()
    test_parse_real_log_if_exists()
    print("ALL PASS")

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_log_parser.py — runner/orchestrator 日志的单一权威解析。

SDC 判定口径唯一定义点 (此前三处拷贝: hw_scan.py / collect_results.py /
feedback.py, 靠人工保持一致):
  runner RunSnapOutcome 枚举 (common/snapshot_enums.h):
    0=kAsExpected 1=kPlatformMismatch 2=kMemoryMismatch
    3=kRegisterStateMismatch 4=kEndpointMismatch
    5=kExecutionRunaway 6=kExecutionMisbehave
  真 SDC = outcome 2/3/4 (计算结果与预期不符, 静默数据损坏);
  outcome 5 (满负载调度延迟超时) / 6 (信号) = 噪声;
  SIGSEGV-outside-snap (fork/mmap 资源耗尽击中 snap 外路径) / SIGTERM = 噪声。
日志行形态 (runner.cc:687): Snapshot [<40位hex>] failed, outcome = <n>
"""
import re

_FAILED_RE = re.compile(
    r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = (\d+)')
_SDC_DETAIL_RE = re.compile(
    r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = [234]')
_SIGSEGV_RE = re.compile(r'SIGSEGV while outside of snap')
_SIGTERM_RE = re.compile(r'SIGTERM')

# feedback.py 消费的单值提取正则 (hash / outcome)
HASH_RE = re.compile(r"Snapshot \[([0-9a-f]+)\]")
OUTCOME_RE = re.compile(r"outcome = (\d+)")


def parse_log(text: str) -> dict:
    """解析 runner/orchestrator 日志文本 → 结构化计数。"""
    sigsegv_outside = len(_SIGSEGV_RE.findall(text))
    sigterm = len(_SIGTERM_RE.findall(text))
    all_failed = _FAILED_RE.findall(text)
    sdc_outcomes = [o for o in all_failed if o in ('2', '3', '4')]
    runaway = sum(1 for o in all_failed if o == '5')
    misbehave = sum(1 for o in all_failed if o == '6')
    sdc_details = _SDC_DETAIL_RE.findall(text)[:10]
    return {"sigsegv_noise": sigsegv_outside, "sigterm": sigterm,
            "runaway_noise": runaway, "misbehave_noise": misbehave,
            "sdc_hits": len(sdc_outcomes), "sdc_details": sdc_details,
            "total_failed": len(all_failed)}

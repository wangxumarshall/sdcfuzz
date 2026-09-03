#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_vault.py — Vault JSONL 持久层单元测试。

R5 解法: 候选/评估幂等存储 + 血缘回溯。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import Candidate
from tools.sdc_pipeline.vault import Vault, Assessment


def _cand(ident, parents=None, origin="seed:t"):
    return Candidate(ident=ident, source_asm="asm", code_bytes=b"\x00" * 4,
                     regs_init={0: 1}, parents=parents or [], origin=origin)


def _assess(ident, ace=0.5, ibr=0.3):
    return Assessment(ident=ident, metrics={"ace_proxy": ace, "ibr": ibr},
                      evaluator="test")


def test_put_and_get():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        c = _cand("aaa111")
        v.put_candidate(c)
        got = v.get("aaa111")
        assert got is not None and got.ident == "aaa111"
        assert got.source_asm == "asm"


def test_put_idempotent():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        v.put_candidate(_cand("aaa111"))
        v.put_candidate(_cand("aaa111"))  # 同 ident 重复 put
        assert v.count_candidates() == 1, "幂等: 同 ident 不产生第二行"


def test_lineage():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        v.put_candidate(_cand("seed001"))
        v.put_candidate(_cand("child01", parents=["seed001"]))
        v.put_candidate(_cand("grand01", parents=["child01"]))
        chain = v.lineage("grand01")
        assert chain == ["grand01", "child01", "seed001"], f"血缘链错误: {chain}"


def test_lineage_missing():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        assert v.lineage("nosuch") == []


def test_children():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        v.put_candidate(_cand("seed001"))
        v.put_candidate(_cand("child01", parents=["seed001"]))
        v.put_candidate(_cand("child02", parents=["seed001"]))
        v.put_candidate(_cand("other", parents=["xxx"]))
        kids = v.children("seed001")
        assert sorted(kids) == ["child01", "child02"]


def test_assessment_put_and_top_by():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        for i, (ident, ace) in enumerate([("a", 0.1), ("b", 0.9), ("c", 0.5)]):
            v.put_candidate(_cand(ident))
            v.put_assessment(_assess(ident, ace=ace))
        top = v.top_by("ace_proxy", 2)
        assert [i for i, _ in top] == ["b", "c"], "top_by 必须按指标降序"


def test_assessment_idempotent_and_persist():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        v.put_candidate(_cand("aaa111"))
        v.put_assessment(_assess("aaa111"))
        v.put_assessment(_assess("aaa111"))  # 同 ident 同 evaluator 幂等
        assert v.count_assessments() == 1
        # 重开 (持久化验证)
        v2 = Vault(td)
        assert v2.get("aaa111") is not None
        assert v2.count_assessments() == 1


def test_top_by_missing_metric():
    with tempfile.TemporaryDirectory() as td:
        v = Vault(td)
        v.put_candidate(_cand("a"))
        v.put_assessment(_assess("a"))
        assert v.top_by("nonexistent_metric", 5) == []

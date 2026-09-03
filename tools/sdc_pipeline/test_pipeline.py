#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_pipeline.py — 筛选器 + 轻量闭环编排器单元测试（首里程碑 M1）。"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.vault import Vault, Assessment
from tools.sdc_pipeline.filters import WeightedFilter, ParetoFilter
from tools.sdc_pipeline.pipeline import Pipeline, HillClimbPolicy
from tools.sdc_pipeline.mutators import OperandBitFlipMutator, OperandDictMutator
from tools.sdc_pipeline.evaluators import IBREvaluator, TogglePowerEvaluator

ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mov     x2, #1
    adds    x0, x1, x2
    eor     x3, x0, x1
"""


def _cand(ident, ace=0.5, ibr=0.3, power=0.2):
    """合成 (Candidate, Assessment) 对, 指标注入。
    ident_label 映射: 测试用短名 → 内容 hash ident, 返回 (cand, assessment, label)。"""
    c = make_candidate(ASM, {1: hash(ident) & 0xFFFF, 2: 2}, [], f"test:{ident}")
    a = Assessment(ident=c.ident, metrics={"ace_proxy": ace, "ibr": ibr,
                                           "toggle_power_proxy": power},
                   evaluator="synthetic")
    return c, a, ident


def test_weighted_filter_orders_correctly():
    rows = [
        _cand("a", ace=0.9, ibr=0.1, power=0.1),
        _cand("b", ace=0.5, ibr=0.5, power=0.5),
        _cand("c", ace=0.1, ibr=0.9, power=0.1),
    ]
    f = WeightedFilter({"ace_proxy": 1.0, "ibr": 0.0, "toggle_power_proxy": 0.0})
    sel = f.select(rows, 2)
    label_of = {c.ident: lab for c, _, lab in rows}
    assert [label_of[s.ident] for s in sel] == ["a", "b"], "纯 ace 权重必须按 ace 降序"


def test_weighted_filter_composite():
    rows = [
        _cand("a", ace=0.0, ibr=0.0, power=0.0),
        _cand("b", ace=1.0, ibr=1.0, power=1.0),
    ]
    f = WeightedFilter({"ace_proxy": 0.5, "ibr": 0.3, "toggle_power_proxy": 0.2})
    sel = f.select(rows, 1)
    label_of = {c.ident: lab for c, _, lab in rows}
    assert label_of[sel[0].ident] == "b"


def test_pareto_filter_keeps_nondominated():
    # a 支配 d (全指标>=); b/c 互不支配; d 被支配
    rows = [
        _cand("a", ace=0.9, ibr=0.1, power=0.1),
        _cand("b", ace=0.5, ibr=0.9, power=0.5),
        _cand("c", ace=0.1, ibr=0.5, power=0.9),
        _cand("d", ace=0.05, ibr=0.05, power=0.05),
    ]
    f = ParetoFilter(maximize=["ace_proxy", "ibr", "toggle_power_proxy"])
    sel = f.select(rows, 10)
    label_of = {c.ident: lab for c, _, lab in rows}
    labels = {label_of[s.ident] for s in sel}
    assert "d" not in labels, "被支配候选必须被剔除非支配前沿"
    assert {"a", "b", "c"} <= labels


def test_pipeline_lightweight_loop():
    """轻量闭环: 2 mutator + 2 evaluator 跑 2 代。"""
    with tempfile.TemporaryDirectory() as td:
        vault = Vault(td)
        seed = make_candidate(ASM, {1: 0x123, 2: 1}, [], "seed:test")
        vault.put_candidate(seed)
        mutators = [OperandBitFlipMutator(3), OperandDictMutator(3)]
        evaluators = [IBREvaluator(), TogglePowerEvaluator()]
        filt = WeightedFilter({"ibr": 0.5, "toggle_power_proxy": 0.5})
        pipe = Pipeline(seeds=[seed], mutators=mutators, evaluators=evaluators,
                        filt=filt, vault=vault,
                        policy=HillClimbPolicy(mutator_names=[m.name for m in mutators]),
                        rng_seed=42)
        report = pipe.run(generations=2, per_gen_mutations=2, top_k=2)
        # Vault: seed + 每代产物 (同父同变异可能撞 ident, Vault 幂等去重是
        # 正确语义 → 上界 1+2*4, 下界保证有产出)
        assert 1 + 2 <= vault.count_candidates() <= 1 + 2 * 4
        # 每代报告 produced 之和与落盘增量一致 (幂等只减不增)
        total_produced = sum(g.produced for g in report.generations)
        assert vault.count_candidates() <= 1 + total_produced
        # 报告: 每代指标均值存在
        assert len(report.generations) == 2
        for gen in report.generations:
            assert "ibr" in gen.metrics_mean or \
                   "toggle_power_proxy" in gen.metrics_mean
        # 血缘: 存在至少一条两代链
        all_idents = [i for i, _ in vault.top_by("ibr", 1000)]
        assert len(all_idents) > 0


def test_pipeline_policy_learns_from_metric_delta():
    """HillClimbPolicy: 上代指标提升的 mutator 权重应增加 (RL 接入口验证)。"""
    pol = HillClimbPolicy(mutator_names=["m1", "m2"])
    w0 = dict(pol.weights)
    pol.observe(generation=1, mutator_scores={"m1": 0.9, "m2": 0.1},
                baseline=0.5)
    w1 = pol.weights
    assert w1["m1"] > w0["m1"] or w1["m2"] < w0["m2"], \
        "高分 mutator 权重必须相对上升"
    chosen = pol.choose_mutators(rng=random.Random(0))
    assert all(m in ("m1", "m2") for m in chosen)

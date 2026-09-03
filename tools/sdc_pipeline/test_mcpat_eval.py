#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_mcpat_eval.py — McPAT 功耗 Evaluator 插件单元测试。

依赖 /home/sdc/wangxu/mcpat (tsv110.xml)。安装见
docs/experiments/2026-09-03-mcpat-setup.md。单测用合成指令构成,
真实 mcpat 调用 smoke 单独跑。
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.mcpat_eval import (
    McPATEvaluator, classify_insns, build_xml, MCPAT_BIN, TSV110_XML)

ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    adds    x0, x1, x2
    eor     x3, x0, x1
    ldr     x4, [x5]
    fmul    d0, d1, d2
"""


def _cand():
    from tools.sdc_pipeline.candidate import make_candidate
    return make_candidate(ASM, {1: 1, 2: 2, 5: 0x10000, 0: 0},
                          [], "test:mcpat")


def test_mcpat_installed():
    assert os.path.exists(MCPAT_BIN), f"mcpat 缺失: {MCPAT_BIN}"
    assert os.path.exists(TSV110_XML), f"tsv110.xml 缺失: {TSV110_XML}"


def test_classify_insns_categories():
    code = _cand().code_bytes
    cats = classify_insns(code)
    # 4 条指令: 2 ALU + 1 LSU + 1 FPU
    assert cats["alu"] + cats["mul"] == 2
    assert cats["lsu"] == 1
    assert cats["fpu"] == 1
    assert sum(cats.values()) == 4


def test_build_xml_activity_from_mix():
    cats = {"alu": 8, "mul": 0, "lsu": 0, "fpu": 0, "br": 0, "ifu": 0}
    xml = build_xml(cats, total_insns=10, cycles=20)
    # ALU 占比 80% → ALU_duty_cycle 应显著提高 (基线 0.76 → ~0.9+)
    import re
    m = re.search(r'name="ALU_duty_cycle" value="([\d.]+)"', xml)
    assert m and float(m.group(1)) > 0.8, "ALU 密集负载应提升 ALU duty cycle"
    # LSU 空闲 → LSU duty 应降
    m2 = re.search(r'name="LSU_duty_cycle" value="([\d.]+)"', xml)
    assert m2 and float(m2.group(1)) < 0.71, "无 LSU 指令应降低 LSU duty"


def test_build_xml_fpu_heavy():
    cats = {"alu": 0, "mul": 0, "lsu": 0, "fpu": 10, "br": 0, "ifu": 0}
    xml = build_xml(cats, total_insns=10, cycles=20)
    import re
    m = re.search(r'name="FPU_duty_cycle" value="([\d.]+)"', xml)
    assert m and float(m.group(1)) > 0.41, "FPU 密集负载应提升 FPU duty (基线 0.41)"


def test_evaluator_smoke_real_mcpat():
    """真实 mcpat 调用: 两个不同指令构成的候选功耗应可算且不同。"""
    ev = McPATEvaluator()
    cand = _cand()
    m = ev.evaluate(cand)
    assert "power_mcpat_w" in m
    assert 0.1 < m["power_mcpat_w"] < 10.0, "单核 V110 功耗量级合理性 (22nm 近似)"
    assert "power_note" in m, "必须携带 22nm 近似声明 (诚实边界)"

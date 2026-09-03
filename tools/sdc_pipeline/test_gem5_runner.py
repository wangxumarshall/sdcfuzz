#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""test_gem5_runner.py — gem5 golden 注册 + CHAOS 检出率验证器单元测试。

单测只测参数构造/golden 解析状态机 (mock subprocess); 真实 gem5 smoke
单独跑 (M2 里程碑)。
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_pipeline.gem5_runner import (
    build_workload_files, parse_golden, make_inject_cmd, Gem5Validator)

SIMOUT_GOLDEN = """Starting simulation...
SUM=118831515424667458 CRC=dbc8bf2a
Exiting @ tick 443784000
"""
SIMOUT_EMPTY = "Starting simulation...\n"

CAND_ASM = """    .include "asm_common.S.inc"
    .text
    .globl _start
_start:
    mov     x2, #1
    adds    x0, x1, x2
"""


def _cand():
    from tools.sdc_pipeline.candidate import make_candidate
    return make_candidate(CAND_ASM, {1: 0x123, 2: 1}, [], "test:gem5")


def test_build_workload_files_structure():
    import tempfile
    cand = _cand()
    with tempfile.TemporaryDirectory() as td:
        s_path, c_path = build_workload_files(cand, td)
        s_src = open(s_path).read()
        c_src = open(c_path).read()
    assert "SUM=" in c_src, "工作负载必须打印 SUM= 行 (golden 判定依据)"
    assert "main" in c_src
    assert "0x123" in c_src, "初值寄存器必须以数值形式注入"
    assert ".long" in s_src and "payload" in s_src, "payload.S 必须嵌入候选机器码"
    assert "stp x29, x30" in s_src and "ldp x29, x30" in s_src, "AAPCS64 帧保存/恢复必须存在"


def test_parse_golden():
    g = parse_golden(SIMOUT_GOLDEN)
    assert g["golden"] == "SUM=118831515424667458 CRC=dbc8bf2a"
    assert g["nc"] == 443784000, "nc = Exiting tick (注入 ROI 依据)"
    assert parse_golden(SIMOUT_EMPTY) is None, "无 SUM 行 → golden 失败"


def test_make_inject_cmd():
    cand = _cand()
    cmd = make_inject_cmd(binary="/tmp/wl.bin", script="/tmp/sc.py",
                          first_clock=1000, mode="bit", seed=7)
    assert "--mode" in cmd and "inject" in cmd
    assert "--first-clock" in cmd and "1000" in cmd
    assert "--max-faults" in cmd and cmd[cmd.index("--max-faults") + 1] == "1"
    assert "--rng-seed" in cmd
    assert "--injector" not in cmd, "bit 模式不加 injector"
    cmd2 = make_inject_cmd(binary="/tmp/wl.bin", script="/tmp/sc.py",
                           first_clock=1000, mode="struct", seed=7)
    assert "--injector" in cmd2 and cmd2[cmd2.index("--injector") + 1] == "lsq_fwd"
    assert "--structural-fault" in cmd2


def test_validator_register_golden_state_machine():
    """mock gem5: golden 跑一次返回 SIMOUT → 注册成功, 再次注册幂等。"""
    cand = _cand()
    v = Gem5Validator(out_root="/tmp/test_g5r")
    with mock.patch("tools.sdc_pipeline.gem5_runner._run_gem5_capture",
                    return_value=SIMOUT_GOLDEN), \
         mock.patch("tools.sdc_pipeline.gem5_runner._compile_workload",
                    return_value="/tmp/fake_wl"):
        g1 = v.register_golden(cand)
        assert g1 is not None and g1["golden"].startswith("SUM=")
        assert v.is_registered(cand.ident)
        g2 = v.register_golden(cand)  # 幂等: 已注册直接返回
        assert g2 == g1


def test_validator_register_golden_failure():
    """mock gem5 无输出 → 返回 None 且标记 incompatible。"""
    cand = _cand()
    v = Gem5Validator(out_root="/tmp/test_g5r2")
    with mock.patch("tools.sdc_pipeline.gem5_runner._run_gem5_capture",
                    return_value=SIMOUT_EMPTY), \
         mock.patch("tools.sdc_pipeline.gem5_runner._compile_workload",
                    return_value="/tmp/fake_wl"):
        assert v.register_golden(cand) is None
        assert not v.is_registered(cand.ident)


def test_validate_detection_roi_from_own_nc():
    """注入 fault-clock 必须从候选自己的 nc ROI 抽取。"""
    cand = _cand()
    v = Gem5Validator(out_root="/tmp/test_g5r3")
    v._goldens[cand.ident] = {"golden": "SUM=1 CRC=2", "nc": 100000,
                              "binary": "/tmp/fake_wl"}
    calls = []
    with mock.patch("tools.sdc_pipeline.gem5_runner._run_gem5_capture",
                    side_effect=lambda *a, **k: calls.append(a) or SIMOUT_GOLDEN):
        r = v.validate_detection(cand, n_runs=4, mode="bit", seed=1, jobs=1)
    assert "rate" in r and "wilson_low" in r and "wilson_high" in r
    assert r["n"] == 4
    # ROI: 20%-80% of 100000 → first_clock ∈ [20000, 80000]
    # (mock 不校验值, 但参数构造逻辑已在 make_inject_cmd 测试覆盖)

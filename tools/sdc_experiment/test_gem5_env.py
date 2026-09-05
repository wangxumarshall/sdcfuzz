#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_env 路径解析测试。运行: python3 -m pytest tools/sdc_experiment/test_gem5_env.py -q"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment import gem5_env  # noqa: E402


def test_gem5_opt_resolves_to_existing_file():
    """GEM5_OPT 必须指向真实存在的 gem5.opt (本机 ~/gem5-fi-wangxu)。"""
    assert os.path.isfile(gem5_env.GEM5_OPT), \
        f"GEM5_OPT 不存在: {gem5_env.GEM5_OPT}"
    assert gem5_env.GEM5_OPT.endswith("build/ARM/gem5.opt")


def test_check_env_ok_on_this_host():
    """check_env 在本机应报 ok (gem5.opt + deps + taishan script + workloads)。"""
    r = gem5_env.check_env()
    assert r["ok"], f"check_env 报错: {r['problems']}"


def test_chaos_se_script_exists():
    """sdcbench 协议的 se 注入脚本路径存在。"""
    assert os.path.isfile(gem5_env.CHAOS_SE_SCRIPT), \
        f"CHAOS_SE_SCRIPT 不存在: {gem5_env.CHAOS_SE_SCRIPT}"

# tools/sdc_experiment/gem5_env.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_env.py — 本机 gem5-CHAOS 注入环境封装。

本机 gem5.opt (v25.1.0.1) 运行依赖 ~/gem5-deps (解包 RPM) 的环境变量;
注入配置与 workload 已固化入仓 gem5_config/ (来源: 0101, golden 逐字节
一致, 见计划 F7)。此后仿真实验 100% 本机自持, 不依赖远程板卡。
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPS = os.path.expanduser("~/gem5-deps")

# 本机 gem5-fi 实际位于 ~/wangxu/gem5-fi (HOME=/home/sdc, 用户目录嵌套)
def _find_gem5_opt():
    cands = [os.path.expanduser(p) for p in (
        "~/wangxu/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt",  # 本机 0103 实际位置
        "~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt",          # 常规布局
    )]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]

GEM5_OPT = _find_gem5_opt()
TAISHAN_SCRIPT = os.path.join(_REPO, "gem5_config/configs/two_level_taishan.py")
WORKLOAD_DIR = os.path.join(_REPO, "gem5_config/workloads")

# 复刻 ~/gem5-deps/env.sh 的关键环境 (source 不可用于 subprocess)
def local_gem5_env() -> dict:
    env = dict(os.environ)
    deps = DEPS
    env["PATH"] = f"{deps}/py/usr/bin:/usr/local/bin:/usr/bin:/bin"
    env["LD_LIBRARY_PATH"] = (f"{deps}/usr/lib64:{deps}/py/usr/lib64:"
                              f"/usr/lib64:{env.get('LD_LIBRARY_PATH','')}")
    env["PYTHONPATH"] = (f"{deps}/usr/lib/python3.11/site-packages:"
                         f"{deps}/py/usr/lib/python3.11/site-packages:"
                         f"{deps}/py/usr/lib64/python3.11/site-packages:"
                         f"{env.get('PYTHONPATH','')}")
    return env

# 工作负载组表 (golden/nc 来自已验证 sweep: F3/F4; 路径指向入仓 workload)
GROUPS = {
    "A":   {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload"),
            "golden": "SUM=1176263118239748788 CRC=5b8846f3", "nc": 63788},
    "B":   {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload_random"),
            "golden": "SUM=10721424292087689827 CRC=6728fc4a", "nc": 71215},
    "D13": {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload_d13"),
            "golden": "SUM=118831515424667458 CRC=dbc8bf2a", "nc": 110946},
}

def check_env() -> dict:
    """自检: gem5.opt 存在 + deps 存在 + 各 workload 存在 + golden 可复现标记。"""
    problems = []
    if not os.path.exists(GEM5_OPT):
        problems.append(f"gem5.opt missing: {GEM5_OPT}")
    if not os.path.isdir(DEPS):
        problems.append(f"gem5-deps missing: {DEPS}")
    if not os.path.exists(TAISHAN_SCRIPT):
        problems.append(f"taishan script missing: {TAISHAN_SCRIPT}")
    for g, spec in GROUPS.items():
        if not os.path.exists(spec["binary"]):
            problems.append(f"workload {g} missing: {spec['binary']}")
    return {"ok": not problems, "problems": problems}

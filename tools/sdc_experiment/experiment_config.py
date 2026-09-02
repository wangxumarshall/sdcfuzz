#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""experiment_config.py — sdcfuzz 实验验证框架: 配置系统

所有实验共享的参数(设备预算/ROI/判定阈值)集中在此, 单一事实来源。
默认值针对本机 0103 (Kunpeng 920, 128核, openEuler 24.03)。
"""
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # 无 pyyaml 时仅支持 default_config

# 全局红线常量 (CLAUDE.md / 计划 Global Constraints)
MAX_CPUS_HARD_LIMIT = 64          # MCE 红线: 本机并发上限
DEFAULT_ROI = (0.2, 0.8)          # gem5 注入 ROI: [20%, 80%] 周期
WILSON_Z = 1.96                   # 95% CI

@dataclass
class ExperimentConfig:
    experiment_id: str = "exp"
    out_dir: Path = Path("output/experiments")
    # gem5 环境 (本机默认; 远程跑时由设备层覆盖)
    gem5_opt: Path = Path.home() / "gem5-fi/CHAOS/gem5/build/ARM/gem5.opt"
    gem5_script: Path = Path("gem5_config/configs/two_level_taishan.py")  # 入仓的注入配置 (Task 5 Step 0 固化)
    # 真机预算
    max_cpus: int = 8              # 从 8 起步 (F8: 满负载 SIGSEGV 噪声)
    scan_duration_s: int = 1800    # 每次真机扫描 30min
    # sweep 预算
    sweep_runs: int = 100
    roi: tuple = DEFAULT_ROI
    wilson_z: float = WILSON_Z
    # 判定阈值 (预注册, 不得事后修改)
    beat_ratio_threshold: float = 1.5   # D/B ≥ 1.5× 记为击败 (预注册)
    significance_alpha: float = 0.05

    def to_dict(self):
        d = asdict(self)
        d["out_dir"] = str(self.out_dir)
        d["gem5_opt"] = str(self.gem5_opt)
        d["gem5_script"] = str(self.gem5_script)
        d["roi"] = list(self.roi)
        return d

def default_config(experiment_id: str) -> ExperimentConfig:
    return ExperimentConfig(experiment_id=experiment_id,
                            out_dir=Path("output/experiments") / experiment_id)

def load_config(path: str) -> ExperimentConfig:
    if yaml is None:
        raise RuntimeError("pyyaml not installed; use default_config()")
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    base = default_config(raw.get("experiment_id", "exp"))
    for k, v in raw.items():
        if k == "roi":
            v = tuple(v)
        if hasattr(base, k):
            if k in ("out_dir", "gem5_opt", "gem5_script") and v is not None:
                v = Path(v)
            setattr(base, k, v)
    if base.max_cpus > MAX_CPUS_HARD_LIMIT:
        raise ValueError(f"max_cpus={base.max_cpus} exceeds hard limit {MAX_CPUS_HARD_LIMIT} (MCE)")
    return base

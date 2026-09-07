#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""filters.py — 多指标筛选器 (sdc_pipeline Filter 层)。

- WeightedFilter: 指标加权和降序取 top-k
- ParetoFilter:  非支配排序 (NSGA 风格第一层), scheme §5.1 跨结构联合优化的
  "Pareto 最优序列集" 的高功耗/高覆盖筛选实现
"""
import random

from tools.sdc_pipeline.vault import Assessment


def _metric_get(a: Assessment, name: str):
    return a.metrics.get(name)


class WeightedFilter:
    """Σ w_i * metric_i 加权和, 降序取 top-k。缺指标的候选该指标记 0。"""
    def __init__(self, weights: dict):
        self.weights = weights

    def score(self, a: Assessment) -> float:
        return sum(w * (a.metrics.get(m, 0.0) or 0.0)
                   for m, w in self.weights.items())

    def select(self, rows: list, k: int) -> list:
        scored = sorted(rows, key=lambda ca: -self.score(ca[1]))
        return [r[0] for r in scored[:k]]


class ParetoFilter:
    """非支配筛选: 保留非支配前沿 (全部 maximize 指标)。"""
    def __init__(self, maximize: list):
        self.maximize = maximize

    def _dominates(self, a: Assessment, b: Assessment) -> bool:
        """a 支配 b: 所有指标 >= 且至少一个 >。缺指标记 0。"""
        ge = all(_metric_get(a, m) >= _metric_get(b, m) for m in self.maximize)
        gt = any(_metric_get(a, m) > _metric_get(b, m) for m in self.maximize)
        return ge and gt

    def select(self, rows: list, k: int) -> list:
        fronts = []
        for c, a in [(r[0], r[1]) for r in rows]:
            if not any(self._dominates(r[1], a) for r in rows if r[0] is not c):
                fronts.append(c)
        return fronts[:k]


class RandomFilter:
    """随机选择 top-k — 闭环 vs 纯随机对照实验 (E7) 的基线 Filter。

    score 委托给内部真实 filter (保持 policy 反馈语义不变), 但 select
    随机抽 k 个 — 等价于"无评估反馈的盲变异走"。
    """
    def __init__(self, inner, rng_seed: int = 0):
        self.inner = inner
        self.rng = random.Random(rng_seed)

    def score(self, a: Assessment) -> float:
        return self.inner.score(a) if hasattr(self.inner, "score") else 0.0

    def select(self, rows: list, k: int) -> list:
        pool = [r[0] for r in rows]
        if len(pool) <= k:
            return pool
        return self.rng.sample(pool, k)


class NegativeControlFilter:
    """FS-001 负对照过滤 (Filter 接口): select 前先剔除已证伪形态。

    经验承载: docs/fault_signature_playbook.md 负对照清单的执行体。
    与 mutators.NegativeControlFilter 同源逻辑; 本类适配 pipeline 的
    select(rows, k) 协议 (rows 元素需有 .cand 或就是 Candidate)。
    """
    def __init__(self, fs_ids=("FS-001",), inner=None):
        from tools.sdc_pipeline.fault_signatures import negative_control_tags
        self.tags = negative_control_tags() if not fs_ids else set()
        if fs_ids:
            from tools.sdc_pipeline import fault_signatures
            for fid in fs_ids:
                self.tags.update(
                    fault_signatures.get(fid)["negative_controls"])
        self.inner = inner

    def _reject(self, cand) -> bool:
        asm = getattr(cand, "source_asm", "")
        has_load = ("ldr" in asm) or ("ldp" in asm)
        tags = getattr(cand, "structure_tags", [])
        if not has_load and any("fs001" in t for t in tags):
            return True  # fs001 定向管线里的纯寄存器链 = 已证伪形态
        return False

    def score(self, a):
        # score 透传内层 (无内层时给 0 — 本过滤器的职责是拦截, 不是排序)
        return self.inner.score(a) if self.inner is not None else 0.0

    def select(self, rows, k):
        cand_of = lambda r: getattr(r, "cand", r)
        kept = [r for r in rows if not self._reject(cand_of(r))]
        dropped = len(rows) - len(kept)
        if dropped:
            import sys
            print(f"[NegativeControlFilter] 拦截 {dropped} 个已证伪形态候选",
                  file=sys.stderr)
        if self.inner is not None:
            return self.inner.select(kept, k)
        return [r[0] for r in kept[:k]]

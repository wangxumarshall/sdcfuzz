#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""filters.py — 多指标筛选器 (sdc_pipeline Filter 层)。

- WeightedFilter: 指标加权和降序取 top-k
- ParetoFilter:  非支配排序 (NSGA 风格第一层), scheme §5.1 跨结构联合优化的
  "Pareto 最优序列集" 的高功耗/高覆盖筛选实现
"""
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

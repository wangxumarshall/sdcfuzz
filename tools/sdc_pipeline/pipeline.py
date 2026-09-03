#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""pipeline.py — 轻量闭环编排器 (sdc_pipeline 首里程碑 M1)。

Gen → Assess → Filter → Feedback 循环:
  每代: policy 选 mutators → 变异 → 评估器池评估 → Filter 选 top-k
        进入下代种子池 → Vault 全程落盘

policy = RL 接入口 (Gym 语义): choose_mutators(state) 相当于 action,
observe(generation, mutator_scores, baseline) 相当于 reward 反馈。
第一版 HillClimbPolicy (启发式权重调整), 后续换 RL policy 对象即可,
框架其余不变 — scheme §5.2 "可演进" 的落点。

gem5+CHAOS 检出率验证 (validate 阶段) 由 validator 参数接入 (Task 6/7),
无 validator 时为纯 Unicorn 轻量闭环 (先轻后重策略)。
"""
import random
from dataclasses import dataclass, field

from tools.sdc_pipeline.vault import Vault, Assessment


@dataclass
class GenerationReport:
    generation: int
    produced: int
    metrics_mean: dict = field(default_factory=dict)
    mutator_scores: dict = field(default_factory=dict)


@dataclass
class PipelineReport:
    generations: list = field(default_factory=list)
    final_top: list = field(default_factory=list)


class HillClimbPolicy:
    """启发式策略: 上代各 mutator 的 (子代指标均值 - 全体基线) 反馈调权。

    score 高的 mutator 权重 × (1 + lr*score), 再归一。这是 RL policy 的
    占位实现 — 接口与 RL 策略对象完全同构 (choose_mutators / observe)。
    """
    def __init__(self, mutator_names: list, lr: float = 0.5):
        self.names = list(mutator_names)
        self.lr = lr
        self.weights = {m: 1.0 for m in self.names}

    def observe(self, generation: int, mutator_scores: dict, baseline: float):
        """mutator_scores: {mutator_name: 该 mutator 子代指标均值};
        baseline: 全体子代均值。相对提升→加权。"""
        for m, s in mutator_scores.items():
            if m in self.weights:
                self.weights[m] *= (1.0 + self.lr * (s - baseline))
        # 归一并保持 >0
        total = sum(self.weights.values()) or 1.0
        for m in self.weights:
            self.weights[m] = max(0.05, self.weights[m] / total)

    def choose_mutators(self, rng: random.Random) -> list:
        """全部 mutator 参与 (权重影响下一代选择, 第一版不丢弃)。"""
        return list(self.names)


class Pipeline:
    def __init__(self, seeds: list, mutators: list, evaluators: list,
                 filt, vault: Vault, policy, rng_seed: int = 42,
                 validator=None):
        self.seeds = list(seeds)
        self.mutators = list(mutators)
        self.evaluators = list(evaluators)
        self.filt = filt
        self.vault = vault
        self.policy = policy
        self.rng = random.Random(rng_seed)
        self.validator = validator  # Task 6/7: gem5_runner 注入验证器 (可选)

        for s in self.seeds:
            self.vault.put_candidate(s)

    def _assess(self, cand) -> Assessment:
        metrics = {}
        for ev in self.evaluators:
            metrics.update(ev.evaluate(cand))
        return Assessment(ident=cand.ident, metrics=metrics,
                          evaluator="+".join(ev.name for ev in self.evaluators))

    def run(self, generations: int, per_gen_mutations: int, top_k: int) -> PipelineReport:
        report = PipelineReport()
        pool = list(self.seeds)  # 当前代种子池
        for gen in range(1, generations + 1):
            chosen = self.policy.choose_mutators(self.rng)
            mutators = [m for m in self.mutators if m.name in chosen]
            # Gen: 变异
            children = []
            for m in mutators:
                for _ in range(per_gen_mutations):
                    parent = self.rng.choice(pool)
                    kids = m.mutate(parent, self.rng)
                    children += kids[:1]  # 每次变异取 1 子代 (控量)
            for c in children:
                self.vault.put_candidate(c)
            # Assess: 评估
            assessed = [(c, self._assess(c)) for c in children]
            for _, a in assessed:
                self.vault.put_assessment(a)
            # Feedback: policy 观察 (mutator 分组均值 vs 基线)
            all_scores = [self.filt.score(a) for _, a in assessed]
            baseline = sum(all_scores) / len(all_scores) if all_scores else 0.0
            mut_scores = {}
            for m in mutators:
                kids_of_m = [a for c, a in assessed
                             if c.origin == f"mutate:{m.name}"]
                if kids_of_m:
                    mut_scores[m.name] = sum(self.filt.score(a) for a in kids_of_m) / len(kids_of_m)
            self.policy.observe(gen, mut_scores, baseline)
            # Filter: top-k 进入下代
            if assessed:
                pool = self.filt.select(assessed, top_k)
            # 报告
            metrics_mean = {}
            for _, a in assessed:
                for mk, mv in a.metrics.items():
                    metrics_mean.setdefault(mk, []).append(mv)
            metrics_mean = {k: sum(v) / len(v) for k, v in metrics_mean.items()}
            report.generations.append(GenerationReport(
                generation=gen, produced=len(children),
                metrics_mean=metrics_mean, mutator_scores=mut_scores))
        # 终榜 (Vault 全量 top)
        report.final_top = self.vault.top_by(
            next(iter(self.evaluators[0].evaluate(pool[0]).keys()))
            if pool else "ace_proxy", 5)
        return report

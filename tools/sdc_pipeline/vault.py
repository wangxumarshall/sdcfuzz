#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""vault.py — Vault JSONL 持久层 + 血缘 (sdc_pipeline R5 解法)。

scheme.md Layer 2 "Vault 持久化 + 血缘" 的第一版实现:
- candidates.jsonl  / assessments.jsonl 两个追加式 JSONL 文件
- 幂等 put (按 ident / ident+evaluator 去重)
- 血缘回溯 lineage() 沿 parents 链回到 seed
- top_by(metric) 供 Filter / 报告查询

选 JSONL 而非 SQLite: 与现有实验 JSON 输出一致、可 git diff、零依赖。
"""
import json
import os
from dataclasses import dataclass, asdict

from tools.sdc_pipeline.candidate import Candidate


@dataclass
class Assessment:
    """一次评估记录: 候选 ident + 指标 dict + 评估器名 (+可选 gem5 验证结果)。"""
    ident: str
    metrics: dict
    evaluator: str
    validated: dict | None = None  # 第二阶段: {bit: {...}, struct: {...}}


class Vault:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.cand_path = os.path.join(root, "candidates.jsonl")
        self.assess_path = os.path.join(root, "assessments.jsonl")
        # 内存索引: ident → 记录; (ident, evaluator) → 记录
        self._cands: dict[str, dict] = {}
        self._assess: dict[tuple, dict] = {}
        self._children: dict[str, list[str]] = {}
        self._load()

    # ---- 持久化 ----
    def _load(self):
        if os.path.exists(self.cand_path):
            with open(self.cand_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self._cands[rec["ident"]] = rec
        if os.path.exists(self.assess_path):
            with open(self.assess_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    self._assess[(rec["ident"], rec["evaluator"])] = rec

    def _append(self, path: str, rec: dict):
        with open(path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---- Candidate ----
    def put_candidate(self, c: Candidate):
        if c.ident in self._cands:
            return  # 幂等
        rec = {"ident": c.ident, "source_asm": c.source_asm,
               "regs_init": {str(k): v for k, v in c.regs_init.items()},
               "parents": c.parents, "origin": c.origin,
               "structure_tags": c.structure_tags}
        self._cands[c.ident] = rec
        for p in c.parents:
            self._children.setdefault(p, []).append(c.ident)
        self._append(self.cand_path, rec)

    def get(self, ident: str) -> Candidate | None:
        rec = self._cands.get(ident)
        if rec is None:
            return None
        return Candidate(ident=rec["ident"], source_asm=rec["source_asm"],
                         code_bytes=b"",  # bytes 不持久化 (可由 asm 重编译)
                         regs_init={int(k): v for k, v in rec["regs_init"].items()},
                         parents=rec["parents"], origin=rec["origin"],
                         structure_tags=rec["structure_tags"])

    def count_candidates(self) -> int:
        return len(self._cands)

    def children(self, ident: str) -> list[str]:
        return list(self._children.get(ident, []))

    def lineage(self, ident: str) -> list[str]:
        """回溯血缘链: [self, parent, grandparent, ..., seed]。"""
        chain = []
        cur = ident
        seen = set()
        while cur and cur in self._cands and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            parents = self._cands[cur]["parents"]
            cur = parents[0] if parents else None
        return chain

    # ---- Assessment ----
    def put_assessment(self, a: Assessment):
        key = (a.ident, a.evaluator)
        if key in self._assess:
            return  # 幂等 (同候选同评估器)
        rec = {"ident": a.ident, "metrics": a.metrics,
               "evaluator": a.evaluator, "validated": a.validated}
        self._assess[key] = rec
        self._append(self.assess_path, rec)

    def count_assessments(self) -> int:
        return len(self._assess)

    def top_by(self, metric: str, k: int) -> list[tuple[str, float]]:
        """按指标降序取前 k (缺该指标的记录跳过)。"""
        rows = []
        for (ident, _ev), rec in self._assess.items():
            if metric in rec["metrics"]:
                rows.append((ident, rec["metrics"][metric]))
        rows.sort(key=lambda x: -x[1])
        return rows[:k]

# tools/sdc_experiment/correlation.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""correlation.py — 跨层 (Sim→HW) 统计关联分析 (E5)。

诚实定位: 健康硅片上真 SDC 稀少, 无法直接关联"仿真 diverge 率 vs 真机 SDC 率"。
本模块关联的是用例组粒度的执行健康度: 仿真侧 (clean_diverge/masked 率)
vs 真机侧 (runnable/runaway/misbehave 率)。主检验 = Spearman + 独立性置换检验。
"""
import math, random

def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks

def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return (float("nan"), float("nan"))
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return (float("nan"), float("nan"))
    r = sxy / math.sqrt(sxx * syy)
    # t 近似 p (n>=10 时可用; 报告同时给置换检验 p)
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return (r, t)

def spearman(xs, ys):
    rx, ry = _rank(xs), _rank(ys)
    return pearson(rx, ry)

def permutation_test(xs, ys, n: int = 10000, seed: int = 42):
    """独立性置换检验: 打乱 ys, 统计 |perm_corr| >= |obs_corr| 的比例。"""
    if len(xs) < 3:
        return float("nan")
    obs, _ = spearman(xs, ys)
    if math.isnan(obs):
        return float("nan")
    rng = random.Random(seed)
    ys2 = list(ys)
    extreme = 0
    for _ in range(n):
        rng.shuffle(ys2)
        r, _ = spearman(xs, ys2)
        if not math.isnan(r) and abs(r) >= abs(obs) - 1e-12:
            extreme += 1
    return (extreme + 1) / (n + 1)

def analyze(sim_rows, hw_rows, sim_key="sim_diverge_rate", hw_key="hw_runaway_rate",
            n_perm=10000):
    by_group_h = {r["group"]: r for r in hw_rows}
    pairs = [(r[sim_key], by_group_h[r["group"]][hw_key])
             for r in sim_rows if r["group"] in by_group_h]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if len(pairs) < 10:
        return {"n": len(pairs), "verdict": "INSUFFICIENT_SAMPLES(<10, 诚实记录)",
                "note": "用例组不足 10, 不做显著性声明"}
    rho, t = spearman(xs, ys)
    p = permutation_test(xs, ys, n=n_perm)
    verdict = ("SIGNIFICANT" if p < 0.05 else "NOT_SIGNIFICANT(诚实记录)")
    return {"n": len(pairs), "sim_key": sim_key, "hw_key": hw_key,
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else None,
            "permutation_p": round(p, 5), "verdict": verdict,
            "note": "组粒度执行健康度关联; gem5 O3 ≠ TSV110 RTL; 真SDC关联需检出样本后再做"}

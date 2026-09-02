# tools/sdc_experiment/test_correlation.py
#!/usr/bin/env python3
"""correlation 纯函数测试。运行: python3 tools/sdc_experiment/test_correlation.py"""
import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.correlation import pearson, spearman, permutation_test, analyze

def test_pearson():
    xs = [1, 2, 3, 4, 5]
    r, _ = pearson(xs, [2, 4, 6, 8, 10])
    assert abs(r - 1.0) < 1e-9
    r2, _ = pearson(xs, [10, 8, 6, 4, 2])
    assert abs(r2 + 1.0) < 1e-9
    print("PASS test_pearson")

def test_spearman():
    # 单调非线性 → spearman=1, pearson<1
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 25]
    rho, _ = spearman(xs, ys)
    assert abs(rho - 1.0) < 1e-9
    print("PASS test_spearman")

def test_permutation():
    rng = random.Random(7)
    xs = list(range(20))
    ys_strong = [x * 2 + rng.random() * 0.1 for x in xs]     # 强相关
    ys_none = [rng.random() for _ in xs]                     # 无相关
    p1 = permutation_test(xs, ys_strong, n=2000, seed=42)
    p2 = permutation_test(xs, ys_none, n=2000, seed=42)
    assert p1 < 0.01, f"强相关应 p<0.01, got {p1}"
    assert p2 > 0.05, f"无相关应 p>0.05, got {p2}"
    print(f"PASS test_permutation: p_strong={p1:.4f}, p_none={p2:.3f}")

def test_analyze():
    sim = [{"group": f"g{i}", "sim_diverge_rate": i / 10} for i in range(10)]
    hw = [{"group": f"g{i}", "hw_runaway_rate": 0.5 - i / 20} for i in range(10)]
    r = analyze(sim, hw, sim_key="sim_diverge_rate", hw_key="hw_runaway_rate")
    assert r["n"] == 10
    assert r["spearman_rho"] < -0.9   # 完美负相关
    assert r["permutation_p"] < 0.05
    print("PASS test_analyze")

if __name__ == "__main__":
    test_pearson(); test_spearman(); test_permutation(); test_analyze()
    print("ALL PASS")

# tools/sdc_experiment/test_sim_sweep.py
#!/usr/bin/env python3
"""sim_sweep 纯函数单元测试 (不跑 gem5)。运行: python3 tools/sdc_experiment/test_sim_sweep.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.sim_sweep import wilson, fisher_exact, classify_output

def test_wilson():
    # 41/500 的 Wilson 95% CI (对照 memory paper2-bbit-honest-recount: 8.2%)
    lo, p, hi = wilson(41, 500)
    assert abs(p - 0.082) < 1e-9
    assert lo < 0.082 < hi
    # 0/500: rule of 3 上界 ≈ 3/500
    lo0, p0, hi0 = wilson(0, 500)
    assert p0 == 0.0 and abs(hi0 - 3/500) < 0.005
    print(f"PASS test_wilson: 41/500 -> [{lo:.4f}, {hi:.4f}]")

def test_fisher_exact():
    # D13=41/500 vs B=40/500 → 不显著 (ratio 1.02)
    orr, p = fisher_exact(41, 459, 40, 460)
    assert p > 0.05, f"p={p} 应不显著"
    # 极端: 50/100 vs 0/100 → 显著
    orr2, p2 = fisher_exact(50, 50, 0, 100)
    assert p2 < 0.01, f"p2={p2} 应显著"
    print(f"PASS test_fisher_exact: p={p:.4f}, p2={p2:.2e}")

def test_classify():
    g = "SUM=123 CRC=abc"
    assert classify_output("SUM=123 CRC=abc", g) == "masked"
    assert classify_output("SUM=999 CRC=xyz", g) == "clean_diverge"
    assert classify_output("SUM=999 Exiting", g) == "exit_diverge"
    assert classify_output("", g) == "no_output"
    assert classify_output(None, g) == "no_output"
    print("PASS test_classify")

if __name__ == "__main__":
    test_wilson(); test_fisher_exact(); test_classify()
    print("ALL PASS")

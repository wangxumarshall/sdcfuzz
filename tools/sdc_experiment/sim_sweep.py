# tools/sdc_experiment/sim_sweep.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sim_sweep.py — 仿真层故障注入 sweep 驱动 (E1/E2), 100% 本机执行。

统一驱动 A/B/D13 等工作组在本机 gem5-CHAOS 上做 bit-flip / byte_lane_skew
注入, 统计 diverge 率 + Wilson CI + Fisher 精确检验。判定逻辑与既有
scripts/gem5_sweep_abcd.py / d13_sweep.py 逐字段一致 (可交叉校验)。

并行 (--jobs, 控制器裁决新增): run i 的 fault-clock 由 Random(seed) 在
dispatch 前按 run 序一次性抽完, 每 run 的 --rng-seed = seed + i, 故并行度
不改变任何 run 的参数 (可复现性不变)。MCE 红线: gem5 并行 ≤ 4。
"""
import argparse, json, math, os, random, shutil, subprocess, sys
from concurrent.futures import ProcessPoolExecutor

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from tools.sdc_experiment.gem5_env import (GEM5_OPT, TAISHAN_SCRIPT,
                                           GROUPS, local_gem5_env)

MAX_JOBS = 4  # MCE 红线: gem5 注入并行上限 (本机 128c, 2-4 路安全)

def wilson(k: int, n: int, z: float = 1.96):
    """Wilson score CI。k=0 时上界≈rule-of-3 (3/n)。"""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - half), p, min(1.0, center + half))

def _log_comb(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

def fisher_exact(a: int, b: int, c: int, d: int):
    """2x2 Fisher 精确检验 (双侧, 超几何), 无 scipy。返回 (odds_ratio, p)。
    表: [[a,b],[c,d]] = [[diverge_D, total_D-diverge_D],
                          [diverge_B, total_B-diverge_B]]

    容差用相对比较 (终审修复): p_obs 极小时 (如 5.6e-20), 绝对容差 +1e-12 会
    把整条尾部都计入 → p 虚高几个数量级 (E2-struct 曾因此记 0.0/1.6e-12)。
    逐 k 在 log 空间比较 (prob_log(k) <= log(p_obs) + log1p(1e-9)), 避免
    exp 下溢到 0 误入求和集; p_two 用 log-sum-exp 聚合, 极端尾部不丢精度。"""
    n = a + b + c + d
    row1, col1 = a + b, a + c
    def prob_log(k):
        return _log_comb(col1, k) + _log_comb(n - col1, row1 - k) \
               - _log_comb(n, row1)
    log_eps = math.log1p(1e-9)   # 相对容差 1e-9 (log 空间加法)
    p_obs_log = prob_log(a)
    lo, hi = max(0, row1 - (n - col1)), min(row1, col1)
    logs = [prob_log(k) for k in range(lo, hi + 1)
            if prob_log(k) <= p_obs_log + log_eps]
    # log-sum-exp: m + log(sum(exp(x-m))), m = max 防 overflow/underflow
    m = max(logs)
    p_two = math.exp(m + math.log(sum(math.exp(x - m) for x in logs)))
    odds = (a * d) / (b * c) if b and c else float("inf")
    return (odds, min(1.0, p_two))

def classify_output(workload_line, golden: str) -> str:
    if not workload_line:
        return "no_output"
    if workload_line == golden:
        return "masked"
    if "Exiting" in workload_line:
        return "exit_diverge"
    return "clean_diverge"

def _execute_run(task):
    """跑一次 gem5 注入并判定 (串行/进程池 worker 共用)。
    task = (i, fc, group, mode, seed, outdir); 返回分类字符串。
    超时 / gem5 abort (Page table fault panic) → no_output (既有 sweep 语义)。"""
    i, fc, group, mode, seed, outdir = task
    g = GROUPS[group]
    env = local_gem5_env()
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5_OPT, "-r", "-e", "--silent-redirect", "-d", outdir,
           TAISHAN_SCRIPT, "--binary", g["binary"], "--mode", "inject",
           "--first-clock", str(fc), "--max-faults", "1",
           "--probability", "1.0", "--rng-seed", str(seed + i)]
    if mode == "struct":
        cmd += ["--injector", "lsq_fwd", "--structural-fault", "byte_lane_skew"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    except subprocess.TimeoutExpired:
        pass   # → no_output (与既有 sweep 语义一致)
    wl = ""
    simout = os.path.join(outdir, "simout.txt")
    if os.path.exists(simout):
        for line in open(simout, errors="replace"):
            if "SUM=" in line:
                wl = line.strip()
                break
    # 每 run 目录只留判定证据, 清掉大文件防磁盘膨胀 (stats/config)
    for junk in ("stats.txt", "config.ini", "config.json", "citations.bib"):
        p = os.path.join(outdir, junk)
        if os.path.exists(p):
            os.unlink(p)
    return classify_output(wl, g["golden"])

def run_group(group: str, mode: str, n_runs: int, seed: int, cfg,
              jobs: int = 1) -> dict:
    """对一工作组在本机 gem5 跑 n_runs 次注入。mode: bit|struct。
    jobs: 并行 gem5 进程数 (默认 1=串行; MCE 红线 1..MAX_JOBS)。
    可复现性: 全部 fault-clock 由 Random(seed) 按 run 序在 dispatch 前抽完,
    每 run --rng-seed = seed + i → jobs 不改变任何 run 参数。"""
    if not 1 <= jobs <= MAX_JOBS:
        raise ValueError(f"jobs={jobs} 越界 (MCE 红线: 1..{MAX_JOBS})")
    g = GROUPS[group]
    roi_lo, roi_hi = int(g["nc"] * cfg.roi[0]), int(g["nc"] * cfg.roi[1])
    # 关键 (控制器裁决): fault-clock 在 dispatch 前按 run 序一次性抽完
    rng = random.Random(seed)
    fault_clocks = [rng.randint(roi_lo, roi_hi) for _ in range(n_runs)]
    out_root = os.path.join("output", "experiments", cfg.experiment_id,
                            "runs", f"{group}_{mode}")
    shutil.rmtree(out_root, ignore_errors=True)
    os.makedirs(out_root, exist_ok=True)
    tasks = [(i, fault_clocks[i], group, mode, seed,
              os.path.join(out_root, f"run_{i:03d}")) for i in range(n_runs)]
    if jobs == 1:
        classifications = [_execute_run(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            classifications = list(ex.map(_execute_run, tasks))
    counts = {"clean_diverge": 0, "masked": 0, "exit_diverge": 0, "no_output": 0}
    for c in classifications:
        counts[c] += 1
    n = sum(counts.values())
    k = counts["clean_diverge"]
    lo, p, hi = wilson(k, n, cfg.wilson_z)
    return {"group": group, "mode": mode, "n": n, **counts,
            "diverge_rate": round(p, 4), "wilson_low": round(lo, 4),
            "wilson_high": round(hi, 4), "seed": seed, "jobs": jobs,
            "host": "local-0103-gem5", "gem5_note": "gem5 O3 model, not TSV110 RTL"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, choices=list(GROUPS))
    ap.add_argument("--mode", required=True, choices=["bit", "struct"])
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--exp", default="exp00")
    ap.add_argument("--jobs", type=int, default=1,
                    help=f"并行 gem5 进程数, 默认 1=串行 (MCE 红线上限 {MAX_JOBS})")
    a = ap.parse_args()
    if not 1 <= a.jobs <= MAX_JOBS:
        ap.error(f"--jobs 必须在 1..{MAX_JOBS} 之间 (MCE 红线)")
    from tools.sdc_experiment.experiment_config import default_config
    cfg = default_config(a.exp)
    res = run_group(a.group, a.mode, a.runs, a.seed, cfg, jobs=a.jobs)
    os.makedirs(cfg.out_dir, exist_ok=True)
    out_json = cfg.out_dir / f"sim_{a.group}_{a.mode}.json"
    json.dump(res, open(out_json, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"saved -> {out_json}")

if __name__ == "__main__":
    main()

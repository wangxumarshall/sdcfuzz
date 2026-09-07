#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sdcbench_eval.py — gem5 批量 SDC 率评估器

协议 (sdcbench_gen.py 序列专用):
  1. golden 跑一次 (无注入) → 16-hex checksum + numCycles
  2. ROI 窗口估算: asm 块 ≈ [0.25C, 0.75C] (startup ~5k cycles 固定开销 + put_hex 尾巴)
     注入点 first_clock = 0.5 × numCycles
  3. 注入采样: arch_frontend 模式, x0-x7 各一次 (n=8), bit_flip, max_faults=1
  4. 判定: checksum 非 golden 且非空 = SDC; 空 = CRASH; 等 golden = MASKED
  SDC 检出率 = SDC / (SDC+MASKED+CRASH)  [CRASH 也是"可检测故障", 但分开计]

用法: sdcbench_eval.py <manifest.json> <out_report.json> [--jobs 8] [--limit N] [--only ids]
"""
import os, sys, json, re, subprocess, argparse, shutil, tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_experiment.gem5_env import GEM5_OPT as GEM5, CHAOS_SE_SCRIPT as CFG
ENV = dict(os.environ)
ENV["LD_LIBRARY_PATH"] = "/home/sdc/gem5-deps/py/usr/lib64:/home/sdc/gem5-deps/usr/lib64:" + ENV.get("LD_LIBRARY_PATH", "")
WORK_BASE = "/tmp/sdcbench_eval"
CHECKSUM_RE = re.compile(r"^([0-9a-f]{16})$", re.M)


def run_gem5(bin_path, outdir, extra_args, timeout=180):
    """跑一次 gem5, 返回 (checksum|None, num_cycles|None, fault_log_lines)."""
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5, "-re", "--silent-redirect", "-d", outdir, CFG,
           "--cmd", bin_path, "--cpu", "O3"] + extra_args
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, env=ENV)
    except subprocess.TimeoutExpired:
        return None, None, []
    cs = None
    simout = os.path.join(outdir, "simout.txt")
    if os.path.exists(simout):
        m = CHECKSUM_RE.search(open(simout, errors="replace").read())
        if m:
            cs = m.group(1)
    cycles = None
    stats = os.path.join(outdir, "stats.txt")
    if os.path.exists(stats):
        for line in open(stats, errors="replace"):
            if "numCycles" in line and "cpu cycles" in line:
                cycles = int(line.split()[1])
                break
    flog = os.path.join(outdir, "fault_injections.log")
    n_inj = 0
    if os.path.exists(flog):
        n_inj = sum(1 for _ in open(flog, errors="replace"))
    return cs, cycles, n_inj


def eval_sequence(entry, work_root):
    """评估单条序列, 返回 dict."""
    name = entry["name"]
    d = os.path.join(work_root, name)
    if os.path.exists(d):
        shutil.rmtree(d)
    # 1. golden
    gcs, gcycles, _ = run_gem5(entry["bin"], os.path.join(d, "golden"), [])
    if gcs is None or gcycles is None:
        return {"name": name, "status": "GOLDEN_FAIL", "golden": gcs, "cycles": gcycles}
    # 2. 注入: x0-x7, first_clock = ROI 中段
    fc = int(gcycles * 0.75)
    result = {"name": name, "id": entry["id"], "golden": gcs, "cycles": gcycles,
              "first_clock": fc, "inj": {"sdc": 0, "masked": 0, "crash": 0, "noinj": 0}}
    for arch in range(8):
        cs, _, n_inj = run_gem5(
            entry["bin"], os.path.join(d, f"inj_a{arch}"),
            ["--chaos_phys", "--phys_mode", "arch_frontend",
             "--phys_target_arch", str(arch),
             "--fault_type", "bit_flip", "--first_clock", str(fc),
             "--max_faults", "1", "--rng_seed", str(1000 + entry["id"] * 10 + arch)])
        if n_inj == 0:
            result["inj"]["noinj"] += 1
        elif cs == gcs:
            result["inj"]["masked"] += 1
        elif cs is None:
            result["inj"]["crash"] += 1
        else:
            result["inj"]["sdc"] += 1
    n = result["inj"]["sdc"] + result["inj"]["masked"] + result["inj"]["crash"] + result["inj"]["noinj"]
    denom = result["inj"]["sdc"] + result["inj"]["masked"] + result["inj"]["crash"]
    result["sdc_rate"] = result["inj"]["sdc"] / denom if denom else 0.0
    result["detect_rate"] = (result["inj"]["sdc"] + result["inj"]["crash"]) / denom if denom else 0.0
    result["status"] = "OK"
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("report")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", type=str, default="", help="comma-separated ids")
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    if args.only:
        ids = {int(x) for x in args.only.split(",")}
        manifest = [e for e in manifest if e["id"] in ids]
    if args.limit:
        manifest = manifest[:args.limit]

    work_root = os.path.join(WORK_BASE, "w")
    os.makedirs(work_root, exist_ok=True)

    # 每序列内部串行 (9 次 gem5), 序列间并行 jobs 个线程 → gem5 并发 = jobs
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(eval_sequence, e, work_root): e for e in manifest}
        done = 0
        for f in futs:
            pass
        import concurrent.futures as cf
        for fut in cf.as_completed(futs):
            try:
                r = fut.result()
            except Exception as exc:
                r = {"name": futs[fut]["name"], "status": f"EXC:{exc}"}
            results.append(r)
            done += 1
            if done % 10 == 0:
                ok = [x for x in results if x.get("status") == "OK"]
                print(f"[{done}/{len(manifest)}] evaluated, avg_sdc_rate="
                      f"{sum(x['sdc_rate'] for x in ok)/max(1,len(ok)):.2f}", flush=True)
    # 清理工作目录 (省盘)
    shutil.rmtree(work_root, ignore_errors=True)
    results.sort(key=lambda r: r.get("id", 0))
    json.dump(results, open(args.report, "w"), indent=1)
    ok = [x for x in results if x.get("status") == "OK"]
    print(f"Report: {args.report}")
    print(f"OK: {len(ok)}/{len(results)}  avg SDC rate: "
          f"{sum(x['sdc_rate'] for x in ok)/max(1,len(ok)):.3f}")


if __name__ == "__main__":
    main()

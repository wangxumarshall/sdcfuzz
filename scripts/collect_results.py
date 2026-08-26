#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""collect_results.py — 拉取各单板扫描状态 + 终态日志, 汇总到 0103

用户要求'获取状态和结果回来'。本脚本:
  1. 从每台单板拉取 scan.log (orchestrator 完整输出)
  2. 解析 SIGSEGV 噪声 (outside-snap, 非 SDC) 与 SDC 命中 (mismatch/SNAPSHOT_FAILED)
  3. 聚合结构化结果到 output/distributed/
  4. 若检出 SDC, 输出触发 snapshot 供演化闭环 (Patch 6) 回灌

用法: collect_results.py [--boards name=ip,...]
"""
import os, sys, re, json, argparse
sys.path.insert(0, os.path.dirname(__file__))
from ssh_lib import ssh, scp

DEFAULT_BOARDS = {
    "0101": "172.168.177.97",
    "0102": "172.168.160.42",
    "0103": "172.168.59.158",
}
REMOTE_CORPUS = "/sdc_corpus"
OUT = "output/distributed"

def parse_log(text):
    """从 orchestrator 日志解析 SDC 命中与噪声。
    满负载时 runner 日志会交织, 须精确匹配结构化失败标记。
    真正的 SDC = snapshot 执行失败 (end-state mismatch), 形如:
      'Snapshot [hash] failed, outcome = ...' (非 SIGSEGV/SIGTERM 杀的)
    SIGSEGV-outside-snap / SIGTERM(timeout) 是噪声, 不算 SDC。"""
    sigsegv_outside = len(re.findall(r'SIGSEGV while outside of snap', text))
    sigterm = len(re.findall(r'SIGTERM', text))
    # SDC 命中: 'Snapshot [hash] failed, outcome' 行 (排除被信号杀的)
    # 满负载交织日志里, 行可能跨多行; 用 findall 计 'failed, outcome' 出现次数
    sdc_markers = re.findall(r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome', text)
    # 进一步: 真正 end-state mismatch 的 outcome 通常含 'mismatch' 或非信号
    sdc_hits = [m for m in sdc_markers if 'signal' not in m.lower() and 'SIG' not in m]
    return {
        "sigsegv_noise": sigsegv_outside,
        "sigterm": sigterm,
        "sdc_hits": len(sdc_hits),
        "sdc_details": sdc_hits[:10],
    }

def collect_one(name, ip, all_results):
    """拉取单板 scan.log 并解析。"""
    out_dir = f"{OUT}/logs"
    os.makedirs(out_dir, exist_ok=True)
    local_log = f"{out_dir}/{name}.scan.log"
    # 0103 是本机, distributed_scan 本地分支日志在 output/distributed/0103.scan.log
    if ip == "172.168.59.158":
        local_src = "output/distributed/0103.scan.log"
        try:
            with open(local_src) as f:
                text = f.read()
            with open(local_log, "w") as f:
                f.write(text)
        except FileNotFoundError:
            text = ""
    else:
        # 远程拉取
        try:
            text = ssh(ip, f"cat {REMOTE_CORPUS}/scan.log 2>/dev/null", timeout=30)
            with open(local_log, "w") as f:
                f.write(text)
        except Exception as e:
            text = ""
            all_results[name] = {"ip": ip, "error": str(e)}
            return
    stats = parse_log(text)
    all_results[name] = {"ip": ip, "log_file": local_log, **stats}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", default="", help="自定义 (name=ip,...)")
    args = ap.parse_args()
    boards = dict(p.split("=") for p in args.boards.split(",")) if args.boards else DEFAULT_BOARDS

    os.makedirs(OUT, exist_ok=True)
    results = {}
    for name, ip in boards.items():
        print(f"拉取 {name} ({ip})...")
        collect_one(name, ip, results)

    print(f"\n=== 扫描结果汇总 ===")
    total_sdc = 0
    for name, r in results.items():
        sdc = r.get("sdc_hits", 0)
        noise = r.get("sigsegv_noise", 0)
        total_sdc += sdc
        print(f"  {name} ({r.get('ip')}): SDC命中={sdc} | SIGSEGV噪声={noise} | SIGTERM(timeout)={r.get('sigterm',0)}")
        if r.get("sdc_details"):
            print(f"    详情: {r['sdc_details'][0][:120]}")
    print(f"  总 SDC 命中: {total_sdc}")

    with open(f"{OUT}/results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  落盘: {OUT}/results.json + {OUT}/logs/*.scan.log")

    if total_sdc > 0:
        print(f"\n[!] 检出 {total_sdc} 个 SDC, 触发演化闭环 (scripts/sdc_evolve.sh)")

if __name__ == "__main__":
    main()

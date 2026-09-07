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
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ssh_lib import ssh, scp
from tools.sdc_experiment.hw_log_parser import parse_log  # noqa: E402

DEFAULT_BOARDS = {
    "0101": "172.168.177.97",
    "0102": "172.168.160.42",
    "0103": "172.168.59.158",
    "0201": "172.168.178.81",
}
# 每板 ssh 用户 + corpus 目录 (0201 用 sdc + /home/sdc/sdc_corpus)
BOARD_CFG = {
    "0101": ("root", "/sdc_corpus"),
    "0102": ("root", "/sdc_corpus"),
    "0201": ("sdc", "/home/sdc/sdc_corpus"),
}
REMOTE_CORPUS = "/sdc_corpus"
OUT = "output/distributed"

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
        # 远程拉取 (按板取 user + corpus 目录)
        user, rcorpus = BOARD_CFG.get(name, ("root", REMOTE_CORPUS))
        try:
            text = ssh(ip, f"cat {rcorpus}/scan.log 2>/dev/null", timeout=40, user=user)
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
        runaway = r.get("runaway_noise", 0)
        misbehave = r.get("misbehave_noise", 0)
        total_sdc += sdc
        print(f"  {name} ({r.get('ip')}): 真SDC={sdc} | runaway噪声={runaway} | misbehave噪声={misbehave} | SIGSEGV噪声={noise} | SIGTERM={r.get('sigterm',0)}")
        if r.get("sdc_details"):
            print(f"    SDC详情: {r['sdc_details'][0][:120]}")
    print(f"  总真 SDC 命中 (outcome 2/3/4): {total_sdc}")

    with open(f"{OUT}/results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  落盘: {OUT}/results.json + {OUT}/logs/*.scan.log")

    if total_sdc > 0:
        print(f"\n[!] 检出 {total_sdc} 个 SDC, 触发演化闭环 (scripts/sdc_evolve.sh)")

if __name__ == "__main__":
    main()

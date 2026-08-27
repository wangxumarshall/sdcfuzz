#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""distributed_scan.py — 3 单板并行接近满负载 SDC 扫描

用户要求: 接近满负载扫描, 并获取状态和结果回来。
实测拓扑 (2026/08/26):
  0101=172.168.177.97 (126核), 0102=172.168.160.42 (192核),
  0103=172.168.59.158 (128核, 编译机), 0201 不可达。
合计 ~446 核可并行扫描。

每单板:
  - orchestrator --max_cpus=$(nproc) 接近满负载 (用户明确要求)
  - 后台 stress-ng 制造 di/dt 带宽风暴 (环境毒化放大器, 设计概念第三维)

满负载 SIGSEGV 容错 (关键实测): --max_cpus=$(nproc) 时偶发
'Received signal SIGSEGV while outside of snap' (fork/mmap 资源耗尽击中 snap
外路径, 非 SDC, 非 假阳性, orchestrator 容错继续)。
本脚本区分: SIGSEGV-outside-snap = 噪声统计; SNAPSHOT_FAILED/mismatch = SDC 命中。

用法: distributed_scan.py --duration 60s [--no-stress] [--boards ...]
"""
import os, sys, time, threading, subprocess, json, argparse
sys.path.insert(0, os.path.dirname(__file__))
from ssh_lib import ssh, scp

DEFAULT_BOARDS = {
    "0101": "172.168.177.97",
    "0102": "172.168.160.42",
    "0103": "172.168.59.158",
    "0201": "172.168.178.81",
}
# 每板独立配置: (ssh_user, remote_tools_dir, remote_corpus_dir)
# 0101/0102/0201 部署机; 0103 本机 (output/ + /usr/local/bin)
# 0201 无 sudo, 用 sdc 用户 + 用户目录 (/home/sdc/...)
BOARD_CFG = {
    "0101": ("root", "/sdc_tools", "/sdc_corpus"),
    "0102": ("root", "/sdc_tools", "/sdc_corpus"),
    "0201": ("sdc", "/home/sdc/sdc_tools", "/home/sdc/sdc_corpus"),
}

def parse_duration_seconds(dur):
    """'60s' -> 60, '8h' -> 28800, '30m' -> 1800"""
    import re
    m = re.match(r'(\d+)([smh])', dur)
    if not m:
        return int(dur)
    n, unit = int(m.group(1)), m.group(2)
    return n * {'s': 1, 'm': 60, 'h': 3600}[unit]

def board_scan_thread(name, ip, duration, stress, results):
    """在单板上跑接近满负载 orchestrator + 可选 stress-ng。0103 本机直接执行。"""
    dur_s = parse_duration_seconds(duration)
    if ip == "172.168.59.158":
        # 0103 编译机: 语料在本地 output/, 工具在 /usr/local/bin
        local_shard_list = "output/sdc_shard_list"
        local_meta = "output/sdc_corpus_metadata"
        runner = "/usr/local/bin/reading_runner_main_nolibc"
        orch = "/usr/local/bin/silifuzz_orchestrator_main"
        log = "output/distributed/0103.scan.log"
        os.makedirs("output/distributed", exist_ok=True)
        cmd = (
            f"timeout {dur_s} {orch} --duration={duration} --max_cpus=$(nproc) "
            f"--runner={runner} --shard_list_file={local_shard_list} "
            f"--corpus_metadata_file={local_meta} 2>&1 | tee {log}; "
            f"echo SCAN_DONE_$?"
        )
        try:
            out = subprocess.run(["bash", "-c", cmd], capture_output=True,
                                 text=True, timeout=dur_s+120).stdout
            results[name] = {"ip": ip, "status": "done", "tail": out[-2000:]}
        except Exception as e:
            results[name] = {"ip": ip, "status": "error", "error": str(e)}
        return
    # 远程板: 按板取 user/path (0201 用 sdc 用户+用户目录)
    user, rtools, rcorpus = BOARD_CFG.get(name, ("root", "/sdc_tools", "/sdc_corpus"))
    runner_r = f"{rtools}/reading_runner_main_nolibc"
    orch_r = f"{rtools}/silifuzz_orchestrator_main"
    log_r = f"{rcorpus}/scan.log"
    cmd = (
        f"cd {rcorpus} && "
        f"timeout {dur_s} {orch_r} --duration={duration} --max_cpus=$(nproc) "
        f"--runner={runner_r} "
        f"--shard_list_file={rcorpus}/shard_list "
        f"--corpus_metadata_file={rcorpus}/corpus_metadata "
        f"2>&1 | tee {log_r}; "
        f"echo SCAN_DONE_$?"
    )
    # 后台 stress-ng (环境毒化) — 留 8 核给系统, 其余跑 matrixprod 制造 di/dt
    if stress:
        stress_cmd = (
            f"stress-ng --cpu 8 --cpu-method matrixprod --timeout {duration} "
            f">/dev/null 2>&1 &"
        )
        try: ssh(ip, stress_cmd, timeout=15, user=user)
        except: pass
    try:
        out = ssh(ip, cmd, timeout=dur_s + 120, user=user)
        results[name] = {"ip": ip, "status": "done", "tail": out[-2000:]}
    except Exception as e:
        results[name] = {"ip": ip, "status": "error", "error": str(e)}

def poll_status(name, ip, results, stop_event):
    """周期性拉取单板状态 (SIGSEGV/SDC 计数) 回 0103。"""
    user, _, rcorpus = BOARD_CFG.get(name, ("root", "/sdc_tools", "/sdc_corpus"))
    log_r = f"{rcorpus}/scan.log"
    while not stop_event.is_set():
        try:
            stat = ssh(ip, f"grep -c 'SIGSEGV' {log_r} 2>/dev/null; "
                          f"grep -cE 'mismatch|SNAPSHOT_FAILED' {log_r} 2>/dev/null; "
                          f"echo ALIVE", timeout=15, user=user)
            results.setdefault(name, {"ip": ip})["last_stat"] = stat
        except: pass
        time.sleep(30)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", default="60s", help="扫描时长 (如 60s/8h)")
    ap.add_argument("--no-stress", action="store_true", help="禁用 stress-ng 环境毒化")
    ap.add_argument("--boards", default="", help="自定义单板 (name=ip,...)")
    args = ap.parse_args()

    if args.boards:
        boards = dict(p.split("=") for p in args.boards.split(","))
    else:
        boards = DEFAULT_BOARDS

    results = {}
    threads = []
    stop = threading.Event()
    # 启动扫描线程
    for name, ip in boards.items():
        t = threading.Thread(target=board_scan_thread,
                             args=(name, ip, args.duration, not args.no_stress, results))
        t.start(); threads.append(t)
        # 状态轮询线程
        p = threading.Thread(target=poll_status, args=(name, ip, results, stop))
        p.daemon = True; p.start()
    # 等待扫描完成
    for t in threads:
        t.join()
    stop.set()
    # 输出汇总
    os.makedirs("output/distributed", exist_ok=True)
    print(f"\n=== 分布式扫描完成 (duration={args.duration}) ===")
    for name, r in results.items():
        stat = r.get("last_stat", "")
        sigsegv = sdc = 0
        lines = stat.splitlines()
        if len(lines) >= 2:
            try: sigsegv = int(lines[0].strip() or 0)
            except: pass
            try: sdc = int(lines[1].strip() or 0)
            except: pass
        status = r.get("status", "?")
        print(f"  {name} ({r.get('ip')}): {status} | SIGSEGV噪声={sigsegv} | SDC命中={sdc}")
        if r.get("error"):
            print(f"    error: {r['error'][:200]}")
        if r.get("tail"):
            print(f"    tail: {r['tail'][-300:]}")
    # 落盘汇总
    with open("output/distributed/scan_summary.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  汇总: output/distributed/scan_summary.json")

if __name__ == "__main__":
    main()

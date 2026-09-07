#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_scan.py — 真机 SDC 扫描驱动 (E3/E4 核心)。

对设备(本机/远程)跑 orchestrator 扫描 corpus, 拉回日志, 用与
scripts/collect_results.py 完全一致的解析规则分类:
  真SDC = outcome 2/3/4; 噪声 = outcome 5/6 + SIGSEGV-outside-snap + SIGTERM。

orchestrator flag 组合与 scripts/distributed_scan.py 已验证行为一致:
  {orch} --duration={dur}s --max_cpus={N} --runner={runner}
          --shard_list_file={list} --corpus_metadata_file={meta}
(shard_list: 每行一个语料绝对路径; metadata: 'version: "local_corpus"')
外加 --enable_v1_compat_logging: orchestrator 默认级别健康时完全静默(实测
2026/09/02 本机 10s/2cpu rc=0 → 日志 0 行), 打开 v1-compat 才有周期性
'Silifuzz Checker Result:{...play_count...}' 汇总行, 提供扫描确实在跑的
iter 证据; 外壳 timeout {dur_s+60} (比 distributed_scan 的裸 dur_s 多 60s
余量, 覆盖收尾/日志落盘), 防 orchestrator 挂死。
"""
import argparse
import json
import os
import re
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from tools.sdc_experiment.hw_log_parser import parse_log as _parse_log  # noqa: E402  权威解析


def parse_log(text: str) -> dict:
    """单一权威解析在 hw_log_parser.py (口径: outcome 2/3/4=SDC)。"""
    return _parse_log(text)


def parse_v1_summary(text: str):
    """解析 orchestrator --enable_v1_compat_logging 的终态汇总行 (最后一条)。

    实测形态 (2026/09/02, /tmp/orch_probe/v1c.log):
      Silifuzz Checker Result:{issues_detected = 0, ..., play_count = 10,
        ..., runaway_count = 0, ...}
    issues_detected = ResultCollector.num_failed_snapshots (含 runaway, 除非
    --report_runaways_as_errors=false 时不计入 — 默认 false); play_count =
    runner 进程完成数。健康无日志时返回 None。
    """
    pat = re.compile(
        r"issues_detected = (\d+).*?play_count = (\d+).*?runaway_count = (\d+)")
    last = None
    for m in pat.finditer(text):
        last = {"issues_detected": int(m.group(1)),
                "play_count": int(m.group(2)),
                "runaway_count": int(m.group(3))}
    return last


def _scan_cmd(orch, runner, shard_list, metadata, duration_s, max_cpus):
    """orchestrator 命令行 (flag 组合自 distributed_scan.py, 加 v1-compat)。"""
    return (f"timeout {duration_s + 60} {orch} --duration={duration_s}s "
            f"--max_cpus={max_cpus} --runner={runner} "
            f"--shard_list_file={shard_list} --corpus_metadata_file={metadata} "
            f"--enable_v1_compat_logging")


def _ERR_RESULT(device, corpus_remote: str) -> dict:
    """错误路径的标准键集 (与正常 parse_log 结果同构, 值为零/None)。

    上游 summary 判定 (exp03 step 4) 直接按 sdc_hits/total_failed/... 取键;
    缺键会 KeyError 且被 set -e 杀掉 → 错误场景必须能落一个
    CLASSIFICATION_INCOMPLETE 的 summary, 而不是崩溃。
    """
    return {"sigsegv_noise": 0, "sigterm": 0, "runaway_noise": 0,
            "misbehave_noise": 0, "sdc_hits": 0, "sdc_details": [],
            "total_failed": 0,
            "scan_work_dir": None, "device": device.name,
            "max_cpus": None, "duration_s": None,
            "corpus": corpus_remote, "orch_rc": None,
            "scan_wall_s": None, "v1_summary": None,
            "archived_log": None}


def hw_scan(device, corpus_remote: str, duration_s: int, max_cpus: int,
            stress: bool = False) -> dict:
    """在 device 上跑 orchestrator 扫描, 返回解析结果。

    corpus_remote: 设备本地的语料文件或目录。目录 → 列出其中语料分片;
    文件 → 单行 shard_list。shard_list + metadata 写到设备工作目录。
    """
    orch = device.tool_path("silifuzz_orchestrator_main")
    runner = device.tool_path("reading_runner_main_nolibc")
    work = f"/tmp/sdc_scan_{int(time.time())}"
    device.run(f"mkdir -p {work}")

    # shard_list: 目录 → 每行一个分片绝对路径; 文件 → 单行。
    # for 循环 rc 只反映最后一个 glob 项 (末项非普通文件时 rc=1) → 不看 rc,
    # 改验产物: shard_list 非空行数即分片数, 0 行才视为失败。
    rc_t, _ = device.run(f"test -d {corpus_remote}", timeout=30)
    if rc_t == 0:
        device.run(f"for f in {corpus_remote}/*; do "
                   f"[ -f \"$f\" ] && readlink -f \"$f\"; done > {work}/shard_list || true",
                   timeout=60)
        rc_n, n_out = device.run(f"grep -c . {work}/shard_list", timeout=30)
        shards = int(n_out.strip().splitlines()[-1]) if rc_n == 0 and n_out.strip() else 0
        if shards < 1:
            return dict(_ERR_RESULT(device, corpus_remote),
                        error=f"shard_list 为空 (目录 {corpus_remote} 无普通文件分片)")
    else:
        rc_f, _ = device.run(f"test -f {corpus_remote}", timeout=30)
        rc_w, _ = device.run(f"echo {corpus_remote} > {work}/shard_list", timeout=60)
        if rc_w != 0 or rc_f != 0:
            return dict(_ERR_RESULT(device, corpus_remote),
                        error=f"语料不可读/写入失败 (test -f rc={rc_f}, write rc={rc_w})")
    device.run(f"echo 'version: \"local_corpus\"' > {work}/corpus_metadata", timeout=60)

    cmd = (_scan_cmd(orch, runner, f"{work}/shard_list",
                     f"{work}/corpus_metadata", duration_s, max_cpus)
           + f" > {work}/scan.log 2>&1; echo ORCH_RC=$?")
    if stress:
        device.run("command -v stress-ng >/dev/null && "
                   f"(stress-ng --cpu {max_cpus} --timeout {duration_s}s "
                   f"> {work}/stress.log 2>&1 &) || true", timeout=30)

    scan_start = int(time.time())
    rc, out = device.run(cmd, timeout=duration_s + 600)
    scan_wall_s = int(time.time()) - scan_start
    orch_rc = None
    m = re.search(r"ORCH_RC=(\d+)\s*$", out.strip())
    if m:
        orch_rc = int(m.group(1))

    # 拉日志 + 解析
    rc2, log = device.run(f"cat {work}/scan.log", timeout=120)
    if rc2 != 0:
        return dict(_ERR_RESULT(device, corpus_remote),
                    error=f"scan.log 读取失败 rc={rc2} (orch_rc={orch_rc})",
                    scan_work_dir=work, max_cpus=max_cpus,
                    duration_s=duration_s, orch_rc=orch_rc,
                    scan_wall_s=scan_wall_s, orch_cmd_rc=rc)
    parsed = parse_log(log)
    v1 = parse_v1_summary(log)
    parsed.update({
        "scan_work_dir": work, "device": device.name,
        "max_cpus": max_cpus, "duration_s": duration_s,
        "corpus": corpus_remote, "orch_rc": orch_rc,
        "scan_wall_s": scan_wall_s,
        "v1_summary": v1,   # issues_detected/play_count/runaway_count (无则 None)
    })
    # 拉回日志存档 (local: 直接拷; remote: scp)
    os.makedirs("output/experiments/hw_scan_logs", exist_ok=True)
    local_log = (f"output/experiments/hw_scan_logs/"
                 f"{device.name}_{scan_start}.scan.log")
    device.get(f"{work}/scan.log", local_log)
    parsed["archived_log"] = local_log
    return parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="local | remote:NAME")
    ap.add_argument("--corpus", required=True, help="设备上的语料文件或目录")
    ap.add_argument("--duration", type=int, default=1800)
    ap.add_argument("--max-cpus", type=int, default=8)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--exp", default="exp03")
    a = ap.parse_args()
    from tools.sdc_experiment.experiment_config import default_config, MAX_CPUS_HARD_LIMIT
    from tools.sdc_experiment.devices.device_pool import DevicePool
    from tools.sdc_experiment.devices.local_device import LocalDevice
    cfg = default_config(a.exp)
    if a.max_cpus > MAX_CPUS_HARD_LIMIT:
        raise SystemExit(f"max_cpus={a.max_cpus} 超出 MCE 红线 {MAX_CPUS_HARD_LIMIT}")
    dev = (LocalDevice() if a.device == "local"
           else DevicePool().load().get(a.device.split(":", 1)[1]))
    res = hw_scan(dev, a.corpus, a.duration, a.max_cpus, a.stress)
    os.makedirs(cfg.out_dir, exist_ok=True)
    out = cfg.out_dir / f"hw_{dev.name}.json"
    with open(out, "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

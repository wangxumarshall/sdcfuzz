#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""deploy.py — 把 silifuzz 静态工具 + corpus 部署到设备池设备。

静态链接 ELF aarch64 → 拷贝即运行 (F6)。幂等: md5 一致跳过。
"""
import argparse, hashlib, json, os, sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

LOCAL_TOOL_SRC = "/usr/local/bin"
TOOLS = ["snap_tool", "simple_fix_tool_main",
         "reading_runner_main_nolibc", "silifuzz_orchestrator_main",
         "silifuzz_platform_id"]

def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _probe_help(device, dst: str, timeout: int = 30) -> tuple:
    """探活: 直接执行 {dst} --help (不接管道, rc 即工具真实退出码), 返回 (ok, 前2行输出)。
    ok = rc in (0,1) (gflags 工具 --help 惯例 rc=1) 且输出非空。
    noexec/缺文件=126/127, 崩溃/ssh失败=其他 → 均 False。"""
    rc, out = device.run(f"{dst} --help 2>&1", timeout=timeout)
    head2 = "\n".join(out.strip().splitlines()[:2])
    return (rc in (0, 1) and out.strip() != ""), head2

def deploy(device, corpus_local_dir: str = None, force: bool = False) -> dict:
    # 依赖契约: device.tools_dir (Device ABC 文档级契约, 见 device.py —
    # LocalDevice/RemoteDevice 均在 __init__ 设置)
    res = {"device": device.name, "tools": {}, "probe_output": {}, "corpus": None}
    device.run(f"mkdir -p {device.tools_dir}")
    for t in TOOLS:
        src = os.path.join(LOCAL_TOOL_SRC, t)
        if not os.path.exists(src):
            res["tools"][t] = "FAILED(no source)"
            continue
        dst = device.tool_path(t)
        _, remote_md5 = device.run(f"md5sum {dst} 2>/dev/null | awk '{{print $1}}'", timeout=30)
        # 远端输出可能含 /etc/profile.d 噪声行 → 逐行比对 md5 (取纯 32 位 hex 的行)
        remote_md5s = [l.strip() for l in remote_md5.splitlines()
                       if len(l.strip()) == 32 and all(c in "0123456789abcdef" for c in l.strip())]
        local_md5 = _md5(src)
        if not force and local_md5 in remote_md5s:
            # 幂等跳过上传 ≠ 跳过探活: md5 一致也要跑 --help 留下活性证据
            ok, head2 = _probe_help(device, dst)
            res["tools"][t] = "skip(md5 match)" if ok else f"BAD(probe after skip)"
            res["probe_output"][t] = head2
            continue
        ok = device.put(src, dst)
        if ok:
            device.run(f"chmod +x {dst}")
            ok, head2 = _probe_help(device, dst)
            res["tools"][t] = "deployed" if ok else "BAD(probe)"
            res["probe_output"][t] = head2
        else:
            res["tools"][t] = "FAILED(put)"
    if corpus_local_dir:
        remote_corpus = os.path.join(os.path.dirname(device.tools_dir.rstrip("/")), "sdc_corpus")
        device.run(f"mkdir -p {remote_corpus}")
        ok = device.put(corpus_local_dir, remote_corpus)   # 目录级 scp -r
        res["corpus"] = {"remote": remote_corpus, "ok": bool(ok)}
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="remote:NAME | local")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.device == "local":
        from tools.sdc_experiment.devices.local_device import LocalDevice
        dev = LocalDevice(tools_dir="/tmp/sdc_experiment/tools")
    else:
        from tools.sdc_experiment.devices.device_pool import DevicePool
        dev = DevicePool().load().get(a.device.split(":", 1)[1])
    print(json.dumps(deploy(dev, a.corpus, a.force), ensure_ascii=False))

if __name__ == "__main__":
    main()

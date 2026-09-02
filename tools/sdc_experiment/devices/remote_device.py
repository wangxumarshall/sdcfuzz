#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""remote_device.py — 远程 SSH 板卡设备 (用户提供 IP/端口/用户名/密码)。

复用 scripts/ssh_lib.py 的零依赖 pty 密码 SSH。与 LocalDevice 同接口,
实验脚本对两种设备透明。凭据只来自参数/清单文件(绝不用硬编码)。
"""
import os, re, sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SCRIPTS = os.path.join(_REPO, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from ssh_lib import ssh as _ssh, scp as _scp, _run, SSH_OPTS   # noqa: E402

GEM5_PROBE = "ls ~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt"

class RemoteDevice:
    def __init__(self, host: str, port: int = 22, user: str = "root",
                 password: str | None = None, name: str | None = None,
                 tools_dir: str = "/sdc_tools"):
        self.host, self.port, self.user = host, port, user
        self._password = password or os.environ.get("SDC_PASSWORD", "")
        self._name = name or f"remote-{host}"
        self.tools_dir = tools_dir

    @property
    def name(self) -> str:
        return self._name

    def _ssh(self, cmd: str, timeout: int = 60) -> tuple:
        """ssh_lib 不透传退出码 → 用 'cmd; echo RC=$?' 约定解析。"""
        out = _ssh(self.host, f"{cmd}; echo RC=$?", password=self._password,
                   timeout=timeout, user=self.user)
        m = re.search(r"RC=(\d+)\s*$", out.strip())
        rc = int(m.group(1)) if m else 1
        text = re.sub(r"\n?RC=\d+\s*$", "", out)
        return rc, text

    def run(self, cmd: str, timeout: int = 60) -> tuple:
        return self._ssh(cmd, timeout)

    def probe(self) -> dict:
        errs = []
        rc, uname = self.run("uname -m", timeout=15)
        if rc != 0:
            return {"reachable": False, "arch": "unknown", "cores": 0, "mem_gb": 0,
                    "os": "", "specs_ok": False, "errors": [f"ssh rc={rc}"], "gem5": False}
        arch = uname.strip()
        _, nproc = self.run("nproc", timeout=15)
        cores = int(nproc.strip()) if nproc.strip().isdigit() else 0
        _, mem = self.run("awk '/MemTotal/{print int($2/1024/1024)}' /proc/meminfo", timeout=15)
        mem_gb = int(mem.strip()) if mem.strip().isdigit() else 0
        _, osrel = self.run("head -1 /etc/os-release", timeout=15)
        rc_g, _ = self.run(f"test -f {GEM5_PROBE.replace('~', '$HOME')}", timeout=15)
        has_gem5 = rc_g == 0
        # 工具检查: tools_dir 下或 PATH
        _, tchk = self.run(
            f"for t in snap_tool simple_fix_tool_main reading_runner_main_nolibc "
            f"silifuzz_orchestrator_main; do command -v $t >/dev/null 2>&1 || "
            f"test -x {self.tools_dir}/$t || echo MISS:$t; done", timeout=15)
        for line in tchk.splitlines():
            if line.startswith("MISS:"):
                errs.append(f"missing tool {line[5:]} (deploy first)")
        if arch != "aarch64":
            errs.append(f"arch={arch} != aarch64")
        if mem_gb < 8:
            errs.append(f"mem={mem_gb}GB < 8GB")
        return {"reachable": True, "arch": arch, "cores": cores, "mem_gb": mem_gb,
                "os": osrel.strip(), "specs_ok": not errs, "errors": errs, "gem5": has_gem5}

    def put(self, local: str, remote: str) -> bool:
        out = _scp(local, remote, self.host, password=self._password,
                   timeout=300, user=self.user)
        rc, _ = self._ssh(f"test -f {remote}", timeout=15)
        return rc == 0

    def get(self, remote: str, local: str) -> bool:
        # ssh_lib.scp 只支持上传; 下载直接组装 scp 命令 (远端在 src 位)
        out = _run(["scp"] + SSH_OPTS + [f"{self.user}@{self.host}:{remote}", local],
                   self._password, timeout=300, is_scp=True)
        return os.path.exists(local)

    def tool_path(self, name: str) -> str:
        return f"{self.tools_dir}/{name}"

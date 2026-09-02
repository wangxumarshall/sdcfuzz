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
from ssh_lib import _run, SSH_OPTS   # noqa: E402
from .device import Device           # noqa: E402

GEM5_PROBE = "$HOME/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt"

class RemoteDevice(Device):
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
        """ssh_lib 不透传退出码 → 用 'cmd; echo RC=$?' 约定解析。
        ssh_lib.ssh 无 port 参数 → 直接组装 _run 以透传 -p 端口。"""
        out = _run(["ssh"] + SSH_OPTS + ["-p", str(self.port),
                   f"{self.user}@{self.host}", f"{cmd}; echo RC=$?"],
                   self._password, timeout=timeout)
        m = re.search(r"RC=(\d+)\s*$", out.strip())
        rc = int(m.group(1)) if m else 1
        text = re.sub(r"\n?RC=\d+\s*$", "", out)
        return rc, text

    def run(self, cmd: str, timeout: int = 60) -> tuple:
        return self._ssh(cmd, timeout)

    @staticmethod
    def _last_line(out: str) -> str:
        """取最后一个非空行: 远端 /etc/profile.d 噪声出现在命令输出之前。"""
        lines = [l for l in out.splitlines() if l.strip()]
        return lines[-1].strip() if lines else ""

    def probe(self) -> dict:
        errs = []
        rc, uname = self.run("uname -m", timeout=15)
        if rc != 0:
            return {"reachable": False, "arch": "unknown", "cores": 0, "mem_gb": 0,
                    "os": "", "specs_ok": False, "errors": [f"ssh rc={rc}"], "gem5": False}
        arch = self._last_line(uname)
        _, nproc = self.run("nproc", timeout=15)
        m = re.search(r"\d+", self._last_line(nproc))
        cores = int(m.group()) if m else 0
        _, mem = self.run("awk '/MemTotal/{print int($2/1024/1024)}' /proc/meminfo", timeout=15)
        m = re.search(r"\d+", self._last_line(mem))
        mem_gb = int(m.group()) if m else 0
        _, osrel = self.run("head -1 /etc/os-release", timeout=15)
        rc_g, _ = self.run(f"test -f {GEM5_PROBE}", timeout=15)
        has_gem5 = rc_g == 0
        # 工具检查: tools_dir 下或 PATH
        _, tchk = self.run(
            f"for t in snap_tool simple_fix_tool_main reading_runner_main_nolibc "
            f"silifuzz_orchestrator_main silifuzz_platform_id; do command -v $t >/dev/null 2>&1 || "
            f"test -x {self.tools_dir}/$t || echo MISS:$t; done", timeout=15)
        for line in tchk.splitlines():
            if line.startswith("MISS:"):
                errs.append(f"missing tool {line[5:]} (deploy first)")
        if arch != "aarch64":
            errs.append(f"arch={arch} != aarch64")
        if mem_gb < 8:
            errs.append(f"mem={mem_gb}GB < 8GB")
        return {"reachable": True, "arch": arch, "cores": cores, "mem_gb": mem_gb,
                "os": self._last_line(osrel), "specs_ok": not errs, "errors": errs, "gem5": has_gem5}

    def put(self, local: str, remote: str) -> bool:
        # ssh_lib.scp 无 port 参数 → 直接组装 _run; scp 端口用 -P (上传, 远端在 dst 位)
        # 目录上传: scp -r。OpenSSH≥9 默认 SFTP 模式下远端目录不存在时行为是
        # "把 src 内容放进 remote" 而非 "remote/<basename>" → 先 mkdir -p 再传, 保证
        # 远端始终落在 remote/<basename>/ (与 LocalDevice.put 目录语义一致)
        if os.path.isdir(local):
            self._ssh(f"mkdir -p {remote}", timeout=15)
            _run(["scp"] + SSH_OPTS + ["-P", str(self.port), "-r", local,
                 f"{self.user}@{self.host}:{remote}"],
                 self._password, timeout=600, is_scp=True)
            rc, _ = self._ssh(f"test -d {remote}/{os.path.basename(local.rstrip('/'))}", timeout=15)
            return rc == 0
        _run(["scp"] + SSH_OPTS + ["-P", str(self.port), local,
             f"{self.user}@{self.host}:{remote}"],
             self._password, timeout=300, is_scp=True)
        rc, _ = self._ssh(f"test -f {remote}", timeout=15)
        return rc == 0

    def get(self, remote: str, local: str) -> bool:
        # ssh_lib.scp 只支持上传; 下载直接组装 scp 命令 (远端在 src 位), 端口用 -P
        _run(["scp"] + SSH_OPTS + ["-P", str(self.port),
             f"{self.user}@{self.host}:{remote}", local],
             self._password, timeout=300, is_scp=True)
        return os.path.exists(local)

    def tool_path(self, name: str) -> str:
        return f"{self.tools_dir}/{name}"

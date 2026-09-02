#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""local_device.py — 本机设备 (0103)。subprocess 直执行, put/get 即拷贝。"""
import os, shutil, subprocess
from .device import Device

LOCAL_TOOLS_DIR = "/usr/local/bin"   # silifuzz 工具已装 (实测 ls 确认)
LOCAL_TOOLS = ["snap_tool", "simple_fix_tool_main", "reading_runner_main_nolibc",
               "silifuzz_orchestrator_main", "silifuzz_platform_id"]

class LocalDevice(Device):
    def __init__(self, work_dir: str = "/tmp/sdc_experiment", name: str = "local-0103",
                 tools_dir: str = LOCAL_TOOLS_DIR):
        self._name = name
        self.work_dir = work_dir
        self.tools_dir = tools_dir   # 部署目标目录 (默认 /usr/local/bin 已装; deploy 冒烟传临时目录)
        os.makedirs(work_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return self._name

    def run(self, cmd: str, timeout: int = 60):
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            return 124, "TIMEOUT"

    def probe(self) -> dict:
        errs = []
        rc, uname = self.run("uname -m")
        arch = uname.strip() if rc == 0 else "unknown"
        rc, nproc = self.run("nproc")
        cores = int(nproc.strip()) if rc == 0 and nproc.strip().isdigit() else 0
        mem_gb = 0
        rc, mem = self.run("awk '/MemTotal/{print int($2/1024/1024)}' /proc/meminfo")
        if rc == 0 and mem.strip().isdigit():
            mem_gb = int(mem.strip())
        rc2, osrel = self.run("cat /etc/os-release | head -1")
        missing = [t for t in LOCAL_TOOLS if not os.path.exists(os.path.join(LOCAL_TOOLS_DIR, t))]
        if missing:
            errs.append(f"missing tools: {missing}")
        if arch != "aarch64":
            errs.append(f"arch={arch} != aarch64")
        if mem_gb < 8:
            errs.append(f"mem={mem_gb}GB < 8GB")
        return {"reachable": rc == 0, "arch": arch, "cores": cores, "mem_gb": mem_gb,
                "os": osrel.strip(), "specs_ok": not errs, "errors": errs}

    def put(self, local: str, remote: str) -> bool:
        try:
            if os.path.isdir(local):
                # 目录上传 (scp -r 语义): 远端落在 remote/<basename>
                os.makedirs(remote, exist_ok=True)
                shutil.copytree(local, os.path.join(remote, os.path.basename(local.rstrip("/"))),
                                dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(remote) or "/", exist_ok=True)
                # 目标已存在且只读 (如 chmod +x 后的 0555 工具) → 先删再拷, 模拟 scp 覆盖
                if os.path.exists(remote):
                    os.unlink(remote)
                shutil.copy(local, remote)
            return True
        except OSError:
            return False

    def get(self, remote: str, local: str) -> bool:
        try:
            os.makedirs(os.path.dirname(local) or "/", exist_ok=True)
            shutil.copy(remote, local)
            return True
        except OSError:
            return False

    def tool_path(self, name: str) -> str:
        return os.path.join(self.tools_dir, name)

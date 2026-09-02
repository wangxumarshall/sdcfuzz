#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""device.py — 设备抽象: 本机与远程板卡对实验脚本透明"""
from abc import ABC, abstractmethod

class Device(ABC):
    """一台可执行 sdcfuzz 验证的机器 (本机或远程 SSH 板卡)。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def probe(self) -> dict:
        """健康检查。返回 {"reachable","arch","cores","mem_gb","os","specs_ok","errors"}。
        specs_ok = arch==aarch64 且内存≥8GB 且 silifuzz 工具可用。"""

    @abstractmethod
    def run(self, cmd: str, timeout: int = 60) -> tuple:
        """执行 shell 命令, 返回 (exit_code, stdout)。"""

    @abstractmethod
    def put(self, local: str, remote: str) -> bool:
        """上传文件到设备, 成功返回 True。"""

    @abstractmethod
    def get(self, remote: str, local: str) -> bool:
        """从设备下载文件, 成功返回 True。"""

    @abstractmethod
    def tool_path(self, name: str) -> str:
        """返回该设备上 silifuzz 工具 (snap_tool/runner/orchestrator/...) 的路径。"""

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""device_pool.py — 设备池: 本机 + 远程板卡统一注册/探活/批量操作。

清单文件 output/devices/devices.json 含密码 (gitignore);
save() 只写抹除密码的公开清单 devices.public.json。
"""
import json, os
from .local_device import LocalDevice
from .remote_device import RemoteDevice

DEFAULT_REGISTRY = "output/devices/devices.json"

class DevicePool:
    def __init__(self):
        self._devices = []

    def add_local(self, name: str = "local-0103"):
        self._devices.append(LocalDevice(name=name))

    def add_remote(self, host: str, port: int = 22, user: str = "root",
                   password: str = "", name: str = None, tools_dir: str = "/sdc_tools"):
        self._devices.append(RemoteDevice(host=host, port=port, user=user,
                                          password=password, name=name,
                                          tools_dir=tools_dir))

    @property
    def devices(self):
        return list(self._devices)

    def get(self, name: str):
        for d in self._devices:
            if d.name == name:
                return d
        raise KeyError(f"no device named {name}")

    def load(self, path: str = DEFAULT_REGISTRY):
        with open(path) as f:
            data = json.load(f)
        for spec in data.get("devices", []):
            if spec.get("type") == "local":
                self.add_local(spec.get("name", "local"))
            else:
                self.add_remote(spec["host"], port=spec.get("port", 22),
                                user=spec.get("user", "root"),
                                password=spec.get("password", ""),
                                name=spec.get("name"),
                                tools_dir=spec.get("tools_dir", "/sdc_tools"))
        return self

    def save(self, path: str):
        """写公开清单 (抹密码)。含密码清单由 register_device.py 维护。"""
        out = {"devices": []}
        for d in self._devices:
            if isinstance(d, LocalDevice):
                out["devices"].append({"type": "local", "name": d.name})
            else:
                out["devices"].append({
                    "type": "remote", "name": d.name, "host": d.host,
                    "port": d.port, "user": d.user, "tools_dir": d.tools_dir})
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

    def probe_all(self, timeout: int = 30) -> dict:
        return {d.name: d.probe() for d in self._devices}

    @property
    def healthy(self):
        return [d for d in self._devices if d.probe()["specs_ok"]]

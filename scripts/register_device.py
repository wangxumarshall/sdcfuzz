#!/usr/bin/env python3
# SPDX-License-License: Apache-2.0
"""register_device.py — 注册用户提供的远程设备到设备清单。

用法:
  python3 scripts/register_device.py --name board-05 --host 10.0.0.5 \
      --port 22 --user root --password-env SDC_PASSWORD --tools-dir /sdc_tools
  # 或 --password 'xxx' (会警告: 建议用 --password-env)
注册后立即探活并打印 probe 结果。
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_experiment.devices.device_pool import DevicePool, DEFAULT_REGISTRY

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default=None, help="明文密码 (不建议; 优先 --password-env)")
    ap.add_argument("--password-env", default="SDC_PASSWORD", help="从该环境变量读密码")
    ap.add_argument("--tools-dir", default="/sdc_tools")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    a = ap.parse_args()
    pw = a.password or os.environ.get(a.password_env, "")
    if not pw:
        sys.exit(f"ERROR: 无密码。设 {a.password_env} 环境变量或传 --password")
    if a.password:
        print("WARNING: --password 明文传入; 建议改用 --password-env")
    reg = {}
    if os.path.exists(a.registry):
        reg = json.load(open(a.registry))
    reg.setdefault("devices", [])
    if any(d.get("host") == a.host and d.get("port") == a.port for d in reg["devices"]):
        sys.exit(f"ERROR: {a.host}:{a.port} 已注册")
    reg["devices"].append({"name": a.name, "host": a.host, "port": a.port,
                           "user": a.user, "password": pw, "tools_dir": a.tools_dir})
    os.makedirs(os.path.dirname(a.registry) or ".", exist_ok=True)
    json.dump(reg, open(a.registry, "w"), indent=2, ensure_ascii=False)
    print(f"已注册 {a.name} -> {a.host}:{a.port} (清单 {a.registry}, 该文件已 gitignore)")
    # 立即探活
    pool = DevicePool().load(a.registry)
    p = pool.get(a.name).probe()
    print(f"probe: {json.dumps(p, ensure_ascii=False, indent=2)}")
    if not p["reachable"]:
        print("WARNING: 设备不可达, 请检查 IP/端口/用户/密码")
    elif not p["specs_ok"]:
        print(f"NOTE: 可达但规格未就绪: {p['errors']} (部署工具后自动消除)")

if __name__ == "__main__":
    main()

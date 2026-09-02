#!/usr/bin/env python3
"""设备层单元测试。运行: python3 tools/sdc_experiment/test_device_pool.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.sdc_experiment.devices.local_device import LocalDevice

def test_local_probe():
    d = LocalDevice()
    p = d.probe()
    assert p["reachable"] is True
    assert p["arch"] == "aarch64", f"本机应为 aarch64, got {p['arch']}"
    assert p["cores"] > 0
    assert p["specs_ok"] is True, f"errors: {p['errors']}"
    print(f"PASS test_local_probe: {p}")

def test_local_run():
    d = LocalDevice()
    rc, out = d.run("echo hello-sdc")
    assert rc == 0 and "hello-sdc" in out
    rc2, _ = d.run("exit 3")
    assert rc2 == 3, f"退出码应透传, got {rc2}"
    print("PASS test_local_run")

def test_local_put_get():
    d = LocalDevice()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("payload-123"); src = f.name
    dst = os.path.join(d.work_dir, "putget_test.txt")
    assert d.put(src, dst) is True
    back = tempfile.mktemp(suffix=".txt")
    assert d.get(dst, back) is True
    assert open(back).read() == "payload-123"
    os.unlink(src); os.unlink(back)
    print("PASS test_local_put_get")

def test_local_tool_path():
    d = LocalDevice()
    p = d.tool_path("snap_tool")
    assert os.path.exists(p), f"snap_tool 应存在于 {p}"
    print(f"PASS test_local_tool_path: {p}")

def test_remote_device_skip_if_unreachable():
    """RemoteDevice 单元测试: 无设备清单时 SKIP (不 FAIL)。
    有清单时 (output/devices/devices.json) 对第一台真测。"""
    import json
    from tools.sdc_experiment.devices.remote_device import RemoteDevice
    cfg_path = "output/devices/devices.json"
    if not os.path.exists(cfg_path):
        print("SKIP test_remote_device: 无设备清单 output/devices/devices.json (用户尚未注册远程设备)")
        return
    devs = json.load(open(cfg_path)).get("devices", [])
    if not devs:
        print("SKIP test_remote_device: 设备清单为空")
        return
    d0 = devs[0]
    d = RemoteDevice(host=d0["host"], port=d0.get("port", 22),
                     user=d0.get("user", "root"), password=d0.get("password"),
                     name=d0.get("name"), tools_dir=d0.get("tools_dir", "/sdc_tools"))
    p = d.probe()
    if not p["reachable"]:
        print(f"SKIP test_remote_device: {d.name} 不可达, probe={p}")
        return
    rc, out = d.run("echo remote-ok")
    assert rc == 0 and "remote-ok" in out, f"run 失败: rc={rc}, out={out!r}"
    # put/get 真测: 上传临时文件再取回, 校验内容一致 (远端放 /tmp, 不依赖 tools_dir 可写)
    payload = f"remote-putget-{os.getpid()}"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(payload); src = f.name
    remote_tmp = f"/tmp/sdc_putget_{os.getpid()}.txt"
    back = tempfile.mktemp(suffix=".txt")
    try:
        assert d.put(src, remote_tmp) is True, "put 失败 (上传后远端 test -f 不通过)"
        assert d.get(remote_tmp, back) is True, "get 失败 (本地文件未出现)"
        assert open(back).read() == payload, "put/get 往返内容不一致"
    finally:
        os.unlink(src)
        if os.path.exists(back):
            os.unlink(back)
        d.run(f"rm -f {remote_tmp}")
    print(f"PASS test_remote_device: {d.name} probe={p} put/get=roundtrip-ok")

def test_device_pool_roundtrip():
    import json, tempfile
    from tools.sdc_experiment.devices.device_pool import DevicePool
    pool = DevicePool()
    pool.add_local("local-0103")
    pool.add_remote("192.0.2.1", port=2222, user="test", password="pw",
                    name="fake-board", tools_dir="/tmp/sdc_tools")
    assert len(pool.devices) == 2
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        path = f.name
    pool.save(path)   # 公开版: 抹密码
    data = json.load(open(path))
    assert "password" not in json.dumps(data), "公开清单不得含密码"
    assert data["devices"][1]["host"] == "192.0.2.1"
    assert data["devices"][1]["port"] == 2222
    os.unlink(path)
    # probe_all: local 真测, fake-board 不可达但不应抛异常
    probes = pool.probe_all(timeout=15)
    assert probes["local-0103"]["specs_ok"] is True
    assert probes["fake-board"]["reachable"] is False
    print("PASS test_device_pool_roundtrip")

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    test_remote_device_skip_if_unreachable()
    test_device_pool_roundtrip()
    print("ALL PASS")

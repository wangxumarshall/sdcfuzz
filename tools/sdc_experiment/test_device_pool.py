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

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    print("ALL PASS")

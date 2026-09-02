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

def test_local_device_tools_dir_and_dir_put():
    """tools_dir 参数 + 目录级 put (scp -r 语义: 远端落在 remote/<basename>)。"""
    import shutil, tempfile
    with tempfile.TemporaryDirectory() as td:
        d = LocalDevice(work_dir=td, tools_dir=os.path.join(td, "tools"))
        assert d.tool_path("snap_tool") == os.path.join(td, "tools", "snap_tool")
        # 目录 put
        src_dir = os.path.join(td, "corpus_src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "shard.bin"), "w") as f:
            f.write("BIN")
        dst_root = os.path.join(td, "corpus_dst")
        assert d.put(src_dir, dst_root) is True
        assert os.path.isfile(os.path.join(dst_root, "corpus_src", "shard.bin")), \
            "目录 put 应落在 remote/<basename>/ 下"
    print("PASS test_local_device_tools_dir_and_dir_put")

def test_deploy_local():
    """deploy() 冒烟: 5 工具部署到临时 tools_dir, 可执行, 幂等 (二次 skip), 探活输出可见。"""
    import stat, tempfile
    from tools.sdc_experiment.deploy import deploy, TOOLS
    for t in TOOLS:  # 前置: 本机源工具须存在
        src = f"/usr/local/bin/{t}"
        if not os.path.exists(src):
            print(f"SKIP test_deploy_local: 本机缺少源工具 {src}")
            return
    with tempfile.TemporaryDirectory() as td:
        d = LocalDevice(work_dir=td, tools_dir=os.path.join(td, "tools"))
        r1 = deploy(d)
        for t in TOOLS:
            assert r1["tools"][t] == "deployed", f"首次部署应 deployed: {t}={r1['tools'][t]}"
            p = d.tool_path(t)
            assert os.path.isfile(p), f"{p} 不存在"
            assert os.access(p, os.X_OK), f"{p} 应可执行"
            assert r1["probe_output"].get(t, "").strip(), f"探活输出应为非空: {t}"
        r2 = deploy(d)   # 幂等: md5 一致 → skip, 但探活仍要跑且留痕
        for t in TOOLS:
            assert r2["tools"][t] == "skip(md5 match)", \
                f"二次部署应 skip: {t}={r2['tools'][t]}"
            assert r2["probe_output"].get(t, "").strip(), f"skip 路径探活输出应为非空: {t}"
        # 负控: noexec 目标 (md5 不变) → skip 路径探活必须报 BAD, 不能谎报 skip
        victim = d.tool_path(TOOLS[0])
        os.chmod(victim, stat.S_IRUSR)   # 去掉执行位, md5 不变
        r3 = deploy(d)
        assert r3["tools"][TOOLS[0]] == "BAD(probe after skip)", \
            f"noexec 应被 skip 路径探活抓到: {r3['tools'][TOOLS[0]]}"
        assert "Permission denied" in r3["probe_output"][TOOLS[0]]
        # 源缺失容错: FAILED(no source), 不抛异常
        import tools.sdc_experiment.deploy as dep
        orig_src = dep.LOCAL_TOOL_SRC
        dep.LOCAL_TOOL_SRC = os.path.join(td, "no_such_src")
        try:
            r4 = deploy(d)
            assert set(r4["tools"].values()) == {"FAILED(no source)"}, r4["tools"]
        finally:
            dep.LOCAL_TOOL_SRC = orig_src
        assert r1["corpus"] is None and r2["corpus"] is None
    print("PASS test_deploy_local: deployed+executable+probe-output, idempotent-skip+probe, noexec/源缺失负控")

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    test_local_device_tools_dir_and_dir_put()
    test_remote_device_skip_if_unreachable()
    test_device_pool_roundtrip()
    test_deploy_local()
    print("ALL PASS")

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ssh_lib.py — 零依赖密码 SSH/SCP 库 (无 sshpass/pexpect 也能用)

环境: 4 台鲲鹏 920 单板, root/sdc 密码 SDC@2026, openEuler 24.03 (无 sshpass,
无 pexpect)。基于 Python 标准库 pty.fork() 实现非交互式密码登录。

实测 (2026/08/26): 可登录 0101/0102/0103, 拷贝静态二进制跨机运行, 远程执行
orchestrator。0201 SSH 超时 (网络不可达, 排除)。
"""
import os, sys, pty, select, time

PASSWORD = os.environ.get("SDC_PASSWORD", "SDC@2026")
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR"]

def _run(cmd, password, timeout, is_scp=False):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(cmd[0], cmd)
    out = b""
    sent = False
    t0 = time.time()
    while True:
        if time.time() - t0 > timeout:
            try: os.kill(pid, 9)
            except: pass
            break
        r, _, _ = select.select([fd], [], [], 1.0)
        if fd in r:
            try:
                d = os.read(fd, 4096)
            except OSError:
                break
            if not d:
                break
            out += d
            if b"assword:" in out and not sent:
                os.write(fd, password.encode() + b"\n")
                sent = True
        st = os.waitpid(pid, os.WNOHANG)
        if st[0] != 0:
            # 进程结束, 只快速读取残留 (最多 1s), 避免慢链路卡死
            t_end = time.time() + 1.0
            while time.time() < t_end:
                r, _, _ = select.select([fd], [], [], 0.2)
                if fd not in r:
                    break
                try:
                    d = os.read(fd, 4096)
                except OSError:
                    break
                if not d:
                    break
                out += d
            break
    # 去除 SSH banner / 密码回显
    text = out.decode(errors='replace')
    lines = [l for l in text.splitlines()
             if l.strip() and "Authorized users only" not in l
             and "assword:" not in l and "Warning: Permanently" not in l]
    return "\n".join(lines)

def ssh(host, cmd, password=None, timeout=30, user="root"):
    """远程执行命令, 返回 stdout。user 指定登录用户 (默认 root)。"""
    pw = password or PASSWORD
    full = ["ssh"] + SSH_OPTS + [f"{user}@{host}", cmd]
    return _run(full, pw, timeout)

def scp(src, dst, host, password=None, timeout=120, user="root"):
    """拷贝文件 src 到 host:dst。"""
    pw = password or PASSWORD
    full = ["scp"] + SSH_OPTS + [src, f"{user}@{host}:{dst}"]
    return _run(full, pw, timeout, is_scp=True)

def scp_dir(src_dir, dst, host, password=None, timeout=300, user="root"):
    """递归拷贝目录。"""
    pw = password or PASSWORD
    full = ["scp"] + SSH_OPTS + ["-r", src_dir, f"{user}@{host}:{dst}"]
    return _run(full, pw, timeout, is_scp=True)

if __name__ == "__main__":
    # 用法: ssh_lib.py <host> <cmd> [--user U]  或  ssh_lib.py scp <src> <host> <dst> [--user U]
    args = sys.argv[1:]
    user = "root"
    if "--user" in args:
        i = args.index("--user")
        user = args[i+1]
        args = args[:i] + args[i+2:]
    if len(args) >= 3 and args[0] == "scp":
        src, host, dst = args[1], args[2], args[3]
        print(scp(src, dst, host, user=user))
    elif len(args) >= 2:
        host, cmd = args[0], args[1]
        print(ssh(host, cmd, user=user))
    else:
        print("Usage: ssh_lib.py <host> <cmd> [--user U] | ssh_lib.py scp <src> <host> <dst> [--user U]")
        sys.exit(1)

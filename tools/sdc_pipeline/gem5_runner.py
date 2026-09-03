#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_runner.py — gem5 golden 自动注册 + CHAOS 检出率验证器 (R3/R4 解法)。

打通 "生成/变异层 → gem5 验证" 断链:
- 任何 Candidate 先包装成 gem5 可跑的静态 Linux ELF 工作负载
  (复刻 sdc_probe_workload 系列的 C harness 结构: 汇编指令序列嵌入
  C 函数 + printf("SUM=... CRC=...")), golden 跑一次定基线
  (SUM/CRC + nc 周期数), 之后即可走 CHAOS bit/struct 注入测检出率。
- fault-clock 从候选自己的 nc 的 ROI [20%, 80%] 抽取 (sim_sweep 语义)。
- MCE 红线: gem5 并行 ≤ 4 (sim_sweep.MAX_JOBS 同源约束)。

注入判定复用 tools/sdc_experiment.sim_sweep 的 classify_output / wilson。
"""
import os
import random
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from tools.sdc_experiment.gem5_env import GEM5_OPT, TAISHAN_SCRIPT, local_gem5_env
from tools.sdc_experiment.sim_sweep import classify_output, wilson

MAX_JOBS = 4  # MCE 红线 (与 sim_sweep.MAX_JOBS 一致)
ROI = (0.2, 0.8)


def build_workload_files(cand, workdir: str) -> tuple[str, str]:
    """生成 gem5 工作负载 (payload.S + main.c), 返回两个源文件路径。

    架构 (经 SIGSEGV 三轮调试定稿, 见 git 历史):
    - payload.S: 独立汇编函数。prologue 按 AAPCS64 保存 callee-saved
      x19-x28 + x29/x30; 全部 x0-x28 从 g_in 装载 → 候选机器码 .long
      原样嵌入 → x0-x28 全部存回 g_out; epilogue 恢复。
      in/out 指针经栈槽传递并在每次访问前重取 (x2 被装载循环覆盖)。
      x29/x30 不参与装载 (FP/LR 不可毁), x31=ZR 不存在。
    - main.c: ITERS 次调用 payload + SUM/CRC printf (sdc_probe 系列
      golden 判定格式)。输出确定性: 静态程序 + 固定初值 → 3 次运行
      逐字节一致 (已实证)。
    """
    nregs = 29  # x0-x28 (x29 FP / x30 LR / x31 ZR 除外)
    insns = [int.from_bytes(cand.code_bytes[i:i + 4], "little")
             for i in range(0, len(cand.code_bytes), 4)]
    L = [".arch armv8-a", ".text", ".balign 64", ".global payload",
         ".func payload", "payload:",
         "    stp x29, x30, [sp, #-256]!",
         "    stp x19, x20, [sp, #128]", "    stp x21, x22, [sp, #144]",
         "    stp x23, x24, [sp, #160]", "    stp x25, x26, [sp, #176]",
         "    stp x27, x28, [sp, #192]",
         "    str x0, [sp, #208]", "    str x1, [sp, #216]"]
    for i in range(nregs):
        L.append("    ldr x2, [sp, #208]")
        L.append(f"    ldr x{i}, [x2, #{i*8}]")
    # 关键修复: x2 是装载循环的 temp, 循环结束时 x2 = in 指针而非 in[2]。
    # 候选指令执行前必须重装 x2 (gdb 实证: 否则候选读到的 x2 是地址值)。
    L.append("    ldr x2, [sp, #208]")
    L.append("    ldr x2, [x2, #16]")
    for w in insns:
        L.append(f"    .long 0x{w:08x}")
    for i in range(nregs):
        L.append("    ldr x2, [sp, #216]")
        L.append(f"    str x{i}, [x2, #{i*8}]")
    L += ["    ldp x19, x20, [sp, #128]", "    ldp x21, x22, [sp, #144]",
          "    ldp x23, x24, [sp, #160]", "    ldp x25, x26, [sp, #176]",
          "    ldp x27, x28, [sp, #192]",
          "    ldp x29, x30, [sp], #256", "    ret", ".endfunc"]
    s_path = os.path.join(workdir, "payload.S")
    with open(s_path, "w") as f:
        f.write("\n".join(L) + "\n")

    init_lines = "\n".join(f"    g_in[{r}] = 0x{v:x}ULL;"
                           for r, v in sorted(cand.regs_init.items()))
    c_src = f"""/* auto-generated from Candidate {cand.ident} (origin={cand.origin}) */
#include <stdio.h>
#include <stdint.h>
#define ITERS 200
extern void payload(uint64_t *in, uint64_t *out);
static uint64_t g_in[31] = {{0}}, g_out[31] = {{0}};
int main(void) {{
{init_lines}
    for (int i = 0; i < ITERS; i++)
        payload(g_in, g_out);
    uint64_t acc = 0;
    for (int i = 0; i < 29; i++) acc += g_out[i];
    uint32_t crc = (uint32_t)(acc ^ (acc >> 32));
    printf("SUM=%llu CRC=%08x\\n", (unsigned long long)acc, crc);
    return 0;
}}
"""
    c_path = os.path.join(workdir, "main.c")
    with open(c_path, "w") as f:
        f.write(c_src)
    return s_path, c_path


def _compile_workload(cand, out_path: str) -> str:
    """生成源文件 + gcc -static -O2 编译 (与 sdc_probe 系列相同方式)。"""
    workdir = os.path.dirname(out_path) or "."
    s_path, c_path = build_workload_files(cand, workdir)
    r = subprocess.run(["gcc", "-static", "-O2", "-o", out_path,
                        s_path, c_path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gcc failed:\n{r.stderr}")
    return out_path


def _run_gem5_capture(binary, script, args: list, outdir: str) -> str:
    """跑一次 gem5, 返回 simout.txt 内容 (golden 或注入)。"""
    os.makedirs(outdir, exist_ok=True)
    cmd = [GEM5_OPT, "-r", "-e", "--silent-redirect", "-d", outdir,
           script] + args
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       env=local_gem5_env())
    except subprocess.TimeoutExpired:
        pass
    p = os.path.join(outdir, "simout.txt")
    if os.path.exists(p):
        with open(p, errors="replace") as f:
            return f.read()
    return ""


def parse_golden(simout: str):
    """从 golden simout 提取 (SUM=.. CRC=.. 行, nc)。
    nc = 'Exiting @ tick N' 的 N (注入 ROI 基准)。"""
    golden = None
    nc = None
    for line in simout.splitlines():
        if "SUM=" in line and golden is None:
            golden = line.strip()
        if "Exiting @" in line and "tick" in line:
            try:
                nc = int(line.split("tick")[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
    if golden is None or nc is None:
        return None
    return {"golden": golden, "nc": nc}


def make_inject_cmd(binary: str, script: str, first_clock: int, mode: str,
                    seed: int) -> list:
    """构造一次 CHAOS 注入的 gem5 参数 (bit|struct)。"""
    cmd = ["--binary", binary, "--mode", "inject",
           "--first-clock", str(first_clock), "--max-faults", "1",
           "--probability", "1.0", "--rng-seed", str(seed)]
    if mode == "struct":
        cmd += ["--injector", "lsq_fwd", "--structural-fault", "byte_lane_skew"]
    return cmd


class Gem5Validator:
    """检出率验证器: golden 注册 (每候选一次) + 注入 sweep (每候选 n 次)。"""

    def __init__(self, out_root="output/experiments/sdc_pipeline_gem5"):
        self.out_root = out_root
        os.makedirs(out_root, exist_ok=True)
        self._goldens = {}  # ident -> {golden, nc, binary}

    def is_registered(self, ident: str) -> bool:
        return ident in self._goldens

    def register_golden(self, cand, force: bool = False):
        """跑一次 golden, 注册 {golden, nc, binary}。失败返回 None。"""
        if cand.ident in self._goldens and not force:
            return self._goldens[cand.ident]  # 幂等
        binary = os.path.join(self.out_root, f"wl_{cand.ident}")
        try:
            _compile_workload(cand, binary)
        except RuntimeError:
            return None
        outdir = os.path.join(self.out_root, f"golden_{cand.ident}")
        simout = _run_gem5_capture(binary, TAISHAN_SCRIPT,
                                   ["--binary", binary, "--mode", "baseline"],
                                   outdir)
        g = parse_golden(simout)
        if g is None:
            return None  # gem5 不兼容 (无输出/崩溃), 如实返回失败
        g["binary"] = binary
        self._goldens[cand.ident] = g
        return g

    def validate_detection(self, cand, n_runs: int, mode: str, seed: int,
                           jobs: int = 1) -> dict:
        """CHAOS 注入 n_runs 次 → diverge 率 + Wilson CI。
        必须先 register_golden 成功。"""
        if not 1 <= jobs <= MAX_JOBS:
            raise ValueError(f"jobs={jobs} 越界 (MCE 红线: 1..{MAX_JOBS})")
        g = self._goldens.get(cand.ident)
        if g is None:
            raise RuntimeError(f"{cand.ident} 未注册 golden, 先 register_golden")
        # fault-clock 从候选自己 nc 的 ROI 抽取 (dispatch 前抽完, 可复现)
        rng = random.Random(seed)
        roi_lo, roi_hi = int(g["nc"] * ROI[0]), int(g["nc"] * ROI[1])
        fault_clocks = [rng.randint(roi_lo, roi_hi) for _ in range(n_runs)]
        run_root = os.path.join(self.out_root, f"inject_{cand.ident}_{mode}")
        subprocess.run(["rm", "-rf", run_root], check=False)
        counts = {"clean_diverge": 0, "masked": 0, "exit_diverge": 0, "no_output": 0}
        for i, fc in enumerate(fault_clocks):
            outdir = os.path.join(run_root, f"run_{i:03d}")
            args = make_inject_cmd(g["binary"], TAISHAN_SCRIPT, fc, mode,
                                   seed + i)
            simout = _run_gem5_capture(g["binary"], TAISHAN_SCRIPT, args, outdir)
            wl = ""
            for line in simout.splitlines():
                if "SUM=" in line:
                    wl = line.strip()
                    break
            counts[classify_output(wl, g["golden"])] += 1
            # 清大文件 (sim_sweep 同语义)
            for junk in ("stats.txt", "config.ini", "config.json"):
                p = os.path.join(outdir, junk)
                if os.path.exists(p):
                    os.unlink(p)
        n = sum(counts.values())
        k = counts["clean_diverge"]
        lo, p, hi = wilson(k, n)
        return {"n": n, **counts, "rate": round(p, 4),
                "wilson_low": round(lo, 4), "wilson_high": round(hi, 4),
                "mode": mode, "seed": seed,
                "host": "local-0103-gem5", "gem5_note": "gem5 O3 model, not TSV110 RTL"}

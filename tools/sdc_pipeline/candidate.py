#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""candidate.py — Candidate 统一抽象 (sdc_pipeline 框架核心数据结构)。

R1 解法: 打通 "evolution_engine 硬编码 hex 短序列" 与 "seeds/*.S 模板体系"
两套割裂表示。Candidate 同时持有 .S 源文本 (可再变异/可入仓) 与编译后
bytes (Unicorn 直接执行), 身份 = 内容 hash (sha256[:12]), 血缘 = parents。

编译方式复刻 scripts/build_seeds.sh: 主机原生 aarch64, `as -I seeds` 汇编,
`objcopy -O binary -j .text` 抽取机器码。无交叉工具链依赖。
"""
import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEEDS_DIR = os.path.join(_REPO, "seeds")


def compile_asm(asm_text: str) -> bytes:
    """汇编 .S 文本 → 原始 AArch64 机器码 (.text 段)。

    与 build_seeds.sh 相同的管线: as -I seeds (asm_common.S.inc 宏可解析)
    → objcopy -O binary -j .text。汇编失败抛 RuntimeError (带 as 的报错)。
    """
    with tempfile.TemporaryDirectory(prefix="sdc_cand_") as td:
        src = os.path.join(td, "cand.S")
        obj = os.path.join(td, "cand.o")
        binp = os.path.join(td, "cand.bin")
        with open(src, "w") as f:
            f.write(asm_text)
        r = subprocess.run(["as", "-I", SEEDS_DIR, "-o", obj, src],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"as failed:\n{r.stderr}")
        r = subprocess.run(["objcopy", "-O", "binary", "-j", ".text", obj, binp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"objcopy failed:\n{r.stderr}")
        with open(binp, "rb") as f:
            return f.read()


@dataclass
class Candidate:
    """一个候选指令序列: .S 源 + 机器码 + 初始寄存器态 + 血缘。"""
    ident: str                    # sha256[:12] of (asm + regs)
    source_asm: str               # .S 全文 (可再变异)
    code_bytes: bytes             # 编译后 .text 机器码 (Unicorn 可执行)
    regs_init: dict               # {寄存器号 0..30: 64-bit 初值}
    parents: list                 # 父 Candidate ident 列表 (血缘链)
    origin: str                   # seed:<name> | mutate:<op> | evolve:<gen>
    structure_tags: list = field(default_factory=list)  # 结构标签 (AutoµSens 雏形)


def _check_regs(regs_init: dict):
    for r in regs_init:
        if not (isinstance(r, int) and 0 <= r <= 30):
            raise ValueError(f"寄存器号必须在 X0-X30 (拒绝 X31/越界): {r!r}")
        v = regs_init[r]
        if not (isinstance(v, int) and 0 <= v < (1 << 64)):
            raise ValueError(f"寄存器值必须是 [0, 2^64) 整数: {r}={v!r}")


def make_candidate(asm_text: str, regs_init: dict, parents: list, origin: str,
                   structure_tags: list | None = None) -> Candidate:
    """构造 Candidate: 编译 .S → bytes, 计算内容 hash 身份。"""
    _check_regs(regs_init)
    code = compile_asm(asm_text)
    h = hashlib.sha256()
    h.update(asm_text.encode())
    # 排序序列化保证 regs dict 顺序不影响身份
    for k in sorted(regs_init):
        h.update(f"{k}={regs_init[k]}".encode())
    ident = h.hexdigest()[:12]
    return Candidate(ident=ident, source_asm=asm_text, code_bytes=code,
                     regs_init=dict(regs_init), parents=list(parents),
                     origin=origin, structure_tags=list(structure_tags or []))

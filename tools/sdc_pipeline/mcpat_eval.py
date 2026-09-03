#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""mcpat_eval.py — McPAT 功耗 Evaluator 插件 (scheme §5.3 功耗维度落地)。

依赖: /home/sdc/wangxu/mcpat (官方 1.3, aarch64 编译) +
configs/tsv110.xml (TaiShan V110 参数, 安装与局限见
docs/experiments/2026-09-03-mcpat-setup.md)。

机制: 候选指令序列 → capstone 分类 (alu/mul/lsu/fpu/br) →
指令构成比映射为 tsv110.xml 的各单元 duty_cycle (活动因子) →
跑 mcpat 取 Runtime Dynamic 功耗。

诚实边界 (必须随指标携带):
- McPAT 最低支持 22nm, 真实 V110 是 7nm → 绝对功耗系统性高估,
  相对比较 (同工艺下 A vs B 候选) 可信度更高。
- 指标名 power_mcpat_w 且输出含 power_note 声明近似。
"""
import os
import re
import subprocess
import tempfile

import capstone

MCPAT_ROOT = os.path.expanduser("~/wangxu/mcpat")
MCPAT_BIN = os.path.join(MCPAT_ROOT, "mcpat")
TSV110_XML = os.path.join(MCPAT_ROOT, "configs", "tsv110.xml")

# tsv110.xml 里的基线 duty cycle (合成整数负载画像)
BASELINE_DUTY = {
    "IFU_duty_cycle": 0.9, "BR_duty_cycle": 0.72, "LSU_duty_cycle": 0.71,
    "MemManU_I_duty_cycle": 0.9, "MemManU_D_duty_cycle": 0.71,
    "ALU_duty_cycle": 0.76, "MUL_duty_cycle": 0.82, "FPU_duty_cycle": 0.41,
    "ALU_cdb_duty_cycle": 0.76, "MUL_cdb_duty_cycle": 0.82,
    "FPU_cdb_duty_cycle": 0.41,
}
POWER_NOTE = ("22nm McPAT approximation of 7nm TSV110; absolute values "
              "overestimated, relative comparisons more reliable")

_cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)


def classify_insns(code_bytes: bytes) -> dict:
    """capstone 反汇编 → 指令类别计数 {alu,mul,lsu,fpu,br,ifu}。"""
    cats = {"alu": 0, "mul": 0, "lsu": 0, "fpu": 0, "br": 0, "ifu": 0}
    for insn in _cs.disasm(code_bytes, 0x10000):
        m = insn.mnemonic
        if m.startswith(("b", "cb", "tb")) and m not in ("bic", "bfi"):
            cats["br"] += 1
        elif m.startswith(("ldr", "str", "ldp", "stp", "ldur", "stur")):
            cats["lsu"] += 1
        elif m.startswith(("f", "s", "u")) and m[-1].isdigit() or m.startswith(
                ("fmov", "fadd", "fmul", "fsub", "fdiv", "fsqrt", "fmadd")):
            cats["fpu"] += 1
        elif m.startswith(("mul", "madd", "msub", "smul", "umul", "smull", "umull")):
            cats["mul"] += 1
        else:
            cats["alu"] += 1
    return cats


def build_xml(cats: dict, total_insns: int, cycles: int) -> str:
    """指令构成 → duty cycle 映射 → 生成 tsv110.xml 变体。

    映射规则 (每周期 4 发射, duty = 该类指令占比 × 4, 截到 [0.05, 1.0]):
      alu 占比 a → ALU_duty = a*4 (基线 0.76 ≈ 19% 占比)
      同理 mul/fpu/lsu/br; IFU 恒 0.9 (取指几乎总忙)。
    """
    ratio = {k: (cats.get(k, 0) / total_insns if total_insns else 0.0)
             for k in ("alu", "mul", "lsu", "fpu", "br")}
    xml = open(TSV110_XML).read()
    # 每类占比 × 4-wide → duty; floor 0.05 (时钟树等常开), cap 1.0
    duty = {
        "ALU_duty_cycle": ratio["alu"] * 4, "ALU_cdb_duty_cycle": ratio["alu"] * 4,
        "MUL_duty_cycle": ratio["mul"] * 4, "MUL_cdb_duty_cycle": ratio["mul"] * 4,
        "FPU_duty_cycle": ratio["fpu"] * 4, "FPU_cdb_duty_cycle": ratio["fpu"] * 4,
        "LSU_duty_cycle": ratio["lsu"] * 4,
        "BR_duty_cycle": ratio["br"] * 4,
    }
    # IPC = total_insns / cycles → pipeline_duty_cycle
    ipc = (total_insns / cycles) if cycles else 2.0
    duty["pipeline_duty_cycle"] = min(1.0, ipc / 4.0)
    for k, v in duty.items():
        v = max(0.05, min(1.0, v))
        xml = re.sub(rf'(<stat name="{k}" value=")[\d.]+(")',
                     rf'\g<1>{v:.4f}\g<2>', xml)
    return xml


def run_mcpat(xml_text: str) -> dict:
    """跑一次 mcpat, 解析 Processor 级功耗/面积。"""
    with tempfile.TemporaryDirectory(prefix="mcpat_eval_") as td:
        x = os.path.join(td, "in.xml")
        with open(x, "w") as f:
            f.write(xml_text)
        r = subprocess.run([MCPAT_BIN, "-infile", x, "-print_level", "1"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"mcpat failed: {r.stderr[:300]}")
        out = r.stdout
    # Processor 级第一组 Area/Peak/Runtime
    proc = out.split("Processor:")[1] if "Processor:" in out else out
    def _grab(pat):
        m = re.search(pat, proc)
        return float(m.group(1)) if m else None
    return {
        "runtime_dynamic_w": _grab(r"Runtime Dynamic = ([\d.]+) W"),
        "peak_power_w": _grab(r"Peak Power = ([\d.]+) W"),
        "area_mm2": _grab(r"Area = ([\d.]+) mm\^2"),
    }


class McPATEvaluator:
    """功耗 Evaluator 插件: 候选指令构成 → duty cycle → mcpat 功耗。"""
    name = "mcpat_power"

    def __init__(self, cycles_per_insn: float = 0.5):
        # IPC 2.0 画像 (与 tsv110 基线一致)
        self.cycles_per_insn = cycles_per_insn

    def evaluate(self, cand) -> dict:
        cats = classify_insns(cand.code_bytes)
        total = sum(cats.values())
        if total == 0:
            return {"power_mcpat_w": 0.0, "power_note": POWER_NOTE}
        cycles = int(total * self.cycles_per_insn)
        xml = build_xml(cats, total, cycles)
        res = run_mcpat(xml)
        # 主指标用 Peak Power: McPAT 的 duty cycle 主要驱动 peak 计算
        # (实测: FPU满载 2.468W vs ALU满载 2.524W; runtime dynamic 对
        # duty 不敏感, 由 busy_cycles 驱动)。功耗应力筛选目标是"负载级
        # 差异", peak 更敏感。runtime_dynamic 保留作辅指标。
        w = res.get("peak_power_w") or 0.0
        return {"power_mcpat_w": round(w, 4),
                "runtime_dynamic_w": round(res.get("runtime_dynamic_w") or 0.0, 4),
                "power_note": POWER_NOTE}

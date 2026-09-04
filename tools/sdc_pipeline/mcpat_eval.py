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

# 2026-09-04: mcpat 升级为 third_party/mcpat submodule (wangxumarshall/mcpat
# master 3cf423f, 含 ARM64 Kunpeng920 支持)。旧 ~/wangxu/mcpat 安装已不存在,
# tsv110.xml 迁到本仓 tools/sdc_pipeline/mcpat_configs/ (升级记录见
# docs/experiments/2026-09-04-mcpat-submodule-upgrade.md)。
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MCPAT_ROOT = os.path.join(_REPO_ROOT, "third_party", "mcpat")
MCPAT_BIN = os.path.join(MCPAT_ROOT, "mcpat")
TSV110_XML = os.path.join(_REPO_ROOT, "tools", "sdc_pipeline", "mcpat_configs", "tsv110.xml")

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
    """指令构成 → tsv110.xml 变体 (duty cycle + 全套 access 统计双通道)。

    2026-09-04 submodule 升级后的口径: 新 mcpat 的 out.ptrace 走
    get_power() = rt_power/executionTime + leakage, 由 XML 的**统计**
    (FU accesses / cache read+write_accesses / window 读写) 驱动;
    duty cycle 只进 TDP/peak, 而文本版 peak 输出已被上游注释掉。
    故本函数同时改两组字段:
      1. duty cycle (原逻辑保留, 每周期 4 发射, 占比×4 截到 [0.05,1.0])
      2. 统计画像: 把"该指令构成若跑满 cyc 周期"的各单元访问次数写全
         (FU/cdb/window/load/store/cache), 与基线 total_cycles 同量纲。
    实测区分度 (cyc=100k): 基线 1.13W, ALU 1.22W, MUL 1.43W,
    FPU 1.49W, LSU 1.59W — 指令构成差异可检出。
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

    # ---- 统计画像 (runtime 功耗主驱动, 与基线 total_cycles=100k 同量纲) ----
    cyc = 100000  # 固定与 tsv110 基线 total_cycles 同规模, executionTime 不变
    n_insn = cyc * 4                       # 4-wide 满发射的指令总数
    n_fu = {k: int(ratio[k] * n_insn) for k in ("alu", "fpu", "mul")}
    n_lsu = int(ratio["lsu"] * n_insn)
    n_fetch = int(n_insn * 1.2)            # 取指含未提交近似 (基线口径同倍率)
    acc = {
        # FU 执行 + 结果广播
        "ialu_accesses": n_fu["alu"], "cdb_ialu_accesses": n_fu["alu"],
        "fpu_accesses": n_fu["fpu"], "cdb_fpu_accesses": n_fu["fpu"],
        "mul_accesses": n_fu["mul"], "cdb_mul_accesses": n_fu["mul"],
        # LSU: load/store 指令数 (基线 load:store = 2:1)
        "load_instructions": n_lsu * 2 // 3, "store_instructions": n_lsu // 3,
        # 调度窗口: 每条指令 1 写 + 2 读 + 唤醒/选择
        "inst_window_writes": n_insn, "inst_window_reads": n_insn,
        "inst_window_wakeup_accesses": n_insn, "inst_window_selections": n_insn,
        "fp_inst_window_writes": n_fu["fpu"], "fp_inst_window_reads": n_fu["fpu"],
        "fp_inst_window_wakeup_accesses": n_fu["fpu"],
        # ROB: 3 读 (dispatch/execute/commit) + 1 写
        "ROB_reads": n_insn * 3, "ROB_writes": n_insn,
        # 指令流 (驱动 IB/ID 解码等): tsv110 用 total_instructions
        "total_instructions": n_insn,
    }
    for k, v in acc.items():
        xml = re.sub(rf'(<stat name="{k}" value=")[\d.]+(")',
                     rf'\g<1>{v}\g<2>', xml)
    # 各 cache 的访问统计是嵌套 <stat>, 全局同名不能一把替换 — 只在对应
    # component 块内改。基线→画像倍率: icache=n_fetch/200000,
    # dcache 读写=n_lsu 相关, BTB=br 占比驱动 (基线 30k)。
    def _sub_in_block(xml, comp_id, name, val):
        # 在 component 块内替换 (tsv110.xml 每个此类 stat 名在块内唯一)
        pat = re.compile(
            rf'(<component id="{comp_id}"[^>]*>.*?<stat name="{name}" value=")[\d.]+(")',
            re.DOTALL)
        return pat.sub(rf'\g<1>{val}\g<2>', xml, count=1)
    base_fetch = 200000
    xml = _sub_in_block(xml, "system.core0.icache", "read_accesses", n_fetch)
    xml = _sub_in_block(xml, "system.core0.icache", "read_misses",
                        int(n_fetch / base_fetch * 500))
    xml = _sub_in_block(xml, "system.core0.dcache", "read_accesses", n_lsu * 2 // 3)
    xml = _sub_in_block(xml, "system.core0.dcache", "write_accesses", n_lsu // 3)
    xml = _sub_in_block(xml, "system.core0.dtlb", "total_accesses", n_lsu)
    xml = _sub_in_block(xml, "system.core0.BTB", "read_accesses",
                        int(ratio["br"] * n_insn))
    return xml


def run_mcpat(xml_text: str) -> dict:
    """跑一次 mcpat, 解析功耗/面积。

    2026-09-04 输出口径变化: submodule 版 mcpat (fork 758d196 起) 不再打印
    "Runtime Dynamic = X W" / "Peak Power = X W" 文本, 改为写 out.ptrace
    (每块功耗一行) 与 out.area (每块面积一行) 到进程 cwd。故 subprocess 必须
    cwd=tmpdir 且 infile 用绝对路径; 功耗 = out.ptrace 数值行 sum (总量) /
    max (峰值块)。旧 v1.3 文本口径的数字 (如 tsv110 基线 Peak 4.42W) 与新
    口径不可直接对比。
    """
    with tempfile.TemporaryDirectory(prefix="mcpat_eval_") as td:
        x = os.path.abspath(os.path.join(td, "in.xml"))
        with open(x, "w") as f:
            f.write(xml_text)
        r = subprocess.run([MCPAT_BIN, "-infile", x, "-print_level", "1"],
                           capture_output=True, text=True, timeout=120,
                           cwd=td)
        if r.returncode != 0:
            raise RuntimeError(f"mcpat failed: {r.stderr[:300]}")
        ptrace = os.path.join(td, "out.ptrace")
        if not os.path.exists(ptrace):
            raise RuntimeError("mcpat produced no out.ptrace (cwd 或输出口径异常)")
        # out.ptrace: 第 1 行块名 TAB 行, 第 2 行每块功耗; 第 3 行起是
        # -trace 模式的逐条 dump (我们没开 -trace, 只有一组)
        with open(ptrace) as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        vals = [float(t) for t in lines[1].split()]
        # stdout 一行是 dump_area 的每块面积 (与 out.area 第 2 行一致)
        areas = [float(t) for t in r.stdout.split()]
    return {
        "runtime_dynamic_w": sum(vals),
        "peak_power_w": max(vals),
        "area_mm2": sum(areas),
    }


class McPATEvaluator:
    """功耗 Evaluator 插件: 候选指令构成 → duty cycle → mcpat 功耗。"""
    name = "mcpat_power"

    def __init__(self, cycles_per_insn: float = 0.5):
        # IPC 2.0 画像 (与 tsv110 基线一致)
        self.cycles_per_insn = cycles_per_insn
        self.last_note = ""  # 最近一次评估的诚实边界声明

    def evaluate(self, cand) -> dict:
        cats = classify_insns(cand.code_bytes)
        total = sum(cats.values())
        if total == 0:
            self.last_note = POWER_NOTE
            return {"power_mcpat_w": 0.0}
        cycles = int(total * self.cycles_per_insn)
        xml = build_xml(cats, total, cycles)
        res = run_mcpat(xml)
        # 2026-09-04 主指标改为 total (out.ptrace 逐块功耗之和): 新口径下
        # peak_power_w 是"最大单块功耗"(ICache 恒最大, 对指令构成不敏感),
        # total 才随指令构成单调变化 (实测: ALU 1.57 < MUL 1.78 < FPU 1.86
        # < LSU 2.91W)。旧口径注释 (FPU 2.468 vs ALU 2.524 peak) 已过时。
        w = res.get("runtime_dynamic_w") or 0.0
        # power_note 是诚实边界声明, 不是数值指标 — 放 self.last_note
        # (进 metrics 会污染 pipeline 的均值聚合)
        self.last_note = POWER_NOTE
        return {"power_mcpat_w": round(w, 4),
                "peak_block_w": round(res.get("peak_power_w") or 0.0, 4)}

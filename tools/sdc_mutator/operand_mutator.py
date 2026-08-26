#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""operand_mutator.py — 操作数空间引导变异引擎

设计概念落地（"指令空间 → 操作数·执行上下文空间"）：
不要只让 add x0,x1,x2 执行过一次。对每条关键指令，遍历操作数的极端值
组合（全0/全1/交替位/进位边界/subnormal/NaN...），把覆盖率空间从
"指令种类"扩展到"操作数组合"——非随机，而是字典引导的系统性遍历。

工作方式：
  1. 读取一个模板 .S 文件，扫描形如 `// MUT: <slot_name>` 的标记行，
     其上一行是待变异的指令（含 %PLACEHOLDER% 占位或宏调用）。
  2. 从 operand_dict.md 解析对应 slot 的种子列表。
  3. 对每个种子的 (movz/movk 编码) 做笛卡尔积替换，生成 N 个变体 .S。
  4. 每个变体保持模板的微架构压力拓扑不变，只换操作数 → 激活不同 Gate 子集。

示例 (e1_carry_chain 模板的可变异槽 = 进位链长度):
  // MUT: carry_chain
  LOAD_ALL_ONES x1        ← 这一行被替换为 LOAD_CARRY32 / LOAD_CARRY48 / ...
  mov x2, #1
  adds x0, x1, x2

用法:
  operand_mutator.py <template.S> <out_dir> [--max-variants N]
"""
import os, re, sys, itertools, pathlib

# 操作数种子字典 (与 seeds/operand_dict.md 一致)
# 每个 slot → [(标签, 构造代码), ...]
# 构造代码是可直接替换进 .S 的宏调用或指令序列。
INT_DICT = [
    ("all_ones",    "LOAD_ALL_ONES  x1"),
    ("alt_01",      "LOAD_ALT_01    x1"),
    ("alt_10",      "LOAD_ALT_10    x1"),
    ("carry32",     "LOAD_CARRY32   x1"),
    ("carry48",     "LOAD_CARRY48   x1"),
    ("byte_alt",    "LOAD_BYTE_ALT  x1"),
    ("half_alt",    "LOAD_HALF_ALT  x1"),
    ("max_pos",     "LOAD_MAX_POS   x1"),
    ("min_neg",     "LOAD_MIN_NEG   x1"),
    ("zero",        "movz x1, #0"),
]
FSU_DICT = [
    ("normal_1",    "fmov d1, #1.0"),
    ("subnormal",   "LOAD_SUBNORMAL_MIN d1, x0"),
    ("qnan",        "LOAD_QNAN       d1, x0"),
    ("pos_inf",     "LOAD_POS_INF    d1, x0"),
    ("neg_zero",    "LOAD_NEG_ZERO   d1, x0"),
    ("max_finite",  "LOAD_MAX_FINITE d1, x0"),
]

SLOTS = {
    "int": INT_DICT,            # 整数操作数槽 (10 种)
    "fsu": FSU_DICT,           # 浮点操作数槽 (6 种)
    "carry_chain": INT_DICT,   # 进位链变体 (整数字典)
}

def parse_template(path):
    """返回 (lines, mut_blocks)。
    // MUT: <slot> 标记单独占一行, 其下一行(非空非注释)是可变异指令。
    mut_blocks = [(slot_name, line_index, original_line), ...]"""
    lines = open(path).read().splitlines()
    muts = []
    for i, line in enumerate(lines):
        m = re.search(r'//\s*MUT:\s*(\w+)', line)
        if m:
            slot = m.group(1)
            # 可变异指令是标记行的下一行 (非空非注释)
            j = i + 1
            while j < len(lines) and (lines[j].strip() == '' or lines[j].strip().startswith('//')):
                j += 1
            if j < len(lines):
                muts.append((slot, j, lines[j]))
    return lines, muts

def extract_reg(line):
    """从一条 LOAD_* / mov / fmov 指令提取目标寄存器名。
    例: 'LOAD_ALL_ONES  x1' -> 'x1'; 'LOAD_SUBNORMAL_MIN d1, x0' -> 'd1'(首目标)。
    支持 'rd, xt' 形式 (取 rd)。"""
    # 去注释 + strip
    code = line.split('//')[0].strip()
    # 去宏名/指令助记符 (第一个 token)
    parts = code.split(None, 1)
    if len(parts) < 2:
        return None
    operands = parts[1].replace(',', ' ').split()
    for op in operands:
        # 取第一个寄存器操作数 (x/d/v/w/h + 数字)
        if re.match(r'^[xdvwqh]\d+', op):
            return op
    return None

def adapt_code(code, reg):
    """把字典构造代码的目标寄存器替换为模板的 reg。
    字典代码形如 'LOAD_ALL_ONES  x1' 或 'fmov d1, #1.0' 或 'LOAD_SUBNORMAL_MIN d1, x0'。
    首个寄存器替换为 reg。"""
    # 找首个寄存器 token 替换
    m = re.search(r'\b([xdvwqh]\d+)\b', code)
    if m:
        return code[:m.start()] + reg + code[m.end():]
    return code

def generate_variants(template_path, out_dir, max_variants=None):
    lines, muts = parse_template(template_path)
    if not muts:
        return 0
    # 每个槽的字典 + 原寄存器
    dicts = []
    for slot, _, orig in muts:
        d = SLOTS.get(slot, INT_DICT)
        dicts.append(d)
    # 笛卡尔积
    combos = list(itertools.product(*dicts))
    if max_variants:
        combos = combos[:max_variants]
    base = pathlib.Path(template_path).stem
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for combo in combos:
        variant = lines[:]
        for (slot, line_idx, orig), (label, code) in zip(muts, combo):
            # 提取原寄存器, 注入到字典代码
            reg = extract_reg(orig) or 'x1'
            adapted = adapt_code(code, reg)
            indent = len(variant[line_idx]) - len(variant[line_idx].lstrip())
            variant[line_idx] = ' ' * indent + adapted + f"    // variant:{slot}={label}"
        tag = "_".join(label for _, (label, _) in zip(muts, combo))
        out = os.path.join(out_dir, f"{base}__{tag}.S")
        with open(out, 'w') as f:
            f.write("\n".join(variant) + "\n")
        n += 1
    return n

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    tpl = sys.argv[1]
    out = sys.argv[2]
    mx = None
    if "--max-variants" in sys.argv:
        mx = int(sys.argv[sys.argv.index("--max-variants")+1])
    n = generate_variants(tpl, out, mx)
    print(f"Generated {n} variant(s) from {tpl} -> {out}")

if __name__ == "__main__":
    main()

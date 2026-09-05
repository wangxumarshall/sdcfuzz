#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sdcbench_gen2.py — 高 SDC 结构定向补充生成器

依据 batch1-3 实测结论的定向设计 (实时策略调整):
  - 全 1.0 组: adds/subs/add/eor/bic (翻转直接传播)
  - 低分组根因: orr 饱和掩蔽 (x|=c → 全1), mul 低位清零区, mixed 混入掩蔽 op
  - 修补: madd (乘+加, 加法保证传播), eon (反转异或, 位保真), 移位链 (lsl/lsr,
    bit 位移不销毁信息), 以及 adds/eor 的双 op 交替链 (微架构多样性, 均为传播 op)
起点 id 从 2000 起, 不与 pool 冲突.
"""
import os, sys, json, random, subprocess

sys.path.insert(0, os.path.dirname(__file__))
from sdcbench_gen import OPERAND_FAMILIES, movz_seq, C_TEMPLATE

GOOD_OPS = {
    "adds": "adds x{d}, x{d}, x{a}",
    "subs": "subs x{d}, x{d}, x{a}",
    "add":  "add  x{d}, x{d}, x{a}",
    "eor":  "eor  x{d}, x{d}, x{a}",
    "bic":  "bic  x{d}, x{d}, x{a}",
    "madd": "madd x{d}, x{d}, x{a}, x{a}",      # d = d*a + a: 加法保传播
    "eon":  "eon  x{d}, x{d}, x{a}",           # d = d ^ ~a: 位保真翻转
    "lsl":  "lsl  x{d}, x{d}, #3",             # 移位链 (信息守恒)
    "lsr":  "lsr  x{d}, x{d}, #3",
    "alt":  None,                               # adds/eor 交替
    "alt2": None,                               # madd/adds 交替
}


def gen_asm(op_name, init_val, step_val, iters, seed):
    rng = random.Random(seed)
    lines = []
    for i in range(8):
        rot = ((init_val << (i * 7)) | (init_val >> (64 - i * 7))) & 0xFFFFFFFFFFFFFFFF if i else init_val
        v = (rot ^ (0x9E3779B97F4A7C15 * (i + 1))) & 0xFFFFFFFFFFFFFFFF
        lines.append(movz_seq(i, v))
    lines.append(movz_seq(9, step_val))
    lines.append(movz_seq(10, (step_val ^ 0xA5A5A5A5A5A5A5A5) & 0xFFFFFFFFFFFFFFFF))
    lines.append(f".rept {iters}")
    for i in range(8):
        src = 9 if (i + iters) % 2 == 0 else 10
        if op_name == "alt":
            op = "adds" if (iters + i) % 2 == 0 else "eor"
            lines.append(GOOD_OPS[op].format(d=i, a=src))
        elif op_name == "alt2":
            op = "madd" if (iters + i) % 2 == 0 else "adds"
            lines.append(GOOD_OPS[op].format(d=i, a=src))
        elif op_name in ("lsl", "lsr"):
            lines.append(GOOD_OPS[op_name].format(d=i))
        else:
            lines.append(GOOD_OPS[op_name].format(d=i, a=src))
    lines.append(".endr")
    for i in range(1, 8):
        lines.append(f"eor x0, x0, x{i}")
    return "\n".join(lines)


def gen_source(op_name, init_val, step_val, iters, seed):
    asm = gen_asm(op_name, init_val, step_val, iters, seed)
    asm_lines = "\n".join(f'        "{l}\\n"' for l in asm.split("\n"))
    return C_TEMPLATE.replace("{ASM}", asm_lines)


def main():
    out_dir = sys.argv[1]
    n_target = int(sys.argv[2])
    start_id = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
    os.makedirs(os.path.join(out_dir, "src"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "bin"), exist_ok=True)
    manifest = []
    seq_id = start_id
    rng = random.Random(424242)
    combo_round = 0
    while seq_id < start_id + n_target:
        for op in GOOD_OPS:
            for fam_name, init_v, step_v in OPERAND_FAMILIES:
                for iters in (60, 80, 100, 120):
                    if seq_id >= start_id + n_target:
                        break
                    seed = rng.randrange(1 << 30)
                    name = f"seq_{seq_id:04d}_{op}_{fam_name}_i{iters}" + (f"_v{combo_round}" if combo_round else "")
                    src = gen_source(op, init_v, step_v, iters, seed)
                    src_path = os.path.join(out_dir, "src", name + ".c")
                    bin_path = os.path.join(out_dir, "bin", name)
                    with open(src_path, "w") as f:
                        f.write(src)
                    r = subprocess.run(["gcc", "-static", "-O2", "-o", bin_path, src_path],
                                       capture_output=True, text=True)
                    if r.returncode != 0:
                        continue
                    manifest.append({"name": name, "id": seq_id, "op": op, "family": fam_name,
                                     "iters": iters, "seed": seed, "init": hex(init_v),
                                     "step": hex(step_v), "bin": os.path.abspath(bin_path),
                                     "src": os.path.abspath(src_path)})
                    seq_id += 1
                if seq_id >= start_id + n_target:
                    break
            if seq_id >= start_id + n_target:
                break
        combo_round += 1
        if combo_round > 12:
            break
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w"), indent=1)
    print(f"Generated {len(manifest)} sequences in {out_dir} (ids {start_id}..{seq_id-1})")


if __name__ == "__main__":
    main()

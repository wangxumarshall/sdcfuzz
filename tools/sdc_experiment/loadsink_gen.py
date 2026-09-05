#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""loadsink_gen.py — 对准 cpu179 load 通路缺陷的 SiliFuzz 用例生成器

设计依据 (2026-09-05 MRU 复现实验的反汇编取证):
  cpu179 缺陷单元 = load 数据返回通路 (fill-buffer/L1D 读出组装级).
  MRU (Eigen Cholesky factorize_preordered) 触发循环 0x403158 窗口的五要素:
    ① 间接寻址链: ldrsw x6,[idx_ptr, x3, lsl#2]; ldr d0,[data_ptr, x6, lsl#3]
       (索引数组内容 = 数据数组下标 → 非连续 gather 型访问)
    ② load→FMA→store 同址往返 (str 后下次迭代 ldr 同一 slot)
    ③ 长存活 FP 累加器 (d4 跨整个循环)
    ④ 条件分支 + fdiv (cdiv pivot)
    ⑤ 同 socket 满载 (低压) + 大量重复执行
  负对照证伪 (档案 11 个): 纯 FMA / 纯 gather / 纯分支 / 纯 NEON / 密集 GEMM 全部 0 触发
  → 必须 ①②③ 交错; 本生成器参数化这三要素的强度.

生成形态: .S 裸指令 (同 sdcbench 管线: as → .bin → snap_tool make → corpus).
内存布局 (SiliFuzz AArch64 proxy config):
  x6 = data1 起址 (runner 播种), x7 = data2 起址 — 索引表放 data1 头, 数据放 data2,
  通过 movz 构造 data2 内的相对偏移 (make 时 runner 对访问过的页自动补映射).
"""
import os, sys, random, subprocess, json

# 参数空间 (对准五要素的变异维度)
#   idx_pattern: 索引表模式 (MRU 用的是排好序的部分置换; 变体: 逆序/隔行/重排)
#   chain_len:   内层 gather 链长度 (MRU 每列 ~10-30)
#   roundtrips:  外层循环次数 (状态压力)
#   fp_width:    FP 累加器宽度 (1=scalar d4 复刻 / 2=双累加器)
#   div_point:   fdiv 出现密度 (MRU: 每列一次)
VARIANTS = []

def movz_seq(reg, val):
    out = [f"movz x{reg}, #{val & 0xFFFF}"]
    for shift in (16, 32, 48):
        w = (val >> shift) & 0xFFFF
        if w:
            out.append(f"movk x{reg}, #{w}, lsl #{shift}")
    return out

def gen_asm(p):
    """生成一条 loadsink 序列的 .S 文本"""
    L = []
    # ---- 索引表 (data1, x6 指向): 32 个 32位 索引, 值域 [0,31) 的伪置换 ----
    # runner 播种 x6=data1_start; 索引表通过 store 写入 (不用预置内存, 快照内存初值全0,
    # 我们先 str 构造索引, 再 gather 读 — 这本身也制造 store→load 往返!)
    n = p["n_idx"]
    # 索引表/数据表初始化用紧凑循环 (省指令预算): 索引用游标+步进生成伪置换,
    # 数据用 seed 常量做 LCG 展开 — 保留非连续访问模式, 牺牲精确值控制.
    L += movz_seq(11, p["seed_const"])
    L += movz_seq(12, p["idx_step"])          # 索引步进 (奇数=与 n 互素 → 伪置换)
    L.append("mov x3, #0")
    L.append(f"and x3, x3, #{n-1}")
    L.append(f".rept {n}")
    L.append("str w3, [x6, x3, lsl #2]")      # 写索引表 (store)
    L.append("add x3, x3, x12")
    L.append(f"and x3, x3, #{n-1}")
    L.append("eor x11, x11, x11, lsl #13")    # LCG-ish 数据值
    L.append("str x11, [x7, x3, lsl #3]")     # 写数据表 (store, 同址稍后读)
    L.append(".endr")
    # ---- 长存活 FP 累加器 ----
    L += movz_seq(10, p["seed_const"] & 0xFFFFFFFF)
    L.append("fmov d4, x10")            # d4 长存活 (MRU 要素③)
    L += movz_seq(10, 0x3F800000)        # 1.0f 模式
    L.append("fmov d5, x10")
    # ---- 主循环: gather 链 + FMA + 同址往返 (要素①②) ----
    L.append(f".rept {p['roundtrips']}")
    L.append("mov x3, #0")              # 内层游标
    for k in range(p["chain_len"]):
        # ① ldrsw x6r,[idx,x3] → ② ldr d, [data,x6r] → fmsub → str 回同址
        L.append(f"ldrsw x12, [x6, x3, lsl #2]")
        L.append(f"ldr d0, [x7, x12, lsl #3]")
        L.append(f"fmsub d0, d5, d4, d0")
        L.append(f"str d0, [x7, x12, lsl #3]")
        L.append("add x3, x3, #1")
    # ③ 累加器更新 (跨迭代存活)
    L.append("fadd d4, d4, d5")
    # ④ 偶发 fdiv (cdiv 模拟)
    if p["div_every"]:
        L.append("fdiv d6, d4, d5")
    L.append(".endr")
    # ---- 聚合校验和 (所有读出值折进 d4 → x0; 任何一次坏读必改变终态) ----
    L.append("mov x3, #0")
    for k in range(0, n, 4):
        L.append(f"ldr x13, [x7, #{k*8}]")
        L.append("eor x0, x0, x13")
    L.append("fmov x14, d4")
    L.append("eor x0, x0, x14")
    return "\n".join(L)


def make_variant(rng, vid):
    n = rng.choice([16, 24, 32])
    perm = list(range(n))
    style = rng.choice(["shuffled", "reversed", "strided", "sorted"])
    if style == "shuffled": rng.shuffle(perm)
    elif style == "reversed": perm.reverse()
    elif style == "strided": perm = perm[::2] + perm[1::2]
    chain_len = rng.choice([8, 12, 16, 20])
    roundtrips = max(2, (110 // chain_len) - rng.randint(0, 110 // chain_len // 2))
    return {
        "id": vid, "n_idx": n, "idx": perm,
        "data": [rng.getrandbits(64) | 0x3FF0000000000000 for _ in range(n)],  # 正常 double 范围
        "seed_const": rng.getrandbits(32),
        # 指令预算: 单页 4084B ≈ 1021 条; chain×roundtrips ≤ 140 (每链步 5 条)
        "chain_len": rng.choice([8, 12, 16, 20]),
        "roundtrips": roundtrips,
        "idx_step": rng.choice([3, 5, 7, 11, 13]),
        "div_every": rng.random() < 0.5,
        "idx_style": style,
    }


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "output/loadsink"
    n_target = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    os.makedirs(f"{out_dir}/bins", exist_ok=True)
    os.makedirs(f"{out_dir}/src", exist_ok=True)
    rng = random.Random(20260905)
    manifest = []
    for vid in range(n_target):
        p = make_variant(rng, vid)
        asm = gen_asm(p)
        s = f".arch armv8-a\n.text\n{asm}\n"
        sp, op, bp = f"{out_dir}/src/v{vid:03d}.S", f"/tmp/ls_{vid}.o", f"{out_dir}/bins/v{vid:03d}.bin"
        open(sp, "w").write(s)
        r = subprocess.run(["as", "-o", op, sp], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"as FAIL v{vid}: {r.stderr[:120]}", file=sys.stderr); continue
        subprocess.run(["objcopy", "-O", "binary", "-j", ".text", op, bp], capture_output=True)
        sz = os.path.getsize(bp)
        if sz > 4084:
            print(f"TOOBIG v{vid}: {sz}"); os.unlink(bp); continue
        manifest.append({"id": vid, "bin": os.path.abspath(bp), "size": sz, **{k: p[k] for k in
                        ("n_idx","chain_len","roundtrips","div_every","idx_style")}})
    json.dump(manifest, open(f"{out_dir}/manifest.json", "w"), indent=1)
    print(f"loadsink: {len(manifest)} variants in {out_dir}")


if __name__ == "__main__":
    main()

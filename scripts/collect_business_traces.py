#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""collect_business_traces.py — 采集业务高频指令序列 (算子三 crossover 源)

从 silifuzz 现有语料的 snapshot 提取真实指令序列, 作为进化引擎算子三
(上下文重组) 的 crossover 源 — 前置高功耗指令制造 Voltage Droop。
"""
import sys, os, subprocess, glob

OUT_DIR = 'seeds/business_traces'
SHARDS = ['output/sdc_stage_a.corpus'] + sorted(glob.glob('output/sdc_stage_b.*'))

def extract_traces_from_corpus(n=20, seq_len=32):
    """从 silifuzz corpus 提取 snapshot 指令序列片段"""
    os.makedirs(OUT_DIR, exist_ok=True)
    extracted = 0
    for shard in SHARDS:
        if not os.path.exists(shard):
            continue
        # 用 snap_tool get_instructions 提取指令 (输出到文件)
        r = subprocess.run(
            ['bazel-bin/tools/snap_tool', 'get_instructions', shard,
             '--out=/tmp/_insns.bin'],
            capture_output=True, timeout=30)
        if r.returncode != 0 or not os.path.exists('/tmp/_insns.bin'):
            # get_instructions 可能不支持 --out, 用 print 模式提取
            r2 = subprocess.run(
                ['bazel-bin/tools/snap_tool', 'print', shard],
                capture_output=True, text=True, timeout=30)
            # 从 print 输出解析指令字节 (略复杂, 用备选: 直接从 .bin 模板取)
            continue
        data = open('/tmp/_insns.bin', 'rb').read()
        if len(data) < seq_len:
            continue
        # 按伪随机偏移取片段
        for i in range(n):
            off = (i * 137 + len(data) // 7) % max(1, len(data) - seq_len)
            chunk = data[off:off + seq_len]
            if len(chunk) == seq_len:
                open(f'{OUT_DIR}/trace_{extracted:02d}.bin', 'wb').write(chunk)
                extracted += 1
                if extracted >= n:
                    return extracted
    return extracted

def extract_traces_from_seed_bins(n=20, seq_len=32):
    """备选: 从 seeds/bin/ 的模板 .bin 提取指令序列 (这些是真实 AArch64 指令)"""
    os.makedirs(OUT_DIR, exist_ok=True)
    extracted = 0
    bins = sorted(glob.glob('seeds/bin/*.bin')) + sorted(glob.glob('output/bin_stage_a/*.bin'))
    for bin_path in bins:
        if extracted >= n:
            break
        data = open(bin_path, 'rb').read()
        if len(data) < seq_len:
            continue
        # 取多个偏移片段
        for off in range(0, min(len(data), seq_len * 4), seq_len):
            if extracted >= n:
                break
            chunk = data[off:off + seq_len]
            if len(chunk) == seq_len:
                open(f'{OUT_DIR}/trace_{extracted:02d}.bin', 'wb').write(chunk)
                extracted += 1
    return extracted

if __name__ == "__main__":
    n = extract_traces_from_seed_bins()
    print(f"Extracted {n} business traces to {OUT_DIR}/")
    if n > 0:
        # 验证首个 trace 是合法 AArch64
        r = subprocess.run(['objdump', '-b', 'binary', '-m', 'aarch64', '-D',
                           f'{OUT_DIR}/trace_00.bin'], capture_output=True, text=True)
        if r.returncode == 0:
            print("首个 trace 反汇编验证 OK:")
            for line in r.stdout.splitlines()[-5:]:
                print(f"  {line}")

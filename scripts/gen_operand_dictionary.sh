#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# gen_operand_dictionary.sh — 从 operand_dict 生成 AFL/libFuzzer 格式 dictionary
#
# 项14: Centipede 变异器定制。Centipede --dictionary 接受 AFL/libFuzzer 格式
# (行 "kw1","kw2",... 或每行 "name"="bytes")。把操作数字典的极端值作为 dictionary
# 项, 引导 Centipede 变异器倾向操作数空间的极端值 (全0/全1/交替/subnormal/NaN),
# 提升操作数空间探索效率。
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-output/operand_dict.txt}

cat > "$OUT" << 'EOF'
# AFL/libFuzzer 格式操作数 dictionary (从 operand_dict.md 生成)
# 引导 Centipede 变异器倾向操作数空间极端值
EOF

# 整数极端值 (little-endian 字节序列)
python3 - "$OUT" << 'PY'
import sys, struct
out = sys.argv[1]
with open(out, "a") as f:
    ints = {
        "all_zero": 0x0000000000000000,
        "all_ones": 0xFFFFFFFFFFFFFFFF,
        "alt_01":   0x5555555555555555,
        "alt_10":   0xAAAAAAAAAAAAAAAA,
        "carry32":  0x00000000FFFFFFFF,
        "carry48":  0x0000FFFFFFFFFFFF,
        "byte_alt":0x00FF00FF00FF00FF,
        "max_pos":  0x7FFFFFFFFFFFFFFF,
        "min_neg":  0x8000000000000000,
        "one":      0x0000000000000001,
    }
    for name, v in ints.items():
        b = struct.pack("<Q", v)
        f.write(f'{name}="{b.hex()}"\n')
    # FSU 特殊值
    fsu = {
        "subnormal_min": 0x0000000000000001,
        "qnan":          0x7FF8000000000000,
        "pos_inf":       0x7FF0000000000000,
        "neg_zero":      0x8000000000000000,
        "max_finite":    0x7FEFFFFFFFFFFFFF,
    }
    for name, v in fsu.items():
        b = struct.pack("<Q", v)
        f.write(f'{name}="{b.hex()}"\n')
print(f"Generated dictionary: {out}")
PY
echo "=== dictionary 内容预览 ==="
head -5 "$OUT"
echo "..."
echo "总项数: $(grep -c '\"' "$OUT")"
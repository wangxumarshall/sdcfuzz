#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# build_seeds.sh — 编译所有 SDC 攻击向量汇编种子为原始机器码 .bin
#
# 设计概念落地: 模板是骨架, 经 Centipede 在操作数空间做引导式变异。
# 每个 .bin 是 Centipede --corpus_from_files 的种子 (每文件一输入)，
# 也可直接经 snap_tool --raw make 转 Snapshot。
#
# 主机原生 aarch64, as/objcopy 即原生汇编器, 无需交叉工具链。
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p seeds/bin

SRC_DIR=seeds
BIN_DIR=seeds/bin
count=0
failed=0

for src in "$SRC_DIR"/*.S; do
    [ -e "$src" ] || continue
    name=$(basename "$src" .S)
    obj="/tmp/${name}.o"
    bin="$BIN_DIR/${name}.bin"
    # 汇编 (asm_common.S.inc 在 seeds/ 目录, -I 指向之)
    if as -I "$SRC_DIR" -o "$obj" "$src" 2>/tmp/as_err_${name}.log; then
        # 抽取 .text 段为原始机器码 (little-endian, AArch64)
        objcopy -O binary -j .text "$obj" "$bin"
        sz=$(stat -c%s "$bin")
        echo "OK   ${name}.bin  (${sz} bytes)"
        count=$((count+1))
    else
        echo "FAIL ${name}.S"
        sed 's/^/     /' /tmp/as_err_${name}.log
        failed=$((failed+1))
    fi
done

echo "-----"
echo "Generated: $count seed(s), failed: $failed"
exit $((failed > 0 ? 1 : 0))

#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# deploy_board.sh — 部署静态二进制 + SDC 语料到远程单板
#
# runner + orchestrator 是 statically linked ELF aarch64 (实测可跨机运行)。
# 从 0103 (编译机) 拷贝预编译二进制 + SDC 语料到各扫描单板, 无需每台重新编译。
# snap_tool/simple_fix_tool_main 是动态 PIE (openEuler 24.03 同构 glibc, 也可跑)。
#
# 用法: deploy_board.sh <board_ip> [board_ip2 ...]
#       deploy_board.sh --all   # 部署到 0101/0102 (0103 本机已有)
set -euo pipefail
cd "$(dirname "$0")/.."

TOOLS_SRC=/usr/local/bin
CORPUS_SRC=output
REMOTE_TOOLS=/sdc_tools
REMOTE_CORPUS=/sdc_corpus
SSH_USER=root
PY="python3 $(dirname "$0")/ssh_lib.py"

deploy_one() {
  local ip=$1
  echo "=== 部署到 $ip (user=$SSH_USER, dir=$REMOTE_TOOLS) ==="
  # 建目录
  $PY "$ip" "mkdir -p $REMOTE_TOOLS $REMOTE_CORPUS" --user "$SSH_USER" >/dev/null 2>&1 || true
  # 拷贝静态二进制 (runner + orchestrator 静态, snap_tool/simple_fix_tool 动态 PIE)
  for bin in reading_runner_main_nolibc silifuzz_orchestrator_main snap_tool simple_fix_tool_main; do
    if [ -f "$TOOLS_SRC/$bin" ]; then
      $PY scp "$TOOLS_SRC/$bin" "$ip" "$REMOTE_TOOLS/" --user "$SSH_USER" >/dev/null 2>&1 || echo "  WARN: $bin 拷贝失败"
    fi
  done
  $PY "$ip" "chmod +x $REMOTE_TOOLS/*" --user "$SSH_USER" >/dev/null 2>&1 || true
  # 拷贝 SDC 语料 (shard_list + metadata + 所有 shard)
  if [ -f "$CORPUS_SRC/sdc_shard_list" ]; then
    for shard in $(cat "$CORPUS_SRC/sdc_shard_list"); do
      local name=$(basename "$shard")
      $PY scp "$shard" "$ip" "$REMOTE_CORPUS/$name" --user "$SSH_USER" >/dev/null 2>&1 || true
    done
    $PY scp "$CORPUS_SRC/sdc_corpus_metadata" "$ip" "$REMOTE_CORPUS/" --user "$SSH_USER" >/dev/null 2>&1 || true
    # 远端重建 shard_list (绝对路径)
    $PY "$ip" "ls -1 $REMOTE_CORPUS/runnable* $REMOTE_CORPUS/sdc_* 2>/dev/null | grep -v metadata > $REMOTE_CORPUS/shard_list; echo 'version: \"local_corpus\"' > $REMOTE_CORPUS/corpus_metadata" --user "$SSH_USER" >/dev/null 2>&1 || true
  fi
  # smoke: runner 可执行
  local rc
  rc=$($PY "$ip" "$REMOTE_TOOLS/reading_runner_main_nolibc 2>&1 | head -1; echo EXIT=\$?" --user "$SSH_USER" 2>&1 | tail -1)
  echo "  $ip runner smoke: $rc"
  local stats
  stats=$($PY "$ip" "echo T=\$(ls $REMOTE_TOOLS 2>/dev/null | wc -l) C=\$(ls $REMOTE_CORPUS/*.corpus $REMOTE_CORPUS/runnable* 2>/dev/null | wc -l)" --user "$SSH_USER" 2>/dev/null | grep -E '^T=' | tail -1)
  echo "  $ip 部署完成: $stats"
}

case "${1:-}" in
  --all)
    # 0101/0102 root, 0103 本机, 0201 sdc 用户 + 用户目录 (无 sudo)
    for ip in 172.168.177.97 172.168.160.42; do deploy_one "$ip"; done
    SSH_USER=sdc REMOTE_TOOLS=/home/sdc/sdc_tools REMOTE_CORPUS=/home/sdc/sdc_corpus deploy_one 172.168.178.81
    ;;
  "") echo "用法: $0 <board_ip>... | --all"; exit 1 ;;
  *) for ip in "$@"; do deploy_one "$ip"; done ;;
esac

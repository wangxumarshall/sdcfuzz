# 阶段B Centipede flag bug 受控 A/B 复现报告 (2026-09-04)

## 设计
单变量 A/B: 唯一差异 = flag (--corpus_from_files vs --corpus_dir);
其余固定: 干净种子集 176 个 (20 模板 + 156 阶段A字典变体, sha256 去重后 160 唯一),
全新 workdir, -j=10, --num_runs=50000, 同一 unicorn_aarch64 binary。

## 结果
| 指标 | A2 (旧 flag corpus_from_files) | B2 (修复 flag corpus_dir) |
|---|---|---|
| 墙钟 | 0.21s | 270.82s |
| end-fuzz 行数 (真实fuzzing证据) | 0 | 10 (每 shard 1) |
| corpus 导出元素 (centipede 自身 --corpus_to_files 口径) | 160 | 23316 |
| 导出与种子 sha256 相同比例 | 100.0% (160/160, 即种子去重集, 0 变异) | 0.4% (含真实变异产物) |
| 每shard corpus 增长 (corp:) | 无 (只导入) | 1920-2144 |

## 结论
1. bug 复现成立: 旧 flag 0.21s 退出, 0 次执行, 产物=种子原样分片 (160 唯一 = 176-16 重复副本)。
2. 修复实证: 新 flag 50000 runs 真实执行 270.8s, corpus 从 176 种子增长到 23316 元素 (132×)。
3. 简单_fix_tool 下游 snapshot 数从 ~104 → 37088 的量级变化由本修复直接解锁。

## 复现过程发现的新问题 (本报告副作用)
--corpus_dir 会把 fuzzing 产物写回种子目录 (flag 语义: "new corpus elements are
written to the first dir")。此前修复后的运行已把 output/bin_stage_a/ 污染成
45646 文件 (176 种子 + 45470 产物, 182M)。修复: 种子目录必须用只读副本隔离。

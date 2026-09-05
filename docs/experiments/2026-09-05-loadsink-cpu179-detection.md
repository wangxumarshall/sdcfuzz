# loadsink 用例: SiliFuzz 优化后首次检出 cpu179 SDC

日期: 2026-09-05
目标: 改造 SiliFuzz 用例生成, 使其能检测 0102 cpu179 的 load 通路 SDC 故障.

## 优化设计 (从 MRU 反汇编提取的触发规格)

cpu179 缺陷单元 = load 数据返回通路. MRU 触发循环五要素 (0x403158 窗口取证):
① 间接寻址链 (ldrsw 索引 → ldr 数据, 非连续 gather)
② load→FMA→store 同址往返
③ 长存活 FP 累加器 (d4 跨循环)
④ 条件分支 + fdiv
⑤ 满载执行 (低压)

**loadsink 生成器** (tools/sdc_experiment/loadsink_gen.py) 把五要素参数化进
SiliFuzz 快照: 索引表/数据表 store 自构造 (额外制造 store→load 往返) +
gather 链 + fmsub 同址回写 + 长存活 d4 + fdiv + XOR 聚合校验和.
变异维度: 索引模式(shuffled/reversed/strided) × 链长(8-20) × 轮次 × 索引步进 ×
数据 seed × fdiv 有无. 指令预算钳在单页 4084B.

126 个变体全部过 fuzz_filter + make (5 次确定性重放) + arm-kunpeng920 corpus.

## 检出结果 (0102 实测, 47 核满载 + taskset cpu)

| 条件 | 轮次 | 结果 |
|---|---|---|
| **cpu179 + 满载, loadsink corpus** | 11 × 150k-200k iter | **4 轮检出 code:6**: outcome:2 (MEMORY_MISMATCH) ×3, outcome:3 (REGISTER_STATE_MISMATCH) ×1 |
| 失败快照归属 | 3 个失败 id 全在 loadsink 126 序列中 | 确认非 corpus 损坏 |
| postfailure_checksum_status | 全部 = 1 (MATCH) | **corpus 完好 → 真实执行差异** |
| cpu_id | 179 | 故障核定位一致 |
| **cpu176 (健康核) + 同满载** | 3 × 150k iter | **全 code:1 (0 失败)** |
| 本机 0103 回放 | 200 iter | code:1 |
| 同窗口 MRU 对照 | 1000 iter | 15/1000 fails (窗口活跃) |

## 结论

1. **SiliFuzz 优化目标达成**: loadsink 用例在 cpu179 满载下检出 SDC
   (4/11 轮, 每轮 15-20 万次快照执行), 健康核对照 0, checksum 证明非数据损坏.
2. 优化本质 = **把用例的指令形态对准故障单元**: 纯寄存器链 (sdcbench, 60431 次
   播放 0 检出) → load 密集 + 间接寻址 + 同址往返 + 长存活寄存器 (loadsink, 检出).
3. 检出信号形态: MEMORY_MISMATCH 为主 (3/4) — 符合 load 返回通路交付坏数据的
   根因模型 (坏数据被 store 回写后在 end-state 内存比对中显形); 偶发
   REGISTER_MISMATCH (坏值经 fmsub 进入 d4 累加器).
4. 剩余差距 (如实): loadsink 检出密度 (4/11 轮) 低于 MRU (1.5-5%/千次),
   因为单快照状态压力弱于长活进程的 3000 次 factorize 循环; 可通过更长
   链/更多轮次/顺序敏感变异继续爬.

## 复现命令

```bash
# 生成+构建
python3 tools/sdc_experiment/loadsink_gen.py output/loadsink 200   # 126 过预算
for b in output/loadsink/bins/*.bin; do
  bazel-bin/tools/snap_tool --raw --runner=<runner> --out=output/loadsink_pb/$(basename $b .bin).pb make $b
done
bazel-bin/tools/snap_tool --target_platform=arm-kunpeng920 generate_corpus output/loadsink_pb/*.pb --out=output/loadsink.corpus

# 检出 (0102): 47核满载 + cpu179
SET=$(echo $(seq 144 178) $(seq 180 191) | tr ' ' ',')
for c in $(echo $SET | tr ',' ' '); do taskset -c $c ./mrueig 100000 555 & done
./runner --cpu=179 --num_iterations=200000 loadsink.corpus   # → code:6 (间歇)
```

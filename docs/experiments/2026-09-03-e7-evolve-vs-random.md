# E7: 闭环演化 vs 纯随机基线 (gem5+CHAOS bit 注入检出率对照)

日期: 2026-09-03 | 框架: tools/sdc_pipeline | 结果: TIE/INSUFFICIENT

## 设计
- 种子: D13 风格 8 指令 ALU 链 (x0-x9 消费初值, 随机 regs_init)
- 两组: EVOLVE (Filter=加权 top-3) vs RANDOM (RandomFilter 盲走)
  同 mutator 池 (bitflip/dict/insn_seq)、同预算 (4代×4变异×3 mutator)、
  唯一差异 = 下代父本选择策略
- 终代: 各组自己的演化路径终态 pool (修正了第一轮两组都按 ace 全局排序
  选中同一批候选的分析 bug)
- 验证: 终代 top-3 候选各 gem5 bit×20 注入 → diverge 率 + Fisher 精确检验

## 结果 (真实 gem5, 修复注入语义后)
| 组 | 候选 diverge | 合计 |
|---|---|---|
| EVOLVE | 1/20, 2/20, 1/20 | **4/60 (6.7%)** |
| RANDOM | 1/20, 1/20, 1/20 | **3/60 (5.0%)** |
| Fisher | | OR=1.357, p=1 → **TIE/INSUFFICIENT** |

## 本轮调试发现并修复的三个真实 bug (全部实证)
1. **g_out 覆盖语义**: payload 每迭代覆盖输出 → 故障稀释 200× → 改 acc 累积
2. **CHAOS 注入单位 (关键)**: --first-clock 是 CPU cycles (CHAOSReg.cc
   Cycles 类型), 非 gem5 tick。tick/385 换算 (2.6GHz)。修复前注入永不
   触发 (fault_injections.log 全空为证), 修复后 20/20 触发
3. **E7 分析 bug**: 两组终代都按 Vault 全局 ace 排序 → 选到同一候选
   → 假打平。修正为各组自己的路径终态 pool

## 诚实解读
- 6.7% vs 5.0% 方向为正但远未显著 (60 样本检出 OR~1.4 需数百样本)
- 可能原因: (a) D13 风格种子在该变异空间已近饱和 (ace 0.7-0.8)
  (b) 4 代浅探索 (c) 统计功效不足
- **框架目的已达成**: 闭环与基线可在同一框架内公平对照, 注入语义
  真实触发, Fisher 管线正常。E7 是后续更大规模对照 (更长序列/更多代/
  多种子/结构故障) 的可复用模板
- 对照 E2 (D13 vs B, 3.143× p=0.004): E2 的 D13 是运行时启发式选择,
  E7 是代际进化选择 — 两者机制不同, E7 的进化深度 (4 代) 远小于
  E2 的每条指令运行时选择 (200 ITERS × 每次迭代)

## 复现
python3 tools/sdc_pipeline/e7_evolve_vs_random.py
# 结果: output/experiments/sdc_pipeline_e7/e7_result.json

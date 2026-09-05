# SDCFuzz 高 SDC 检出率检测序列集 — 最终报告

日期: 2026-09-05
产物: output/sdcbench_final/ (bin/ 1000 个静态 ELF + src/ 1000 个 C 源 + final_manifest.json)

## 结果

- **1000 个检测序列, 全部 SDC 检出率 = 100%** (8/8 注入 diverge)
- 评估协议: gem5 v25.1.0.1 (CHAOS) ARM O3, CHAOSPhysReg arch_frontend 注入,
  x0-x7 架构寄存器各 1 次单 bit 翻转, 注入时刻 = 0.75×总周期 (ROI 中段),
  max_faults=1; SDC 判定 = 终态 16-hex 校验和 ≠ golden
- 独立复验: 随机抽 5 条重测, 5/5 仍为 100%

## 生成-评估-筛选流程 (实时策略调整记录)

1. 池1 (1400 条): 9 op × 18 CSP 操作数族 × 4 链长 × seed 变体 → 评估 1400, 达标 802 (57%)
2. 实测发现低分根因: orr 饱和掩蔽 (x|=c → 全1 后翻转抵消), mul 低位清零区,
   mixed 混入掩蔽 op, lsl/lsr 移位链翻转移出寄存器
3. 池2 (800 条, 定向修补): 只用高分组 op (adds/subs/add/eor/bic/eon/madd/alt 交替)
   → 评估 800, 达标 488 (61%), 其中 eon/alt/alt2 等新 op 贡献 127 条满分
4. 合并 1290 达标, 按 (sdc_rate 降序, id 升序) 取前 1000 — 恰好全部 rate=1.0

## 序列结构 (sdcbench 设计原则, 实测验证)

- 8 条独立累加器链 (x0-x7) + 步进常量 (x9/x10) + 结尾 XOR 聚合
- 关键教训 (校准实验实录):
  * xorshift 链 0% SDC — 值被反复改写, 翻转被后继混合吞掉
  * 独立链 + 单次聚合 100% SDC — 翻转无覆盖路径, 必然传播到校验和
  * 注入时刻必须落在 asm ROI 窗口内 (~0.55C-0.9C); 过早打 startup (CRASH), 过晚打尾部 (MASKED)
  * first_clock 单位是 cycle 不是 tick (CHAOSPhysReg.cc:40 Cycles(p.firstClock))

## 组成分布

- op: {'adds': 283, 'subs': 243, 'add': 213, 'eor': 213, 'mixed': 15, 'orr': 9, 'bic': 12, 'eon': 12}
- family (top8): {'cc64_full': 65, 'cc32_boundary': 63, 'cc_bit63_walk': 59, 'cc_sign_overflow': 58, 'cc_bit31_walk': 58, 'cc64_nonzero': 57, 'cc64_plus_alt': 57, 'alt01_step': 57}
- iters: {60: 243, 80: 248, 100: 256, 120: 253}
- 池: {'pool1(base)': 709, 'pool2(targeted)': 291}

## 工具 (tools/sdc_experiment/)

- sdcbench_gen.py    池1 生成器 (9 op × 18 族 × 4 iters + seed 轮次)
- sdcbench_gen2.py   池2 定向生成器 (高分组 op + madd/eon/alt 修补)
- sdcbench_eval.py   批量评估器 (golden + 8 注入, 并行 gem5)
- sdcbench_select.py 筛选器 (threshold 过滤 + 统计)

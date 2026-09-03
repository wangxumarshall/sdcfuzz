# sdc_pipeline — 可演进 SDC 用例生成闭环框架

按 `docs/scheme.md` §4.3/§5 思路构建的五阶段闭环：**Gen → Assess → Filter → Validate → Feedback**，插件化设计（启发式 ↔ RL 可替换），Vault 血缘持久化。

## 架构

```
SeedPool (20 模板 + D13 + evolved)
   │
   ▼  Mutator 池 (可插拔)
   │   OperandBitFlipMutator   — 操作数位翻 (evolution_engine 爬山泛化)
   │   OperandDictMutator      — 极端值字典替换 (operand_mutator 体系打通)
   │   InsnSequenceMutator     — 指令插入/替换
   │   PowerStressMutator      — 功耗应力 Type-I/II (scheme §5.3 雏形)
   ▼  Evaluator 池 (可插拔, Unicorn 静态)
   │   ACEProxyEvaluator       — 执行中 midflip → diverge 比例 (gem5 注入代理)
   │   IBREvaluator            — 逐指令输入位翻转率 (Harpocrates IBR 近似)
   │   TogglePowerEvaluator    — 翻转功耗代理 (McPAT 插件位, 见下)
   │   AvalancheEvaluator      — 1-bit 扰动雪崩 (反逻辑屏蔽)
   ▼  Filter (可插拔)
   │   WeightedFilter / ParetoFilter
   ▼  Validator (可选重层)
   │   Gem5Validator           — golden 自动注册 + CHAOS bit/struct 注入 → 检出率+Wilson CI
   ▼  Vault (JSONL)
       candidates.jsonl / assessments.jsonl, lineage() 血缘回溯
       ↑ Feedback: 高分候选回灌下代种子池; policy 权重自适应
```

## 快速上手

```python
from tools.sdc_pipeline.candidate import make_candidate
from tools.sdc_pipeline.vault import Vault
from tools.sdc_pipeline.pipeline import Pipeline, HillClimbPolicy
from tools.sdc_pipeline.mutators import OperandBitFlipMutator, OperandDictMutator
from tools.sdc_pipeline.evaluators import ACEProxyEvaluator, IBREvaluator, TogglePowerEvaluator
from tools.sdc_pipeline.filters import WeightedFilter

seed = make_candidate(open("seeds/e1_carry_chain.S").read(),
                      {i: 0x1234_5678_9abc_def0 for i in range(10)},
                      [], "seed:e1", structure_tags=["alu", "carry_chain"])
pipe = Pipeline(seeds=[seed],
                mutators=[OperandBitFlipMutator(3), OperandDictMutator(3)],
                evaluators=[ACEProxyEvaluator(n_probes=10), IBREvaluator()],
                filt=WeightedFilter({"ace_proxy": 0.7, "ibr": 0.3}),
                vault=Vault("output/vault"),
                policy=HillClimbPolicy(["operand_bitflip", "operand_dict"]))
report = pipe.run(generations=3, per_gen_mutations=3, top_k=4)
# 重层 (gem5+CHAOS): validator=Gem5Validator(...), validate_top_k=1
```

## 演进路线（框架不改，只换插件）

| 阶段 | 组件 | 现状 | 演进 |
|---|---|---|---|
| v1 (当前) | HillClimbPolicy | ✅ 三因子启发式 | — |
| v1.5 | McPATEvaluator | 插件位已留 | McPAT + tsv110.xml 装好即插（后台安装中） |
| v2 | RL policy | 接口已按 Gym 语义（choose_mutators/observe） | 替换 policy 对象即可 |
| v2 | AutoµSens | structure_tags 已是雏形 | 接 gem5 结构统计做 STRUCTURE_MAP 逆向靶向 |
| v2.5 | 故障模型 | bit + byte_lane_skew + 多bit（gem5 侧） | 时序故障模型 |

## 关键设计决策

- **Candidate 统一抽象**（R1）：`.S` 文本 + 编译后 bytes + regs_init + 血缘，打通原先割裂的 evolution_engine 硬编码序列与模板体系。
- **gem5 重层接入**（R3/R4）：任何候选自动包装为 `payload.S`（AAPCS64 保存 x19-x28，x0-x28 全装载/存回）+ `main.c`（SUM/CRC golden 格式），`--mode baseline` 定 golden 后即可注入。fault-clock 从候选自身 nc 的 ROI [20%,80%] 抽取。
- **MCE 红线**：gem5 并行 ≤4（`MAX_JOBS`），与 sim_sweep 一致。
- **诚实降级**：McPAT 未接入前功耗指标命名 `toggle_power_proxy`；ACE 为 Unicorn 代理（非逐周期 AVF）。

## 已知边界（实测发现，诚实记录）

1. **自包含模板对操作数变异不敏感**：`seeds/*.S` 的 LOAD 宏自带常量构造，`regs_init` 变异不改变其行为。需用消费初值寄存器的种子（如 D13 风格），或做 `// MUT:` 槽改写（后续工作）。
2. **逻辑掩蔽的寄存器覆写**：变异目标寄存器若被指令序列"写前不读"覆写，则变异无效（M2 实证：dict 变异 x5 被 `adds x5,x4,x3` 屏蔽）。后续：读集分析，只在指令序列读集内选变异目标。
3. **短序列 ACE 窗口小**：5 指令序列 bit×10 注入 diverge=0（CI 上界 0.28），需更长序列/更多样本才能测出差异。

## 测试

```bash
python3 -m pytest tools/sdc_pipeline/ -q        # 38 项单测
# 回归: tools/sdc_mutator + tools/sdc_experiment 共 77 项
```

## 实证记录

- M1（轻量闭环）：`output/experiments/sdc_pipeline_m1/` — e1 种子 ace 0.70 → 演化 0.80，血缘深 3
- M2（重层闭环）：`output/experiments/sdc_pipeline_m2/e2e_report.md` — 全链路 + x2 污染修复实证 + 逻辑掩蔽发现

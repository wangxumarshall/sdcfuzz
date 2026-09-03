# sdc_pipeline 可演进框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有工具链之上构建可演进的 SDC 用例生成闭环框架：种子 → 指令/操作数变异 → 静态评估(ACE/IBR/功耗代理) → gem5 执行 → 多指标筛选 → CHAOS 检出率验证 → Vault 血缘回灌。

**Architecture:** 五阶段流水线（Gen → Assess → Filter → Validate → Feedback）+ 插件接口（Generator/Mutator/Evaluator/Filter 可替换，启发式↔RL 可换）+ Vault JSONL 持久层（候选+指标+血缘）。轻层（Unicorn 静态评估）先闭环，重层（gem5+CHAOS）第二阶段接入；McPAT 做成 Evaluator 插件（并行安装中）。

**Tech Stack:** Python 3.11 + Unicorn 2.1.4 + capstone 5.0.7（静态评估）；gem5-fi CHAOS（注入验证，本机 ~/wangxu/gem5-fi）；McPAT（功耗插件位）；aarch64 交叉编译（.S → .bin）。

**Spec:** docs/scheme.md §4.3/§5（四层架构 + 三大关键技术）；差距分析 docs/experiments/2026-09-03-scheme-compliance-assessment.md（G1-G9）；架构审视 findings 见 .planning/2026-09-03-sdcentric-evolvable-framework/findings.md（R1-R6 重构清单）。

## Global Constraints

- **one-patch-per-unit**：每个 Task 一个 commit，verify 通过才 commit，push 到 feature 分支 `feat/sdc-pipeline-framework`（不推 main）。
- **MCE 红线**：gem5 并行 ≤4（sim_sweep.MAX_JOBS=4）；任何编译 -j8 以内。
- **诚实纪律**：McPAT 未装好之前功耗只能叫"Unicorn 翻转率代理"；验证命令的真实输出必须引用。
- **不推倒现有代码**：sdc_mutator/sdc_experiment 是算子库和实验驱动，新框架 tools/sdc_pipeline/ 只编排不复制。
- Python 测试统一 `python3 -m pytest tools/sdc_pipeline/ -x -q`（无 pytest 则 `python3 -m unittest discover`）。
- 每个生成器产出的候选必须能被 aarch64 交叉编译（`aarch64-linux-gnu-gcc` 或本机 gcc，seeds/*.S 的编译方式为准）+ Unicorn 可执行。

---

## 框架分层设计（Phase 2 定稿）

```
tools/sdc_pipeline/
├── candidate.py      # R1 解法: Candidate 统一抽象
├── vault.py          # R5 解法: JSONL Vault + 血缘 (parent chain)
├── evaluators.py     # R2 解法: Evaluator 插件接口 + Unicorn 静态实现
│                     #   (ace_proxy / ibr / toggle_power_proxy / avalanche)
├── mutators.py       # 变异插件: 指令变异 + 操作数变异 (复用 sdc_mutator 算子)
├── filters.py        # R6 关联: 多指标加权/Pareto 筛选
├── gem5_runner.py    # R3/R4 解法: golden 自动注册 + 注入 sweep (复用 sim_sweep)
├── mcpat_eval.py     # McPAT Evaluator 插件 (依赖装好后启用)
├── pipeline.py       # 闭环编排: Gen→Assess→Filter→Validate→Feedback
└── test_*.py         # 每模块单测
```

**核心数据结构：**
```python
@dataclass
class Candidate:
    ident: str              # 内容 hash (sha256 前 12 位)
    source_asm: str         # .S 全文 (可编译)
    code_bytes: bytes       # 编译后 (Unicorn 直接执行)
    regs_init: dict[int,int]  # X0-X30 初始值 (键为寄存器号)
    structure_tags: list[str] # ["alu","carry_chain","lsu",...] 结构标签 (AutoµSens 雏形)
    parents: list[str]      # 血缘: 父 Candidate ident 列表
    origin: str             # seed:<name> | mutate:<op> | evolve:<gen>

@dataclass
class Assessment:
    ident: str              # 对应 Candidate
    metrics: dict[str,float] # ace_proxy / ibr / toggle_power / avalanche / entropy...
    evaluator: str           # 产生该记录的评估器名
    validated: dict|None    # gem5+CHAOS 检出率 {bit: {rate, wilson_lo, hi}, struct: {...}} (第二阶段填)
```

**插件接口（可演进关键）：**
```python
class Evaluator(Protocol):
    name: str
    def evaluate(self, cand: Candidate) -> dict[str,float]: ...
class Mutator(Protocol):
    name: str
    def mutate(self, cand: Candidate, rng: random.Random) -> list[Candidate]: ...
class Filter(Protocol):
    def select(self, assessed: list[tuple[Candidate,Assessment]], k: int) -> list[str]: ...
```
RL 接入口：pipeline 的选择循环等价于 Gym 环境（state=评估向量, action=mutator 选择, reward=指标增量），第一版用爬山策略，后续换 RL 只替换 policy 对象，接口不变。

**数据流：** SeedPool(20模板+D13+evolved) → Mutator 池 → Evaluator 池(Unicorn:4指标, McPAT:插件位) → Filter(TopK/Pareto) → [第二阶段] gem5 golden 注册 → CHAOS bit/struct 注入 → diverge率+Wilson CI → Vault 全程记录 → 高分候选回灌 SeedPool。

---

### Task 1: Candidate 统一抽象 + .S/bytes 双形态

**Files:**
- Create: `tools/sdc_pipeline/__init__.py`
- Create: `tools/sdc_pipeline/candidate.py`
- Test: `tools/sdc_pipeline/test_candidate.py`

**Interfaces:**
- Produces: `Candidate` dataclass（字段见上）；`make_candidate(asm_text, regs_init, parents, origin, structure_tags)` → Candidate（ident=内容hash，code_bytes 由 `compile_asm()` 填充）；`compile_asm(asm_text) -> bytes`（调用交叉编译器，裸机 -nostdlib，入口对齐 seeds/build_seeds.sh 方式）。

- [x] **Step 1: 写失败测试** — 构造最小 .S（如 `adds x0,x1,x2` 裸机模板），断言 make_candidate 返回的 ident 稳定（同输入同 hash）、code_bytes 非空且 4 字节对齐、regs_init 键在 0..30。

```python
def test_candidate_identity_stable():
    c1 = make_candidate(ASM, {0:1,1:2,2:3}, [], "seed:test")
    c2 = make_candidate(ASM, {0:1,1:2,2:3}, [], "seed:test")
    assert c1.ident == c2.ident and len(c1.code_bytes) % 4 == 0

def test_compile_asm_produces_aarch64():
    code = compile_asm(MINIMAL_ASM)
    assert len(code) >= 4 and len(code) % 4 == 0
```

- [x] **Step 2: 跑测试确认失败** — `python3 -m pytest tools/sdc_pipeline/test_candidate.py -x -q` → ModuleNotFoundError
- [x] **Step 3: 实现 candidate.py** — compile_asm 参照 `scripts/build_seeds.sh` 的编译命令（先读它确定真实命令）；ident=sha256(asm+regs)[:12]
- [x] **Step 4: 跑测试通过**
- [x] **Step 5: 回归** — `python3 -m pytest tools/sdc_pipeline/ tools/sdc_mutator/test_evolution_engine.py -q` 全绿
- [x] **Step 6: Commit** — `feat(sdc_pipeline): Candidate统一抽象——.S/bytes双形态+内容hash身份`

### Task 2: Vault JSONL 持久层 + 血缘

**Files:**
- Create: `tools/sdc_pipeline/vault.py`
- Test: `tools/sdc_pipeline/test_vault.py`

**Interfaces:**
- Produces: `Vault(path)`：`put_candidate(cand)`、`put_assessment(a)`（幂等，按 ident 去重）、`get(ident)`、`children(ident)`、`lineage(ident)`（沿 parents 回溯到 seed，返回链）、`top_by(metric, k)`。

- [x] **Step 1: 失败测试** — put 两个候选（第二个 parents=[第一个 ident]），断言 lineage 返回 ['seed','child']；重复 put 同 ident 不产生第二行；top_by 排序正确。
- [x] **Step 2: 确认失败** → ImportError
- [x] **Step 3: 实现** — 两个 JSONL 文件（candidates.jsonl / assessments.jsonl），逐行 append；内存索引 dict 加速 get。
- [x] **Step 4: 通过**
- [x] **Step 5: Commit** — `feat(sdc_pipeline): Vault JSONL持久层——候选/评估幂等存储+血缘回溯`

### Task 3: Unicorn 静态评估器池（ACE代理/IBR/功耗代理/雪崩）

**Files:**
- Create: `tools/sdc_pipeline/evaluators.py`
- Test: `tools/sdc_pipeline/test_evaluators.py`

**Interfaces:**
- Consumes: Candidate（Task 1）
- Produces: `UnicornEvaluator` 基类（通用化 evolution_engine 的 X0-X4 限制到 X0-X30，指令数上限可配）；`ACEProxyEvaluator.evaluate(cand) -> {"ace_proxy": f}`（复用 ace_workload_engine 的 midflip 语义：随机注入点翻转寄存器 bit → 输出 diverge 比例，注入点数可配默认 20）；`IBREvaluator` → `{"ibr": f}`（逐指令源操作数 bit 翻转率：hook 每条指令，记录其输入寄存器读值与上一条写值的 XOR popcount / 64，全序列平均）；`TogglePowerEvaluator` → `{"toggle_power": f}`（每指令寄存器写翻转总量/指令数，di/dt 功耗代理，**明确命名 proxy**）；`AvalancheEvaluator` → `{"avalanche": f}`（复用 avalanche_test 语义）。
- 全部输出 0.0..1.0 或明确的非负比例，供 Filter 加权。

- [x] **Step 1: 失败测试** — 用固定 .S（如 adds+eor 两条指令 + 固定 regs），断言：四个评估器各返回 dict 且值域合法；全0操作数与随机操作数的 ibr 值有可测差异（全0 → 低 ibr）。
- [x] **Step 2: 确认失败**
- [x] **Step 3: 实现** — 参考 evolution_engine.py:52-96（run_once/REG_MAP 扩到 X0-X30：unicorn.arm64_const 逐个映射或 `getattr(arm64_const, f"UC_ARM64_REG_X{i}")`）；midflip 参考 ace_workload_engine.run_with_midflip；hook 用 UC_HOOK_CODE。
- [x] **Step 4: 通过**；并用真实模板 seeds/bin/e1_carry_chain 相关 .S 跑一次 smoke（打印四指标）作为实证
- [x] **Step 5: 回归** — 旧 sdc_mutator 测试仍绿（不改旧文件）
- [x] **Step 6: Commit** — `feat(sdc_pipeline): Unicorn静态评估器池——ACE代理/IBR/翻转功耗代理/雪崩四指标`

### Task 4: 变异器池（指令序列变异 + 操作数变异 + 功耗应力插入）

**Files:**
- Create: `tools/sdc_pipeline/mutators.py`
- Test: `tools/sdc_pipeline/test_mutators.py`

**Interfaces:**
- Consumes: Candidate
- Produces: `OperandBitFlipMutator`（随机翻转 regs_init 的 1-4 bit，复用 toggle_hill_climb 思路但产出 Candidate 列表）；`OperandDictMutator`（把 operand_mutator.INT_DICT/FSU_DICT 的构造值作为 regs_init 替换——不生成 .S 变体而是直接操作数级，打通两体系）；`InsnSequenceMutator`（对 .S 文本做指令级变异：从合法指令小池 add/eor/and/orr/lsl/mul/sub 随机插一条或换一条，保持汇编可编译）；`PowerStressMutator`（scheme Type-I/II 雏形：Type-I 在头部插入高翻转块（复用 encode_high_power_alu），Type-II 交替高/低翻转块，产出的候选 structure_tags 加 "power_type1"/"power_type2"）。

- [x] **Step 1: 失败测试** — 每个 mutator：mutate(种子cand, rng) 返回非空 list[Candidate]，子候选 parents 含父 ident，code_bytes 可编译，OperandDictMutator 子候选 regs_init 是字典值之一。
- [x] **Step 2: 确认失败**
- [x] **Step 3: 实现**（InsnSequenceMutator 的指令池用最小合法集，避免反汇编复杂性）
- [x] **Step 4: 通过** + smoke：对 e1 模板各 mutator 生成 3 个子代并跑 Task 3 评估器，打印指标变化（真实输出留证）
- [x] **Step 5: Commit** — `feat(sdc_pipeline): 变异器池——操作数位翻/字典/指令序列/功耗应力Type-I-II`

### Task 5: 多指标筛选器 + 轻量闭环编排器

**Files:**
- Create: `tools/sdc_pipeline/filters.py`、`tools/sdc_pipeline/pipeline.py`
- Test: `tools/sdc_pipeline/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1-4 全部
- Produces: `WeightedFilter(weights: dict[str,float]).select(assessed, k)`；`ParetoFilter.select(assessed, k)`（非支配排序，指标方向表里配置）；`Pipeline(seed_pool, mutators, evaluators, filt, vault, policy)`，`policy` 对象提供 `choose_mutators(state) -> list[str]`（第一版 `HillClimbPolicy`：上代均值提升的 mutator 权重加大——RL 接入口）；`run(generations, per_gen) -> PipelineReport`。

- [x] **Step 1: 失败测试** — 合成 Assessment 列表测 WeightedFilter/ParetoFilter 排序正确；Pipeline 用 2 个 mutator + 2 个 evaluator 跑 2 代，断言 Vault 中候选数 = seed + 2×per_gen，血缘链存在，report 含每代指标均值。
- [x] **Step 2: 确认失败**
- [x] **Step 3: 实现**（每代：policy 选 mutators → 变异 → 评估 → filter 选 top-k 进入下代种子池 → Vault 落盘）
- [x] **Step 4: 通过** + **端到端 smoke（轻量闭环首里程碑）**：真实种子（e1_carry_chain + D13 风格序列）跑 3 代 × 8 候选，打印每代四指标均值变化，输出进 docs/experiments/。诚实记录（指标可能不单调提升）。
- [x] **Step 5: 回归** — 全部旧测试绿
- [x] **Step 6: Commit** — `feat(sdc_pipeline): 筛选器+轻量闭环编排——Unicorn级Gen-Assess-Filter-Feedback全通`

### Task 6: gem5 golden 自动注册 + CHAOS 检出率验证器（重层接入）

**Files:**
- Create: `tools/sdc_pipeline/gem5_runner.py`
- Test: `tools/sdc_pipeline/test_gem5_runner.py`（单测只测参数构造与 golden 注册状态机，真实 gem5 调用 smoke 单独跑）

**Interfaces:**
- Consumes: Candidate、gem5_env（GEM5_OPT/TAISHAN_SCRIPT/local_gem5_env）、sim_sweep（wilson/classify_output 复用）
- Produces: `register_golden(cand) -> {golden, nc}`（gem5 --mode golden 跑候选 .bin，解析 simout 的 SUM=/CRC= 行与 numcycles，写入 cand 的 Vault 记录）；`validate_detection(cand, n_runs, mode, seed, jobs≤4) -> {rate, wilson_lo, wilson_hi, counts}`（复用 sim_sweep._execute_run 逻辑但 binary 用候选自己的 .bin、fault-clock 按其自己的 nc 的 ROI 抽取）。

- [x] **Step 1: 失败测试** — mock subprocess：register_golden 正确解析 simout 样例；validate_detection 参数构造正确（--binary 指向候选 bin、ROI 按候选 nc）。
- [x] **Step 2: 确认失败**
- [x] **Step 3: 实现**（关键：候选 .bin 必须是 gem5 可跑的静态裸机二进制——golden 先行，SUM/CRC 不匹配或无输出 → 该候选标记 gem5_incompatible，验证器跳过并如实记录）
- [x] **Step 4: 单测通过 + 真实 smoke**：挑 1 个已验证可跑的候选（如 D13 workload 同源序列），n_runs=10 bit 注入，打印 diverge 率 + Wilson CI（真实 gem5 输出，约 10×40s）
- [x] **Step 5: Commit** — `feat(sdc_pipeline): gem5 golden自动注册+CHAOS检出率验证器——重层接入`

### Task 7: 重层闭环打通（Validate 阶段接入 Pipeline）+ 端到端实证

**Files:**
- Modify: `tools/sdc_pipeline/pipeline.py`（加 validate 阶段钩子）
- Test: 扩展 `test_pipeline.py`

- [x] **Step 1: 实现**：Pipeline 加 `validator: gem5_runner|None` 与 `validate_top_k` 参数——每代 Filter 后的 top-K 进 gem5 检出率验证，结果写 Vault 的 assessment.validated 字段；无 validator 时行为同 Task 5（可演进：轻量/重量两档）。
- [x] **Step 2: 端到端实证（首里程碑 M2）**：真实种子 → 2 代变异 → 评估 → top-2 候选 golden 注册 + 各 10 次 bit 注入 + 5 次 struct 注入 → 汇总报告（含与种子基线的检出率对比 + Wilson CI + 诚实边界：样本小）。
- [x] **Step 3: 全测试绿** + 报告存 docs/experiments/2026-09-XX-sdc-pipeline-e2e.md
- [x] **Step 4: Commit** — `feat(sdc_pipeline): 重层闭环——top-K候选CHAOS检出率验证+端到端实证报告`

### Task 8: McPAT Evaluator 插件（依赖后台安装结果）

**Files:**
- Create: `tools/sdc_pipeline/mcpat_eval.py`
- Test: `tools/sdc_pipeline/test_mcpat_eval.py`

**Interfaces:**
- Consumes: /home/sdc/wangxu/mcpat/mcpat + configs/tsv110.xml（后台 agent 安装中；未就绪则本 Task 顺延，不阻塞 Task 1-7）
- Produces: `McPATEvaluator.evaluate(cand) -> {"power_mcpat": W, "power_peak_proxy": ...}`——把候选指令序列的翻转率/指令构成映射为 tsv110.xml 的活动因子（McPAT -xml 输入的 activity/duty cycle 参数），跑 mcpat 取总功耗与分解； Unicorn toggle 代理作交叉校验列。

- [ ] **Step 1: 检查 McPAT 安装状态**（后台 agent 的 docs/experiments/2026-09-03-mcpat-setup.md）；未就绪 → 本 Task 标记 blocked，记录到 plan，跳到 Task 9
- [ ] **Step 2: 失败测试 + 实现**（活动因子映射：候选的每类指令占比 → 对应单元 duty cycle，其余参数 tsv110.xml 固定）
- [ ] **Step 3: smoke**：e1 模板 vs 高功耗变体的 McPAT 总功耗差异（真实输出）
- [ ] **Step 4: Commit** — `feat(sdc_pipeline): McPAT功耗Evaluator插件——tsv110活动因子映射`

### Task 9: 框架文档 + scheme.md 修订收尾

**Files:**
- Create: `tools/sdc_pipeline/README.md`
- Modify: `docs/scheme.md`（4 处过时陈述，引用合规评估报告）

- [ ] **Step 1: README**：架构图（五阶段+插件接口）、用法、演进路线（AutoµSens 第二版接 gem5 结构统计 / RL policy 替换口 / McPAT 即插即用 / 多bit·时序故障扩展口）
- [ ] **Step 2: scheme.md 修订**（20模板/8模块、mutator 清单、多bit已有、3板；Sim→HW 改"已建待阳性"）
- [ ] **Step 3: 汇报**：已实现/未实现/演进路线三段
- [ ] **Step 4: Commit** — `docs(sdc_pipeline): 框架README+scheme.md过时陈述修订`

## Self-Review 结论

- **Spec 覆盖**：用户 7 条需求 → 种子(Task 1/SeedPool)、指令+操作数变异(Task 4)、ACE/IBR 静态评估(Task 3)、gem5 执行与 CHAOS 检出率(Task 6/7)、功耗计算(Task 3 代理 + Task 8 McPAT)、筛选(Task 5)、可演进框架(插件接口+Vault+policy 接口，贯穿)。AutoµSens 完整版与 RL 完整版为框架上的第二版演进（接口已留），符合"可演进"要求而非第一版全量。
- **无占位符**：每 Task 有真实测试代码骨架与接口签名。
- **类型一致**：Candidate/Assessment/Vault/Evaluator/Mutator/Filter 签名在 Tasks 间一致。

# 鲲鹏 920 SDC 高效检测用例生成 — 执行方案（融合版）

## 核心理念（对齐设计概念，纠正"丢弃变异"的偏差）

本方案**保留并强化变异**——不是无方向随机 fuzz，而是由设计概念引导的变异：

> **weak 三因素（设计冗余不足 / 老化·工艺退化 / 业务负载模型）+ 两范式（指令空间→操作数·执行上下文空间、均匀覆盖→压力权重）+ Down-Top/Top-Down 融合 + 三维压测空间** 引导的变异，面向"操作数空间变异 + 微架构定向压力模板"。

落地为：**18 个微架构定向压力模板（V1-V6 + M/C/L/O/E/F/I 系列）作为种子** → 经 Centipede 在**操作数空间**做引导式变异（每个模板用操作数字典做笛卡尔积扩展，而非随机字节翻转）→ `simple_fix_tool` 转 Snap 语料 → 真机回放检测。模板是骨架，操作数空间变异是血肉，二者缺一不可。

## 已实测验证的工程机制（2026/08/26）

四条路径全部跑通：

1. **直链种子→语料**：`seed.S → as/objcopy → seed.bin → snap_tool --raw --runner=... --out=x.pb make → snap_tool --target_platform=arm-neoverse-n1 generate_corpus *.pb --out=corpus → reading_runner_main_nolibc corpus`（返回 `code:1`=OK）。实测 `movz/movk` 构造 `0xFFFF…/0x5555…` + `add`(进位链)/`eor`/`madd`，end-state 精确 `x3=0x5555…5554`、`x4=0xAAAA…AAAA`、`x5=0xFFFF…FFFF`。
2. **分支种子有效**（纠正先前假设）：`b.eq`/`b.ne`/前向 `b` 均通过 `make`+`runner`。退出序列在 PC 走出代码边界时捕获（非线性递增），故 V3 误预测、O2 训练循环、I2 分支密集模板**可原样保留**。唯一约束：执行须在代码地址范围内终结，不跳到外部地址。
3. **Centipede 引导变异入口**：`centipede --corpus_from_files=<seeds_dir>`（每文件一输入，正是 `.bin`）→ 变异器在操作数空间探索 → 输出 `corpus.*`（Centipede blob 格式）→ `simple_fix_tool_main corpus.*` → sharded Snap 语料（实测 726 输入→104 有效 snapshot）。
4. **内存布局**：`x6=data1_base(0x7'0000'0000,4MB)`、`x7=data2_base(0x1007'0000'0000,4MB)`、`sp=0x200'1000`，数据页初值 0；NUMA 拓扑实测与文档一致（4 节点×32 核，距离 10/12/20/22/24）；`taskset`/`stress-ng` 可用，`numactl` 未装（给回退）。

banned 指令：PAC/WFE/WFI/排他 store/MRS/MSR/UDF。18 模板的核心指令（FMLA/ALU/MUL/MADD/LDP/STP/AES/SHA/CRC32/LDR/STR/fadd/fmul）**全部通过**。主机原生 aarch64，`as`/`objcopy` 即原生汇编器。MCE 红线：`--jobs=32`、orchestrator `--max_cpus`、centipede `-j=10`。

## 执行步骤（one-patch-per-unit，逐个验证+提交+推送）

所有产物落 `seeds/`、`scripts/`、`tools/sdc_mutator/`，不污染既有 C++ 树。每个 patch 独立构建+真机验证+回归测试后提交推送。

### Patch 1：统一设计文档（融合父目录方案 → docs/plan/kunpeng920_sdc_plan.md）
将 `/home/sdc/wangxu/kunpeng920_sdc_plan.md`（含操作数变异字典、18 模板、EDA-vs-功能检出率融合、覆盖率路线图）融合进 `docs/plan/kunpeng920_sdc_plan.md`，统一为单一权威方案。保留原 6 向量（V1-V6）+ 新增 7 模块模板（M1-M4 MMU、C1-C3 L2C、L1-L2 LSU、O1-O2 OoO、E1-E3 IEX、F1 FSU、I1-I2 IFU）+ 操作数字典 + 三维压测空间图。
**验证**：markdown 渲染无断裂，内部链接有效。

### Patch 2：操作数变异字典 + 模板汇编骨架
- `seeds/operand_dict.md`：整数种子表（全 0/全 1/0x5555…/0xAAAA…/单 bit 游走/进位边界/字节边界/半字游走/`0x7FFF…+1`/乘法极端）、FSU 种子（subnormal/NaN/Inf/最大有限/符号位/FP16 极端）、地址种子（对齐/跨 16B/跨 64B/跨 128B L3 line/跨 4KB 页/Set 冲突步长）。
- `seeds/asm_common.S.inc`：可复用宏——`MOVK_ALL rd, hi16, lo16`（构造任意 64-bit 常量）、`LOAD_SUBNORMAL_vd`、`LOAD_NaN_vd`、`.rept` NOP 填充对齐宏。
- `seeds/v1_fsu_vdroop.S`（FSU 功耗振荡器：NOP 窗口→双 FSU FMLA 爆发→subnormal/NaN 全谱→验证锚点）。
- `scripts/build_seeds.sh`：遍历 `seeds/*.S` → `as`+`objcopy` → `seeds/bin/*.bin`。
**验证**：V1 经 `as` 无错；`fuzz_filter_tool` 返回 0；`objdump -d` 反汇编与设计一致。回归 `bazel test //util:crc32c_test` pass、零 SIGSEGV。

### Patch 3：IEX/FSU/MMU/L2C/LSU/OoO/IFU 压力模板
按操作数字典展开 18 个模板为直链/可控分支 `.S`：
- `v2_alu_complex_saturation.S`、`v3_prf_mispredict.S`（保留 `b.eq`，已验证有效）、`v4_lsu_cross_boundary.S`、`v6_crypto_toggle.S`、`v5`（系统级 NUMA，无 asm，落脚本）。
- `e1_carry_chain.S`（`0xFFF…F+1` 全进位链 + 32/48 位进位链变异）、`e2_mul_extreme.S`（`0xFFFF×0xFFFF` 乘法器最长延迟）、`e3_toggle_rate.S`（0x5555↔0xAAAA 100% bit-toggle）。
- `f1_subnormal_nan.S`（subnormal 慢路径 + NaN 传播 + `fcmp` unordered）。
- `m1_tlb_thrash.S`（>1024 页跨步 LDR 激活 PTW）、`m3_cross_page.S`（`ldp` 跨 4KB 页边界）、`c1_l2_eviction.S`（L2 8-way Set 冲突 + Dirty Write-back）、`c3_l3_128B.S`（L3 128B line 特异性 + 跨 128B 边界 `ldp`）、`l1_disambig.S`（地址歧义 Store→Load）、`l2_dualagu_split.S`（双 AGU 同时跨 16B split）、`o1_rob_full_wakeup.S`（L3 Miss Load + 30+ 依赖链唤醒风暴）、`o2_mispredict_rollback.S`（`b.ne` 训练循环 + 最后一次误预测 + PRF 回滚验证锚点）、`i1_icache_boundary.S`（`.balign 64` + NOP 填充跨 L1I line）、`i2_branch_dense.S`（≤16B 间隔短跳转序列）。
**验证**：每个 `.bin` 经 `fuzz_filter_tool` 返回 0；`snap_tool --raw make` 成功；`--end_regs=all print` 显示的操作数/结果寄存器值与手算一致（如 `e1`: `x0=0`、`C=1`；`e2`: `umull x0=0xFFFFFFFE00000001`、`smull x3=1`）。

### Patch 4：操作数空间引导变异引擎（操作数字典 → 模板笛卡尔积扩展）
- `tools/sdc_mutator/operand_mutator.py`：读取 `operand_dict.md` 的种子表，对每个模板的"可变异操作数槽"（如 `e1` 的被加数/加数、`v1` 的 FSU 操作数）做**笛卡尔积替换**，生成 N 个变体 `.S`（如 `e1` 10×10=100 变体覆盖不同进位链长度/位位置），编译为 `.bin`。这是"操作数空间变异"的工程化落地——非随机，而是字典引导的系统性遍历。
- `scripts/run_guided_mutation.sh`：两阶段——(a) 纯模板+操作数字典笛卡尔积直接产语料（确定性、可复现、覆盖操作数空间）；(b) 以全部模板 `.bin` 为 `centipede --corpus_from_files=seeds/bin` 种子，`-j=10 --num_runs=...` 做引导式探索（Centipede 变异器在模板骨架上进一步探索操作数/指令组合），两阶段语料合并。
- `scripts/build_sdc_corpus.sh`：合并两阶段原始输入 → `simple_fix_tool_main --num_output_shards=10 --runner=...` → `output/sdc-corpus.*` + `output/sdc_shard_list` + `output/sdc_corpus_metadata`。
**验证**：`reading_runner_main_nolibc output/sdc-corpus.00000` 返回 `code:1`；统计 snapshot 数 ≥ 模板变体数；脚本幂等。

### Patch 5：分布式接近满负载 SDC 扫描集群（多单板协同）
用户已提供 4 台鲲鹏 920 单板（密码 `SDC@2026`），实测拓扑：
| 单板 | IP | 核数 | NUMA | SSH | 工具 | 角色 |
|------|-----|------|------|-----|------|------|
| 0101 | 172.168.177.97 | 126 | 待查 | ✅ | 需部署 | 扫描节点 |
| 0102 | 172.168.160.42 | 192 | 8 节点(双路×4,24c/节点) | ✅ | 需部署 | 扫描节点(最大算力) |
| 0103 | 172.168.59.158 | 128 | 4×32c | ✅(本机) | 全有 | **编译+基准+扫描节点** |
| 0201 | 172.168.178.81 | ? | ? | ❌ 超时 | — | 不可达,排除(备用) |

合计 3 台可达单板、~446 核可并行扫描。

- `scripts/ssh_lib.py`：零依赖密码 SSH/SCP 库（基于 `pty.fork()`，无 sshpass/pexpect 也能用），处理 banner/密码提示/超时。已原型验证。
- `scripts/deploy_board.sh`：从 0103 拷贝预编译静态二进制（runner+orchestrator 静态链接，已验证可跨机运行）+ 语料到各单板 `/sdc_tools/`+`/sdc_corpus/`，无需每台重新编译。
- `scripts/distributed_scan.py`：并行调度 3 单板接近满负载扫描——每单板 `--max_cpus=$(nproc)`(接近满负载) 跑 `orchestrator`，后台 `stress-ng` 制造 di/dt 带宽风暴（环境毒化放大器）。**关键容错**：满负载时 orchestrator 会偶发 `SIGSEGV while outside of snap`（实测 126 核 10s ~8 次，`--max_cpus=8` 时 0 次）——这是 fork/mmap 资源耗尽击中 snap 外路径，**非 SDC、非假阳性**，orchestrator 自身容错继续运行；脚本区分对待（SIGSEGV-outside-snap 计入噪声统计，`SNAPSHOT_FAILED`/`mismatch` 计为 SDC 命中）。
- `scripts/collect_results.py`：实时/结束时拉取各单板 `scan.log`、`result_collector` 输出、runner crash dumps → 汇总到 0103 `output/distributed/`，含每板吞吐量/SDC 命中/SIGSEGV 噪声统计。**"获取状态和结果回来"** = 脚本周期性 SSH 拉取状态 + 终态聚合。
**验证**：`--duration=60s` 三板并行冒烟，每板 orchestrator 正常起停、`collect_results.py` 拉回结构化状态（每板执行次数/SDC 命中数/噪声数）；确认无 MCE/重启。

### Patch 6：演化反馈闭环 + 文档收尾
- `scripts/sdc_evolve.sh`：汇总分布式结果，若任一单板检出 SDC（`SNAPSHOT_FAILED`/`mismatch`/`code:6`）→ 提取触发 snapshot 的指令 → 回灌 `seeds/` 高权重 → 重跑 Patch 4 局部变异放大 → 重新部署分布式扫描。形成"压测→分布式检出→回灌→再压测"闭环。
- 更新 `docs/plan/kunpeng920_sdc_plan.md` 第四部分：补实测验证记录（分支种子有效、blob 格式、`corpus_from_files` 入口、静态二进制跨单板部署、满负载 SIGSEGV 容错）。
**验证**：`bash -n` 语法检查；日志路径正确；闭环脚本空跑（无 SDC 时）正常退出。

## 关键技术决策

1. **保留变异，强化方向**：18 模板是骨架（Down-Top 微架构定向），操作数字典笛卡尔积是确定性变异（操作数空间范式），Centipede `--corpus_from_files` 是探索式变异（在骨架上探索）。三者叠加 = 设计概念的三维压测空间落地，而非随机无向。
2. **分支模板原样可用**（实测纠正）：`b.eq/b.ne/b` 不破坏 snapshot，退出序列按 PC 边界捕获。V3/O2/I2 保留分支语义。
3. **操作数在代码内自构造**：数据页初值 0，数值压力用 `movz/movk` 链构造（V1/V2/V6/E 系列）；V4/M/C/L 系列用 `x6/x7` 作基址做 store→load 往返自洽（end-state checksum 捕获翻转）。**寻址约束（实测）**：`stp/ldp` 只接受 `[Xn,#imm]`(imm 为 8 倍数) 或 `[Xn]`，**不接受** `[Xn,Xm]`；故跨边界须先 `add x8,x6,#14` 计算非对齐地址到寄存器，再 `stp x0,x1,[x8]`（已验证往返捕获）。`ldr/str` 单寄存器形式可接受 `[Xn,Xm]`。
4. **两阶段语料合并**：确定性笛卡尔积（保覆盖下限）+ Centipede 探索（提检出上限），对应"下限保覆盖、上限靠激发"。
5. **分布式接近满负载**（用户明确要求，已实测可行）：runner+orchestrator 静态链接，从 0103 拷贝到 0101/0102 即可跑（已验证 0101 端到端）。3 单板 ~446 核并行。满负载 SIGSEGV 是资源耗尽击中 snap 外路径，非 SDC，orchestrator 容错继续，脚本单独计为噪声。MCE 风险由"接近满负载"(略低于 nproc 或留 2-4 核给系统) + stress-ng 上限控制缓解。
6. **one-patch-per-unit**：6 patch 顺序执行，各自构建+真机验证+回归+提交+推送。

## 验证标准（每 patch 强制）
- 构建 clean（无新 warning/error）。
- 功能验证：真机实跑，引用真实输出（`fuzz_filter_tool` exit 0、`snap_tool make` "Re-made snapshot successfully"、`runner code:1`、`objdump` 反汇编一致、`simple_fix_tool` "Make snapshot count: N of N"、分布式 `collect_results.py` 拉回每板状态）。
- 回归：`bazel test //util:crc32c_test` exit pass，零 SIGSEGV（本机单核回归上下文）。
- 不满足则 fix→re-verify，禁止"assumed pass"。

## 不做（范围外）
- 不改 silifuzz 核心 C++（runner/orchestrator/snap_tool/simple_fix_tool 均已可用）。
- 不重新在 0101/0102 上 bazel 编译（静态二进制拷贝更高效，已验证可行）。
- 不重写 Centipede 变异器内核；用其 `--corpus_from_files` 种子入口 + 外部操作数字典做引导。
- 不接入 0201（SSH 不可达，标注备用，用户可后续告知恢复后纳入）。

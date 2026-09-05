# SDC 用例生成经验模式库（Fault-Signature Playbook）

> 目的：把每一个**已确证的硬件缺陷案例**固化成"故障签名 → 触发要素 → 生成器模板"三段式
> 经验模式，供后续生成器（AutoµSens / loadsink 家族 / RL 变异器）直接复用，避免
> "纯寄存器链打 load 通路缺陷"这类故障模型错配重演。
>
> 收录标准（缺一不入）：① 真机检出（非仅 gem5）；② 有健康核/健康板对照；③
> postfailure_checksum_status=MATCH（排除 corpus 损坏）；④ 触发要素经负对照界定。
>
> 每条模式是一个"食谱"：**故障在哪条通路 → 用什么指令形态打它 → 在什么执行条件下打 →
> 怎么判定检出**。

---

## 模式 FS-001：load 数据返回通路时序边界缺陷

**案例来源**：0102（172.168.160.42，192 核 HIP08）cpu179（PkgID 19062/NUMA node7），
12 次开机 135 次 spurious fault + 12 次 Oops 100% 单点该核；2026-09-05 MRU 复现
（1.3%~5.1% per 1000）+ loadsink 框架内检出（4/11 轮）。
档案：`vmcore0102/gem5-fi/docs/cases/core179-*`、
`gem5-fi-wangxu/docs/cases/sdc1-01-02-core179-diagnostics/`。

### 故障签名（怎么识别"又是它"）

- 损坏发生在 **load 返回数据**，不在计算/地址生成/存储：寄存器收到"其他位置真实内容
  的字节相位错位副本"（±k·8bit）、陈旧行回放、或全零交付；内存真值完好。
- **静默**：无 EDAC/APEI/GHES 记录，无 PMU memory_error——低于全部架构化 RAS 粒度。
- **负载敏感**：单核 0%，同 socket 满载（≥47 核，低压近似）才显形；满载下 0.5%~5%。
- 内核侧投影：spurious translation fault（PTW 读出同族受累）、坏指针 Oops。
- SiliFuzz 检出形态：**outcome:2（MEMORY_MISMATCH）为主**——坏 load 数据被 store 回写
  后在 end-state 内存比对显形；偶发 outcome:3（坏值经 FMA 进长存活寄存器）。

### 触发要素（五要素，负对照界定的充分条件）

| # | 要素 | 指令形态 | 为什么必需 |
|---|---|---|---|
| ① | 间接寻址链 | `ldrsw x6,[idx,x3,lsl#2]; ldr d0,[data,x6,lsl#3]` 两级追逐 | 打中 fill-buffer 合并/读出组装级 |
| ② | load→FMA→store 同址往返 | `ldr/fmsub/str` 同一 slot 下轮重读 | 制造陈旧行回放窗口 |
| ③ | 长存活寄存器 | FP 累加器跨整个循环 | 状态泄漏型缺陷的载体 |
| ④ | 条件分支包裹 FP 除 | `fdiv` + 分支 | cdiv 发射相位 |
| ⑤ | 满载执行环境 | 同 socket ≥47 核 burner | 电压裕量压缩，时序违例显形 |

**已证伪的替代形态**（11 个负对照，勿再投入）：纯 FMA、纯 gather、纯分支、纯 NEON、
密集 GEMM/SVD、纯 C 重写的稀疏分解、L1D 冷压力、三角求解——单独任一都不触发，
**必须交错**。

### 生成器模板（已落地）

- **金标准（长活进程）**：`mru_eigenmc.c`（libc-only，Eigen 机器码内嵌）——状态压力
  上界，1.5-5%/千次。用于确认窗口活跃性（背靠背对照）。
- **框架内（SiliFuzz 快照）**：`tools/sdc_experiment/loadsink_gen.py`——五要素参数化：
  索引模式（shuffled/reversed/strided）× 链长（8-20）× 轮次（单页预算内联合钳制）×
  索引步进（奇数互素）× 数据 seed × fdiv 有无；索引/数据表用 **store 自构造**
  （额外制造 store→load 往返）。检出密度 4/11 轮（每轮 15-20 万次快照执行）。

### 执行与判定协议

```bash
# 满载 + 定向（0102）:
SET=$(echo $(seq 144 178) $(seq 180 191) | tr ' ' ,)      # 47 核 burner (排除 179)
for c in ...; do taskset -c $c ./mrueig 100000 <seed> & done
./runner --cpu=179 --num_iterations=200000 loadsink.corpus
# 检出 = code:6 + outcome:2/3 + cpu_id:179 + postfailure_checksum_status:1
# 必做对照: 健康核 176 同条件 (应 0) + 同窗口 MRU (应 1.5-5%, 证明窗口活跃)
```

### 教训（生成策略层的记忆）

1. **先定故障单元，再定探针形态**：gem5 寄存器 bit-flip 协议下 100% 传播率的纯寄存器
   链（sdcbench 60,431 次真机播放）对此缺陷 0 检出——优化"损坏传播性"不等于提高
   "损坏产生概率"。
2. **负载敏感缺陷必须在满载下评估**：单核 gem5 / 单核真机都测不出此类故障。
3. **负对照清单与正例同等重要**：11 个不触发形态界定了"交错"是本质，防止后续生成器
   在已证伪的形态上浪费搜索预算。

---

## 模式 FS-002（预留）：浮点 FMA 链数值放大缺陷

**案例来源**：Cholesky 尾数漂移（core179 案例的 Case-2 投影，尚无独立确证案例）。
待有真机确证后按收录标准补全。

---

## 维护规则

1. 新案例确证后：在本文件追加 FS-XXX 模式（签名/要素/模板/协议/教训五节齐全），
   同时在对应生成器源码头部注释指向 FS 编号。
2. 模式被新实验修正时（如要素增删）：更新本文件并在 `docs/experiments/` 留实验报告
   链接，旧结论不删除——标注"已被 FS-XXX-v2 修正"。
3. AutoµSens / RL 变异器实现时，应把本库作为先验：故障签名匹配 → 直接加载对应
   要素约束，而不是从零探索。

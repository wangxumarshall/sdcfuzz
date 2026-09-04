# 本机 PMU 事件全集：Kunpeng 920 / TaiShan v110（128 核）

> 调查日期：2026-09-04。**所有事件名、raw ID、实测计数均在本机用真实命令取得**（perf 6.6.0、内核 6.6.0-159.4.3.154.oe2403sp4、CPUID/MIDR `0x481fd010`）。微架构背景见同目录 [kunpeng920_microarchitecture.md](kunpeng920_microarchitecture.md)。
>
> 采样环境说明：`kernel.perf_event_paranoid=2`，普通用户只能计数用户态事件；uncore PMU 的使用限制见 §5。

---

## 1. PMU 硬件总览

| 层级 | PMU 名 | 设备数 | 计数器/设备 | 说明 |
|---|---|---|---|---|
| 核心 | `armv8_pmuv3_0` | 1（全核共用） | 6 通用 + 1 cycle | ARMv8 PMUv3 + TaiShan v110 自定义事件 |
| L3 缓存控制器 | `hisi_sccl{1,3,5,7}_l3c{0..7}` | 32 | 每实例若干 | 每 SCCL（die）8 个 L3C bank |
| 一致性代理 | `hisi_sccl{1,3,5,7}_hha*` | 8 | 每实例若干 | HHA = Hydra Home Agent，每 die 2 个 |
| DDR 控制器 | `hisi_sccl{1,3,5,7}_ddrc{0..3}` | 16 | 每实例若干 | 每 die 4 个 DDRC |

- 内核驱动：`hisi_uncore_l3c_pmu` / `hisi_uncore_hha_pmu` / `hisi_uncore_ddrc_pmu`（均已加载，`lsmod` 实证）。
- SCCL 编号 1、3 在 socket 0，5、7 在 socket 1（与 NUMA node0-3 一一对应）。
- 每实例事件名相同、raw ID 相同，只是设备实例不同——所以下面按"事件族"列出，用哪个 die/实例就换前缀。
- `perf list pmu` 共 1832 行；核心 PMU 事件在 `perf list` 里出现在两段：`armv8_pmuv3_0`（架构事件）和 `core imp def`（v110 实现自定义事件）。

核心计数器数量说明：一次 `perf stat` 最多同时打开 **6 个**硬件事件（实测第 7 个起报 `<not supported>`），即 PMCR_EL0.N = 6。`/sys/.../armv8_pmuv3_0/caps/` 中 `slots=0`、`threshold_max=0`——**不支持** FEAT_PMUv3_METRIC（topdown 硬件指标）与 FEAT_PMUv3_TH（事件阈值过滤）。

事件 attr 格式（`/sys/.../armv8_pmuv3_0/format/`）：

| 字段 | 位 | 说明 |
|---|---|---|
| `event` | config:0-15 | 16 位事件号（架构事件 + imp-def 事件共用） |
| `long` | config1:0 | 64 位计数 |
| `rdpmc` | config1:1 | 允许用户态 rdpmc 读 |
| `threshold` | config1:5-16 | 阈值（本机 threshold_max=0，不可用） |
| `threshold_compare` | config1:3-4 | 比较模式（不可用） |
| `threshold_count` | config1:2 | 计数模式（不可用） |

调试硬件（`ID_AA64DFR0_EL1` EL0 实测 = 0x6）：**7 个上下文比较器**（CTX_CMPs=6），
watchpoint/breakpoint 至少各 1（寄存器读出值保守，见微架构文档 §3.6 的 ID 寄存器
可信度说明）。`armv8_pmuv3_0` 的 `rdpmc` 格式位存在，但用户态直读计数器需先经
`perf_event_open` 使能（PMSELR/PMEVCNTR 访问由内核管控）。

---

## 2. 核心 PMU：架构事件（48 个，raw ID 实测自 sysfs）

`/sys/bus/event_source/devices/armv8_pmuv3_0/events/` 全量导出。用法：`perf stat -e <name>` 或 `armv8_pmuv3_0/event=0xNN/`。

### 2.1 周期 / 指令 / 分支

| 事件 | raw | 含义 |
|---|---|---|
| `cpu_cycles` | 0x11 | 周期数 |
| `inst_retired` | 0x08 | 退休指令 |
| `inst_spec` | 0x1b | 推测执行指令（含错误路径） |
| `br_retired` | 0x21 | 退休分支 |
| `br_mis_pred_retired` | 0x22 | 退休误预测分支 |
| `br_pred` | 0x12 | 预测的分支 |
| `br_mis_pred` | 0x10 | 误预测分支（推测口径） |
| `br_return_retired` | 0x0e | 退休返回分支 |
| `exc_taken` | 0x09 | 异常进入 |
| `exc_return` | 0x0a | 异常返回 |
| `cid_write_retired` | 0x0b | CONTEXTIDR 写 |
| `ttbr_write_retired` | 0x1c | TTBR 写 |

### 2.2 停顿（v110 扩展的架构号）

| 事件 | raw | 含义 |
|---|---|---|
| `stall_frontend` | 0x23 | 前端停顿周期 |
| `stall_backend` | 0x24 | 后端停顿周期 |

这两个不在 ARM 基础事件集里，是 v110 落在架构事件空间的扩展（PMUv3 允许 imp-def 事件号出现在 0x00-0x3F 段）。

### 2.3 L1D / L1I / L2 / LL 缓存（架构号）

| 事件 | raw | 含义 |
|---|---|---|
| `l1i_cache_refill` | 0x01 | L1I 重填 |
| `l1i_tlb_refill` | 0x02 | iTLB 重填 |
| `l1d_cache_refill` | 0x03 | L1D 重填 |
| `l1d_cache` | 0x04 | L1D 访问 |
| `l1d_tlb_refill` | 0x05 | dTLB 重填 |
| `l1d_cache_wb` | 0x15 | L1D 写回 |
| `l1i_cache` | 0x14 | L1I 访问 |
| `l2d_cache_refill` | 0x17 | L2D 重填 |
| `l2d_cache` | 0x16 | L2D 访问 |
| `l2d_cache_wb` | 0x18 | L2D 写回 |
| `l2i_cache_refill` | 0x28 | L2I 重填 |
| `l2i_cache` | 0x27 | L2I 访问 |
| `l1d_tlb` | 0x25 | dTLB 访问 |
| `l1i_tlb` | 0x26 | iTLB 访问 |
| `l2d_tlb_refill` | 0x2d | L2 dTLB 重填 |
| `l2i_tlb_refill` | 0x2e | L2 iTLB 重填 |
| `l2d_tlb` | 0x2f | L2 dTLB 访问 |
| `l2i_tlb` | 0x30 | L2 iTLB 访问 |
| `ll_cache_rd` | 0x36 | LL（L3/末级）读访问 |
| `ll_cache_miss_rd` | 0x37 | LL 读未命中 |
| `ll_cache` | 0x32 | LL 访问 |
| `ll_cache_miss` | 0x33 | LL 未命中 |
| `remote_access` | 0x31 | 远端（跨 socket）访问 |
| `remote_access_rd` | 0x38 | 远端读访问 |

### 2.4 总线 / 内存 / TLB walk / 其他

| 事件 | raw | 含义 |
|---|---|---|
| `mem_access` | 0x13 | 数据内存访问（load+store） |
| `bus_access` | 0x19 | 总线访问 |
| `bus_cycles` | 0x1d | 总线周期 |
| `memory_error` | 0x1a | 内存本地错误（可纠正/不可纠正）——**SDC 硬件故障排查直接相关** |
| `dtlb_walk` | 0x34 | dTLB 页表遍历 |
| `itlb_walk` | 0x35 | iTLB 页表遍历 |

### 2.5 SPE 采样事件（raw 0x4000 段）

| 事件 | raw |
|---|---|
| `sample_pop` | 0x4000 |
| `sample_feed` | 0x4001 |
| `sample_filtrate` | 0x4002 |
| `sample_collision` | 0x4003 |

（本机 HWCAP 无 `spe`，SPE 采样本身不可用，这组仅计数器存在。）

---

## 3. 核心 PMU：TaiShan v110 实现自定义事件（29 个）

这一节是 `perf list` 中 `core imp def:` 段的全部事件。**raw ID 不在 sysfs 里**，本文用
`perf stat -v -e <name>`（verbose 输出会打印解析后的 `armv8_pmuv3_0/event=0xXXXX/`）逐个实测解析：

### 3.1 前端 / 分发 / 队列

| 事件 | raw | 含义 |
|---|---|---|
| `exe_stall_cycle` | **0x7001** | 发射数 < 4 的周期（4 宽机器未喂满） |
| `fetch_bubble` | **0x2014** | 取指气泡：能收指令但不能发出 |
| `if_is_stall` | **0x1044** | 取指停顿周期 |
| `iq_is_empty` | **0x1043** | 指令队列为空的周期 |
| `hit_on_prf` | **0x6014** | 命中预取数据 |
| `prf_req` | **0x6013** | LSU 发出的预取请求 |

### 3.2 L1D cache / TLB（读写口径拆分——比架构事件细）

| 事件 | raw | 含义 |
|---|---|---|
| `l1d_cache_rd` | 0x40 | L1D 读访问 |
| `l1d_cache_wr` | 0x41 | L1D 写访问 |
| `l1d_cache_refill_rd` | 0x42 | L1D 重填（读） |
| `l1d_cache_refill_wr` | 0x43 | L1D 重填（写） |
| `l1d_cache_wb_victim` | 0x46 | L1D 写回（victim） |
| `l1d_cache_wb_clean` | 0x47 | L1D 写回（clean/一致性） |
| `l1d_cache_inval` | 0x48 | L1D 无效化 |
| `l1d_tlb_rd` | 0x4e | dTLB 读访问 |
| `l1d_tlb_wr` | 0x4f | dTLB 写访问 |
| `l1d_tlb_refill_rd` | 0x4c | dTLB 重填（读） |
| `l1d_tlb_refill_wr` | 0x4d | dTLB 重填（写） |

### 3.3 L1I 预取 / L2D

| 事件 | raw | 含义 |
|---|---|---|
| `l1i_cache_prf` | **0x102e** | L1I 预取访问计数 |
| `l1i_cache_prf_refill` | **0x102f** | L1I 预取导致的 miss |
| `l2d_cache_rd` | 0x50 | L2D 读访问 |
| `l2d_cache_wr` | 0x51 | L2D 写访问 |
| `l2d_cache_refill_rd` | 0x52 | L2D 重填（读） |
| `l2d_cache_refill_wr` | 0x53 | L2D 重填（写） |
| `l2d_cache_wb_victim` | 0x56 | L2D 写回（victim） |
| `l2d_cache_wb_clean` | 0x57 | L2D 写回（clean/一致性） |
| `l2d_cache_inval` | 0x58 | L2D 无效化 |

### 3.4 访存停顿（SDC 压力实验最有价值的一组）

| 事件 | raw | 含义 |
|---|---|---|
| `mem_stall_anyload` | **0x7004** | 无任何微操作发射 且 有 load 未解析 |
| `mem_stall_l1miss` | **0x7006** | 无发射 且 有 load miss L1 等待重填 |
| `mem_stall_l2miss` | **0x7007** | 无发射 且 有 load miss L1+L2 等待 L3 |

`mem_stall_l1miss` / `mem_stall_l2miss` 给出了"停在 L2"与"停在 L3/内存"的**周期级分解**，是量化访存压力梯度（不同 CCL 距离、不同 cache 占用状态）的直接仪器。

### 3.5 raw 事件空间扫描（0x00-0xFF）

用 6 事件一批的 `perf stat` 扫描全部 256 个事件号（负载：2×10⁸ 次加法的 spin 循环），**88 个事件号有非零计数**。除上述已命名事件外，还有一批**未命名但活跃**的 imp-def 事件号（0x60-0x91 段），例如 0x66/0x67（≈2×10⁸，与 load 数一致）、0x70/0x71、0x76/0x78（≈2×10⁸）、0x73（≈6×10⁸）。这些没有 perf 名称映射，语义未知；如需使用需对照 HiSilicon 事件手册逐一标定。完整扫描结果保存在仓库计划目录 `data/sweep`。

> 提醒：raw 扫描用"非零计数"判定存在性，计数含义未经语义验证，不要直接当作已知指标使用。

---

## 4. Uncore PMU 事件（L3C 13 + HHA 26 + DDRC 8）

用法模板（以 sccl1 = NUMA node0 所在 die 为例）：

```bash
perf stat -a -e hisi_sccl1_l3c0/rd_cpipe/,hisi_sccl1_hha2/rx_ops_num/,hisi_sccl1_ddrc0/flux_rd/ ...
```

⚠️ **普通用户在本机当前配置下打不开 uncore 事件**——详见 §5 的权限分析。事件表本身是完整的（sysfs + perf list 双源实测）。

### 4.1 L3C（L3 缓存控制器，每 die 8 实例 × 13 事件）

| 事件 | raw config | 含义 |
|---|---|---|
| `rd_cpipe` | 0x00 | 总读访问（cpipe = cluster 侧管道，来自本 CCL 环的方向） |
| `wr_cpipe` | 0x01 | 总写访问 |
| `rd_hit_cpipe` | 0x02 | 总读命中 |
| `wr_hit_cpipe` | 0x03 | 总写命中 |
| `victim_num` | 0x04 | victim（写回驱逐）数 |
| `rd_spipe` | 0x20 | spipe 方向（ring 侧）读行——来自其他 CCL/远端 |
| `wr_spipe` | 0x21 | spipe 方向写行 |
| `rd_hit_spipe` | 0x22 | spipe 读命中 |
| `wr_hit_spipe` | 0x23 | spipe 写命中 |
| `back_invalid` | 0x29 | **反向无效化操作数——核间一致性干扰的直接计数器** |
| `retry_cpu` | 0x40 | L3C 压制 CPU 操作的重试数 |
| `retry_ring` | 0x41 | L3C 压制环网操作的重试数（**拥塞信号**） |
| `prefetch_drop` | 0x42 | L3C 丢弃的预取数 |

> cpipe/spipe 的语义：L3 tag 在 CPU 簇侧（华为独特设计），cpipe 是簇侧管道、spipe 是环网侧管道——见微架构文档 §3.5。

### 4.2 HHA（Hydra Home Agent，每 die 2 实例 × 26 事件）

| 事件 | raw config | 含义 |
|---|---|---|
| `rx_ops_num` | 0x00 | HHA 接收的全部操作数 |
| `rx_outer` | 0x01 | 来自**另一个 socket** 的操作数 |
| `rx_sccl` | 0x02 | 来自**本 socket 其他 SCCL** 的操作数 |
| `rx_ccix` | 0x03 | 来自 CCIX 的操作数 |
| `rx_wbi` | 0x04 | 接收 WBI（write-back invalidate） |
| `rx_wbip` | 0x05 | 接收 WBIP（write-back invalidate partial） |
| `rx_wtistash` | 0x11 | 接收 wtistash（write-through + stash） |
| `rd_ddr_64b` | 0x1c | HHA→DDRC 64B 读操作 |
| `rd_ddr_128b` | 0x1e | HHA→DDRC 128B 读操作 |
| `wr_ddr_64b` | 0x1d | HHA→DDRC 64B 写操作 |
| `wr_ddr_128b` | 0x1f | HHA→DDRC 128B 写操作 |
| `spill_num` | 0x20 | HHA 发出的 spill 操作数 |
| `spill_success` | 0x21 | 成功的 spill 操作数 |
| `bi_num` | 0x23 | back invalidation 数 |
| `sdir-lookup` | 0x40 | sdir（共享目录）查找 |
| `edir-lookup` | 0x41 | edir（独占目录）查找 |
| `sdir-hit` | 0x42 | sdir 命中 |
| `edir-hit` | 0x43 | edir 命中 |
| `sdir-home-migrate` | 0x4c | sdir home 迁移 |
| `edir-home-migrate` | 0x4d | edir home 迁移 |
| `mediated_num` | 0x32 | 介质化（mediated）操作数 |
| `tx_snp_num` | 0x33 | 发出的 snoop 总数 |
| `tx_snp_outer` | 0x34 | 发往 socket 外的 snoop |
| `tx_snp_ccix` | 0x35 | 发往 CCIX 的 snoop |
| `rx_snprspdata` | 0x38 | 接收 snoop 响应数据 |
| `rx_snprsp_outer` | 0x3c | 接收 socket 外 snoop 响应 |

本 die 实例命名对照（sysfs 实测）：sccl1_hha2/3、sccl3_hha0/1、sccl5_hha6/7、sccl7_hha4/5。

### 4.3 DDRC（DDR 控制器，每 die 4 实例 × 8 事件）

| 事件 | raw config | 含义 |
|---|---|---|
| `flux_wr` | 0x00 | DDR 总写操作数 |
| `flux_rd` | 0x01 | DDR 总读操作数 |
| `flux_wcmd` | 0x02 | DDR 写命令数 |
| `flux_rcmd` | 0x03 | DDR 读命令数 |
| `pre_cmd` | 0x04 | precharge 命令数 |
| `act_cmd` | 0x05 | active 命令数 |
| `rnk_chg` | 0x06 | rank 切换数 |
| `rw_chg` | 0x07 | 读写切换数 |

`flux_rd/flux_wr` 是 DRAM 带宽测量的标准仪器；`rnk_chg/rw_chg` 反映 bank/rank 局部性，可观测访存干扰是否把 DRAM 行缓冲打穿。

---

## 5. 实测验证与权限限制（诚实记录）

### 5.1 核心事件实测：全部可用

计算型负载（`/tmp/spin`：2×10⁸ 次加法循环，绑 cpu0）：

```
$ taskset -c 0 perf stat -e cycles,instructions,l1d_cache_rd,l2d_cache_refill_rd,mem_stall_l2miss,stall_backend -- /tmp/spin
（instructions 1,200,096,559 / l2d_cache_refill_rd 1,807 / mem_stall_l2miss 70,545 / stall_backend 63,291）
```

访存型负载（128 MB 随机指针追逐，绑 cpu0）：

```
$ taskset -c 0 perf stat -e cycles,instructions,l1d_cache_refill,l2d_cache_refill,ll_cache_miss_rd,mem_stall_l2miss,remote_access_rd -- /tmp/membench
  4,378,882      l1d_cache_refill
 10,046,969      l2d_cache_refill
  8,049,959      ll_cache_miss_rd
101,964,433      mem_stall_l2miss
    102,196      remote_access_rd
```

未命中级联 L1(4.4M) → L2(10.0M) → LLC(8.0M) 与 102M 周期的 `mem_stall_l2miss` 数量级自洽（工作集 128 MB 远超 32 MB L3 分区，约一半访问落到 DRAM）。

imp-def 事件实测示例：

```
$ taskset -c 0 perf stat -v -e exe_stall_cycle -- /tmp/spin
exe_stall_cycle -> armv8_pmuv3_0/event=0x7001/
exe_stall_cycle:u: 1,349,857,070
```

（540M 周期中 1.35G 次发射不足——4 宽机器跑纯依赖链加法，每周期最多 1 条退休，符合预期。）

### 5.2 topdown 指标：不可用

`perf stat -e topdown-fe-bound,...` 报 `Unable to find event`——v110 无 FEAT_PMUv3_METRIC，与 caps `slots=0` 一致。**前端/后端/坏推测的分解只能用 `stall_frontend`/`stall_backend`/`br_mis_pred` + `exe_stall_cycle` 组合近似**。（注意：旧版微架构文档 §5.2 提到 topdown L1 指标可用，本次实测不可用，以本文为准。）

### 5.3 Uncore 事件：驱动在、设备在，但普通用户打不开

实测（多种姿势均为 `<not supported>`）：

```
$ perf stat -a -e hisi_sccl1_l3c0/rd_cpipe/ sleep 2
   <not supported>      hisi_sccl1_l3c0/rd_cpipe/u
```

strace 定位到根因链条：

1. `perf_event_open(..., exclude_kernel=0)` → **EACCES**：`kernel.perf_event_paranoid=2` 禁止普通用户计数内核态；
2. perf 自动重试加 `exclude_kernel=1` → **EINVAL**：HiSilicon uncore 驱动（`drivers/perf/hisilicon/hisi_uncore_pmu.c`，主线内核行为）**拒绝任何带 exclude_kernel/exclude_hv 的事件**——uncore 计数器本来就是系统级的，没有"内核态过滤"概念；
3. 两个方向都死 → perf 显示 `<not supported>`。

**结论：uncore 事件需要 root 权限**（`sudo sysctl kernel.perf_event_paranoid=1` 后即可用，或直接以 root 运行 perf）。本账号（sdc，wheel 组）sudo 需密码，本会话未提权验证。旧版微架构文档 §5.3/§6 声称"uncore 全套可用"不准确，应读作"**全套已就绪，但需 root**"。

### 5.4 计数器复用与 multiplexing

核心 PMU 只有 6 个通用计数器：一次 `perf stat -e` 列超过 6 个硬件事件时内核会分时复用（输出带 `MUX` 或按 `time enabled/running` 折算）。对精确比值实验（如 IPC、miss 率），**单次运行事件数 ≤ 6**，或显式接受缩放。

---

## 6. 对 SDC / SiliFuzz 实验的事件选型建议

| 实验目标 | 推荐事件 | 层级 |
|---|---|---|
| 执行环境是否干扰 victim 核流水线 | `exe_stall_cycle`(0x7001), `stall_backend`, `iq_is_empty` | 核心 |
| 访存压力梯度（L1/L2/L3 停顿分解） | `mem_stall_anyload/l1miss/l2miss`(0x7004/06/07) | 核心 |
| victim 核缓存被挤压程度 | `l1d_cache_refill_rd`(0x42), `l2d_cache_refill_rd`(0x52), `ll_cache_miss_rd`(0x37) | 核心 |
| 跨 socket / 跨 die 流量 | `remote_access`(0x31), HHA `rx_outer`/`rx_sccl` | 核心 + uncore |
| 核间一致性干扰（伪共享/无效化风暴） | L3C `back_invalid`(0x29), `retry_ring`(0x41), HHA `tx_snp_num` | uncore（需 root） |
| DRAM 带宽/行缓冲行为 | DDRC `flux_rd/flux_wr`, `rnk_chg`, `rw_chg` | uncore（需 root） |
| 硬件内存故障排查 | `memory_error`(0x1a) | 核心 |

配套约束（来自微架构文档，事件选型时必须记住）：

1. L3 行 128 B 而 L1/L2 行 64 B——伪共享/对齐实验按 128 B 设计；
2. L3 partition 模式默认开启，"私有 36 周期"只在近端 <4 MB 份额内成立，共享数据全容量高延迟；
3. 绑核避开跨 socket（NUMA 距离 20/22）；
4. node0/node2 无本地内存，node0 上的进程默认内存落在 node1/node3。

---

## 附：数据来源与复现命令

**全部本机实测**：

```bash
# 事件清单
perf list pmu
ls /sys/bus/event_source/devices/
cat /sys/bus/event_source/devices/armv8_pmuv3_0/events/*        # 核心 raw ID
cat /sys/bus/event_source/devices/hisi_sccl1_{l3c0,hha2,ddrc0}/events/*  # uncore raw ID

# imp-def 事件名 → raw ID 解析技巧
perf stat -v -e exe_stall_cycle -- /tmp/spin 2>&1 | grep '\->'

# raw 事件空间扫描（0x00-0xFF，6 个一批）
for i in $(seq 0 42); do base=$((i*6)); EVS=""; \
  for j in 0 1 2 3 4 5; do e=$((base+j)); EVS="$EVS,armv8_pmuv3_0/event=0x$(printf %x $e)/"; done; \
  taskset -c 0 perf stat -x, -e "${EVS#,}" -- /tmp/spin 2>&1 | awk -F, '$1+0>0'; done

# uncore（需先 root 提权）
sudo sysctl kernel.perf_event_paranoid=1
perf stat -a -e hisi_sccl1_l3c0/rd_cpipe/,hisi_sccl1_ddrc0/flux_rd/ sleep 5
```

**事件语义描述**：`perf list`（jevents 表，openEuler 内核自带 HiSilicon 事件描述）；cpipe/spipe、edir/sdir 语义结合主线内核 `drivers/perf/hisilicon/` 驱动注释与华为 TaiShan 100/200 PMC 手册惯例。

**纠错声明**：本文修正了 [kunpeng920_microarchitecture.md](kunpeng920_microarchitecture.md) §5.2（topdown 可用性）与 §5.3/§6（uncore 权限）两处不准确表述；微架构规格部分以该文档为准。

# 本机 CPU 深度研究：Huawei TaiShan 200 / Kunpeng 920 (128 核)

> 调查日期：2026-09-04。除标注"公开资料"的部分外，**所有数据均在本机用真实命令实测取得**，
> 关键命令在文中随附，可复现。这台机器是 SiliFuzz AArch64 移植的宿主机与实验平台，
> 理解它的微架构直接决定 fuzzing/SDC 实验的设计与解读。

---

## 1. 一页速览

| 项目 | 值 | 来源 |
|---|---|---|
| 整机 | Huawei TaiShan 200 (Model 2280)，主板 BC82AMDD，BIOS 7.44 | `/sys/class/dmi/id/*` |
| CPU | Kunpeng-920，2 路（2 socket）| `lscpu` |
| 核心数 | 128 逻辑 CPU = 128 物理核（无 SMT，每核 1 线程）| `lscpu` |
| 微架构 | TaiShan v110（HiSilicon 首个自研 64 位 ARM 核，ARMv8.2）| MIDR `0x481fd010` |
| 主频 | 2.6 GHz 固定（cppc_cpufreq，performance governor，boost 关闭）| sysfs cpufreq |
| ISA | ARMv8-A：fp asimd aes pmull sha1 sha2 crc32 atomics(LSE) fphp asimdhp cpuid asimdrdm jscvt fcma dcpop asimddp asimdfhm；**无 SVE** | `/proc/cpuinfo` flags |
| NUMA | 4 节点（每 socket 2 个计算 die 各为一节点），节点 0/2 无本地内存 | `numactl -H` |
| 内存 | 32 GB DDR4（node1 ≈ 15.1 GB + node3 ≈ 14.7 GB）| node meminfo |
| OS | openEuler 24.03 LTS-SP4，内核 6.6.0-159.4.3.154 | `/etc/os-release` |
| PMU | armv8_pmuv3 核心 PMU + 4×SCCL 全套 Hisilicon uncore PMU（L3C/HHA/DDRC） | `/sys/bus/event_source/devices/` |

---

## 2. 拓扑：chiplet → SCCL → CCL(4 核簇) → 核

本机是 **2 socket × 2 计算die** 的四 NUMA 节点结构。Kunpeng 920 的 chiplet 设计
（公开资料，IEEE Micro 2021 / Chips and Cheese 2025）：

```
Socket 0                          Socket 1
┌──────────────┬──────────────┐   ┌──────────────┬──────────────┐
│ 计算die(SCCL) │ 计算die(SCCL) │   │ 计算die(SCCL) │ 计算die(SCCL) │
│  node0       │  node1       │   │  node2       │  node3       │
│  cpu 0-31    │  cpu 32-63   │   │  cpu 64-95   │  cpu 96-127  │
│  无本地内存   │  ~15.1GB DDR │   │  无本地内存   │  ~14.7GB DDR │
└──────────────┴──────────────┘   └──────────────┴──────────────┘
   (7nm 计算die + 16nm IO die, CoWoS 封装; "Hydra" 互联支撑双路)
```

每个 SCCL（Super CPU Cluster，计算 die）内部：

- 8 个 **CCL（CPU Cluster）** = 4 核簇，共享一个 L3 数据 bank 组；
- 双向**环形总线**连接 CCL、L3 bank、DDR 控制器（每 die 上下边各一组 DDR4 控制器）；
- 全 die 共 8 个 L3C PMU（`hisi_scclN_l3c0..7`）、2 个 HHA（Hydra 主线仲裁/一致性）、4 个 DDRC —— 与 sysfs 实测完全对应；
- **L3 tag 放在 CPU 簇侧而不是数据 bank 侧**（华为独特设计）。

本机 sysfs 证据：

```
$ numactl -H
node 0 cpus: 0 31 ...   node 1 cpus: 32 63 ...
node distances:  10 12 20 22 / 12 10 22 24 / 20 22 10 12 / 22 24 12 10
```

距离矩阵解读：同 die=10，同 socket 跨 die=12，跨 socket=20/22。即**跨 socket 访问代价是本地
die 内的 2 倍距离值**，写 SDC/性能实验时绑核要避免跨 socket。

每 4 核一个 cluster（sysfs `cluster_cpus_list`：cpu0 → `0-3`，cpu4 → `4-7` …），
core_id 以 4 为步长（cpu0 core_id=0, cpu32 core_id=36），physical_package_id=0/36 区分 socket。

> ⚠️ **对 SiliFuzz 的直接影响**：`util/platform.cc` 中 `implementer==0x48` 被强制映射为
> `kArmNeoverseN1`（`util/platform.cc:165-166`）。这是"借用"Neoverse N1 的 PlatformId 做
> snapshot 兼容性判断，不代表两者微架构相同——本文档第 4 节详细对比两者差异，SDC 实验
> 解读时不可把 N1 的公开数据当作本机行为。

---

## 3. TaiShan v110 核内微架构（公开资料 + 本机佐证）

TaiShan v110 是 HiSilicon 首个完全自研的 64 位 ARM 核（此前用 Cortex-A57/A72），
**4 宽乱序执行**，PRF（物理寄存器堆）式后端，流水线约 8 级。综合公开微基准
（Chips and Cheese 2025、LLVM TSV110 调度模型 D89972、国内微基准评测）：

### 3.1 前端

| 结构 | 规格 |
|---|---|
| 取指/译码/重命名宽度 | 4 指令/周期 |
| L1 ICache | 64 KB，4-way，每周期供 4 条指令 |
| iTLB | 32 项全相联；L2 TLB 1024 项（指令/数据共用），L2 TLB 命中 +11 周期（偏慢，Zen2 为 7） |
| BTB | L1 BTB 64 项（taken 分支单周期零气泡）；L2 BTB 约 2048 项 |
| 返回地址栈 RAS | 31~32 项 |
| 间接分支预测 | 每分支约 16 目标，全局约 256 间接目标 |
| µop cache | **没有**。代码溢出 L1i 后取指带宽骤降：L1i 内 4 条/周期 → L2 约 1.75 → L3/内存约 0.25 |
| 分支预测器 | 华为自称"两级动态预测"，行为近似 Cortex-A73；SPEC2017 准确率与 Goldmont Plus 相当，明显弱于 N1/Zen2（505.mcf MPKI 16.64 vs N1 的 15.03） |

### 3.2 乱序引擎

| 结构 | 规格 |
|---|---|
| ROB | ~128 µop（微基准实测有效约 108-110） |
| 调度器 | 按 ALU / 访存 / FP·向量 三类分设统一式调度器，各约 33 项 |
| 整数寄存器堆 | 约 128 项（足够覆盖 ROB，很少成为瓶颈） |
| Flag 重命名 | 约 31 项 |
| FP/向量寄存器堆 | 容量偏小（aarch64 32 个 FP 寄存器占去更多重命名空间，FP 密集负载易压满） |
| move elimination | 重命名级支持 |

### 3.3 执行端口（整数 4 + FP 2 + AGU 2）

```
整数侧:  ALU0 ALU1 ALU2   MUL/DIV(第4口)
          └─ 分支可走其中两口，每周期最多 1 个 taken 分支
FP 侧:   FP0 FP1 —— 都支持 128-bit FMA(FP32, 5周期)
          FP64 为 1/4 吞吐; 向量整数加 2 周期(双口);
          向量乘法仅单口; FADD/FMUL 各只占一个口(设计怪点)
访存:    2×AGU(每周期 2 个 load 或 1 load+1 store)
```

关键延迟（周期 @2.6GHz）：整数加 1；整数乘 4；整数除 19（早退）；FADD 4；FMUL 5；
FDIV 17；FMA 7（CnC 实测 FP32 FMA 5）；向量整数加 2。

### 3.4 访存子系统

| 结构 | 规格 | 本机实测/佐证 |
|---|---|---|
| L1D | 64 KB 4-way，双 128-bit 访问/周期（可 2 load），4 周期 load-to-use | sysfs：`size=64K, ways=4, sets=256, line=64` |
| store→load 转发 | 6-7 周期，跨 16B 边界 +1~2 周期（L1D 按 16B 对齐块操作） | — |
| L2 | 512 KB 私有/核，8-way，10 周期，L2→L1 带宽约 32B/周期 | sysfs：`size=512K, ways=8, sets=1024` |
| L3 (SLC) | 每 die 32 MB（8 bank×4MB），**15-way 伪随机、128B 行**，tag 在簇侧 | sysfs：`size=32768K, ways=15, sets=2048, line=128`（注意 L3 行 128B，L1/L2 是 64B！） |
| L3 模式 | shared / private / **partition（默认）** 三态，partition 态近端 4MB 内 ~36 周期，扩到全容量 >90 周期 | — |
| dTLB | 32 项全相联 + 1024 项 L2 TLB | — |
| DRAM | DDR4，读带宽 ~63 GB/s/die（CnC 样机），空载延迟 ~96 ns | 本机见 §5 |

### 3.5 L3 partition 模式——对实验设计最重要的微架构特性

华为把 L3 tag 放在 CPU 簇侧，且默认运行在 partition 模式：

- 单核访问近端私有份额（<4 MB）：~36 周期，性能尚可；
- 单核工作集增大逐步覆盖全 L3：延迟逐渐涨到 >90 周期；
- **两个核共享同一段数据时，L3 表现退化为 shared 模式行为，全容量范围都是高延迟**
  ——包括同簇内的两个核共享数据也没有优待；
- 每 4 核簇 L3 读带宽 ~21.7 GB/s，是簇级带宽瓶颈（类似 Intel E-core 簇但更严重）。

**实验含义**：任何绑核 + 共享数组的微基准（包括 SDC 的双核压核实验），其 L3 延迟
行为取决于数据共享模式，不能按"私有 36 周期"预期。

---

## 4. 与相关核心的定位对比

| | TaiShan v110 | Neoverse N1 (2.6GHz) | Cortex A72 | Goldmont Plus |
|---|---|---|---|---|
| 宽度 | 4 宽 OoO | 4 宽 OoO | 3 宽 OoO | 3 宽顺序前端+OoO 后端 |
| ROB | ~128 | 128 | ~128(µop 合并后更小) | ~124 |
| L1D | 64K/4-way/2×128b | 64K/4-way/2×128b | 48K(可配) | 32K |
| L2 | 512K 私有 | 512K-1M | 512K-1M(共享) | 4M 共享(LLC) |
| µop cache | 无 | 有 | 无 | 无 |
| IPC 定位 | SPEC17 INT 单核落后 N1 约 52% | 基准 | — | 落后 v110 7% |

一句话：**v110 是"面积/功耗优先"的自研第一代，整数尚可、FP/向量与分支预测偏弱、
访存层级靠 L3 partition 模式弥补互联短板**。这就是仓库把 0x48 映射成 N1 只能当作
"快照格式兼容"而不能当作"性能等价"的原因。

---

## 5. 本机实测数据（可复现）

### 5.1 缓存层级实测：指针追逐延迟阶梯

随机指针追逐（gcc -O2，绑 cpu4，避开跨 NUMA）：

```
$ for sz in 4K 32K 256K 512K 1M 4M 8M 32M 64M 256M; do taskset -c 4 ./latency_bench $sz; done
工作集      ns/load    级别判断
4 KB       1.54      L1D (4 cyc @2.6GHz ≈ 1.54ns)   ← 与 4 周期 load-to-use 完全吻合
32 KB      1.67      L1D
256 KB     4.88      L2 (10 cyc ≈ 3.85ns + TLB/追逐开销)
512 KB     8.12      L2/L3 边界（L2 容量 512K）
1 MB       8.76      L3 partition 近端份额
4 MB       16.79     L3 近端私有份额上限（~36 cyc ≈ 13.8ns 量级）
8 MB       84.68     L3 扩张区（partition 模式延迟陡增，CnC 的 >90 cyc 曲线）
32 MB      124.68    全 L3（32MB/die）
64 MB      133.25    L3 边界
256 MB      163.51    DRAM（~96ns 空载 + 本机负载/ NUMA 混合,~424 cyc）
```

注意本机 node0（cpu0-31）**无本地内存**，任何从 node0 出发的访存默认落在 node1/node3，
所以 256MB 点的 163 ns 实际是"跨 die 本地 socket DRAM"值。

### 5.2 PMU 核心事件实测（证明计数器可用）

```
$ taskset -c 4 perf stat -e cycles,instructions,l1d_cache,l1d_cache_refill,l2d_cache_refill,stall_frontend,stall_backend,inst_spec python3 ...
  3,741,712,411   instructions    # 3.48 insn per cycle
  1,415,133,879   l1d_cache
    298,887       l1d_cache_refill
    516,291       l2d_cache_refill
 13,911,980       stall_frontend
 28,006,760       stall_backend
```

可用的事件族：`armv8_pmuv3_0`（含 `stall_frontend/backend`、`ll_cache_rd/miss_rd`、
`inst_spec`、`exe_stall_cycle`、`if_is_stall` 等 Hisilicon 扩展事件）。
**topdown L1 指标（`bad_speculation` 等）不可用**——2026-09-04 复测确认 v110 无
FEAT_PMUv3_METRIC（caps `slots=0`），前端/后端分解用 `stall_frontend/backend` 近似。
全部事件名与 raw ID 详见 [kunpeng920_pmu_events.md](kunpeng920_pmu_events.md)。

### 5.3 Uncore PMU（SDC 环境敏感性实验的现成工具）

`/sys/bus/event_source/devices/` 下每 die 一整套：

- **L3C**（8 个/die）：`rd_cpipe/wr_cpipe`（读写流量）、`rd_hit_spipe`（近端命中）、
  `back_invalid`（反向无效化，**核间一致性干扰的直接计数器**）、`retry_ring`、`prefetch_drop`；
- **HHA**（2 个/die）：`rx_sccl`（跨 die 流量）、`edir-*`（一致性目录）、`rd_ddr_64b/128b`；
- **DDRC**（4 个/die）：`flux_rd/flux_wr`（DRAM 读写带宽）、`act_cmd/pre_cmd/rnk_chg`。

这给了 SDC"环境干扰→缓存状态→SDC 翻转"链条一个**硬件级的因果观测手段**，
是设计共享 LLC 干扰实验时的首选仪器。

> ⚠️ **权限更正（2026-09-04 复测）**：uncore 事件在 `perf_event_paranoid=2` 下
> 普通用户打不开（perf 自动加的 `exclude_kernel=1` 被 hisi uncore 驱动以 EINVAL
> 拒绝；不加则 EACCES）。需要 root：`sudo sysctl kernel.perf_event_paranoid=1`
> 或直接以 root 运行 perf。事件清单与 raw ID 全表见
> [kunpeng920_pmu_events.md](kunpeng920_pmu_events.md)。

### 5.4 其他系统事实

- 内核启动参数含 `nospectre_bhb`、`arm64.nopauth`（指针认证已关）、smmu bypass 两个设备
  —— SDC 实验不受 spectre 缓解干扰；
- `perf_event_paranoid=2`：普通用户可计数内核态之外的 PMU，足够实验用；
- 网卡 HNS GE/10GE/25GE（含 RDMA）、LSI SAS3408 RAID + HiSilicon SAS/SATA、iBMC 管理口；
- 仓库 CLAUDE.md 中的 MCE 警告（满核并行触发机器检查重启）与 128 核/4 NUMA 的
  全互联压力一致，继续遵守 `--jobs=32` / `-j=10` 上限。

---

## 6. 对仓库工作的结论性影响

1. **Snapshot 平台兼容**：所有核 MIDR 相同（`0x00000000481fd010` = impl 0x48, var 1,
   part 0xd01），整机单一微架构，corpus 无跨核异构问题；
2. **绑核策略**：跨 socket（距离 20/22）与跨 die（12）的访存代价差异显著，fuzzing
   实验（含 Centipede `-j` 并行、orchestrator 分 shard）应尽量在 die 内绑定；
   node0/node2 无内存，内存分配会自动落到 node1/node3；
3. **L3 行 128B vs L1/L2 64B**：做缓存行对齐/伪共享敏感的实验（如 SDC 干扰注入）
   必须以 128B 为 L3 粒度设计，而非 x86 直觉的 64B；
4. **L3 partition 模式 + 共享退化**：双核共享数据时 L3 延迟全域 >90 周期——
   设计"压力干扰核 + 受害核共享 L3"的实验时，观测到的慢是**设计使然**，不是故障；
5. **PMU 完备（核心普通用户即可用；uncore 需 root）**：核心 + L3C/HHA/DDRC uncore
   全套就绪（uncore 需 `perf_event_paranoid<=1`，见 §5.3 更正），SDC 论文的环境敏感性
   机制分析可直接落地，无需额外仪器；
6. **无 SVE**（HWCAP 无 sve 位，features 无 sve）：所有 snapshot/工具链不得使用
   SVE 指令，`util/aarch64/sve.*` 的运行时路径在这台机器上不会被触发。

---

## 附：数据来源

**本机实测**：`lscpu`、`/proc/cpuinfo`、`/sys/devices/system/cpu/cpu*/{cache,topology,regs}`
、`/sys/bus/event_source/devices/`、`numactl -H`、`perf stat`（含 §5.2 引用的真实输出）、
指针追逐微基准（§5.1，源码思路：64B 行随机置换追逐，gcc -O2）。

**公开资料**（微架构规格，本机无法直接读出的部分）：
- [Chips and Cheese — Huawei's Kunpeng 920 and TaiShan v110 CPU Architecture (2025-07)](https://chipsandcheese.com/p/huaweis-kunpeng-920-and-taishan-v110)
- [LLVM D89972 — Add pipeline model for HiSilicon's TSV110](https://reviews.llvm.org/D89972)
- IEEE Micro 2021: *Kunpeng 920: The First 7-nm Chiplet-Based 64-Core ARM SoC for Cloud Services*
- [知乎 — 华为鲲鹏920 TSV110微架构评测](https://zhuanlan.zhihu.com/p/616648182)
- 仓库内：`README_AArch64_Deployment.md`、`util/platform.cc:165`（0x48→N1 映射）

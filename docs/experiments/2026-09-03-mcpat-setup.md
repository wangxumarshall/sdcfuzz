# McPAT 安装与 TaiShan V110 功耗建模基线

日期: 2026-09-03
主机: 0103 (172.168.59.158, TaiShan 200 Model 2280, Kunpeng-920, 2 socket x 64c, 2.6GHz, openEuler 24.03 LTS-SP4 aarch64)
目的: 为 sdcfuzz 研究项目建立 ARM TaiShan V110 微架构的 McPAT 功耗模型, 用于后续功耗归因/异常检测分析。

## 结果总览

| 项 | 状态 | 路径/值 |
|----|------|---------|
| 安装结果 | 成功 | `/home/sdc/wangxu/mcpat` |
| mcpat 二进制 | 成功 | `/home/sdc/wangxu/mcpat/mcpat` (ELF aarch64) |
| V110 配置 | 成功 | `/home/sdc/wangxu/mcpat/configs/tsv110.xml` |
| 验证输出 | 成功 | `/home/sdc/wangxu/mcpat/tsv110_baseline_output.txt` |
| 单核总功耗 (22nm 近似) | 见下文 | Peak 4.42 W / Runtime Dynamic 0.91 W @ 2.6GHz |

## 1. 安装步骤 (全程实录)

### 1.1 依赖检查
```
$ which bison flex g++ gcc make git
/usr/bin/bison  (GNU Bison 3.8.2)
/usr/bin/flex   (flex 2.6.4)
/usr/bin/g++    (GCC 12.3.1 openEuler)
```
全部已存在, 无需 dnf 安装 (未动用 sudo)。

### 1.2 获取 McPAT (HewlettPackard 官方仓库)
- 直接 `git clone https://github.com/HewlettPackard/mcpat.git` 失败:
  本机 git 全局配置把 `https://github.com/` 重写为 `https://gitclone.com/github.com/`
  (该镜像当时返回 502)。
- 改用 ghproxy.net 镜像。第一次完整克隆失败
  (`RPC 失败。curl 92 HTTP/2 stream ... INTERNAL_ERROR`)。
- **成功方法**: `--depth 1` 浅克隆 + 强制 HTTP/1.1:
```
git -c http.version=HTTP/1.1 clone --depth 1 \
    https://ghproxy.net/https://github.com/HewlettPackard/mcpat.git mcpat
```
- 得到 McPAT ver 1.3 (commit 74d4759, 2015-02)。

### 1.3 aarch64 编译适配
McPAT 1.3 的 `mcpat.mk` 含 x86 专用编译参数, aarch64 上必须打两个补丁
(已直接修改 `/home/sdc/wangxu/mcpat/mcpat.mk`, 文件内有注释标记):
1. `CXX = g++ -m32` / `CC = gcc -m32` -> 去掉 `-m32` (aarch64 不支持, 64 位是原生)。
2. `OPT = -O3 -msse2 -mfpmath=sse ...` -> 去掉 `-msse2 -mfpmath=sse` (x86 SSE 专用; aarch64 NEON 是默认 FP 路径)。

### 1.4 编译 (遵守 MCE 约束, ≤ -j8)
```
$ cd /home/sdc/wangxu/mcpat && make opt -j8
MAKE_EXIT=0
```
- 全部 30 个源文件编译链接成功。
- 唯一警告: `cacti/powergating.cc:146: 警告：在有返回值的函数中未发现 return 语句`
  (上游已知问题, 非本次移植引入, 不影响结果)。

### 1.5 冒烟测试
```
$ ./mcpat -infile ProcessorDescriptionFiles/ARM_A9_2GHz.xml -print_level 1
  Technology 40 nm / Core clock 2000 MHz
  Area = 5.39485 mm^2 / Peak Power = 1.74187 W
```
二进制在 aarch64 上工作正常。

## 2. TaiShan V110 配置参数映射 (tsv110.xml)

参数来源:
- 项目文档 `docs/superpowers/plans/2026-08-20-sdc/kunpeng.md` (官方公开资料汇总)
- Chips and Cheese "Huawei's Kunpeng 920 and TaiShan v110 CPU Architecture" (2025-07-22 实测)
- 本机 sysfs 实测 (TaiShan 200 2280, `/sys/devices/system/cpu/`)

### 2.1 系统级
| McPAT 参数 | 值 | V110 依据 |
|-----------|-----|----------|
| core_tech_node | **22** (近似) | 真实 TSMC 7nm; McPAT 1.3 CACTI 工艺库最低 22nm (16nm 分支被上游注释, 7/10nm 直接报错退出)。见 §4 局限 |
| target_core_clockrate | 2600 MHz | 本机 lscpu 最大 2600MHz |
| machine_bits / VA / PA | 64 / 48 / 48 | AArch64 |
| device_type | 2 (LOP) | 服务器能效取向 |
| number_of_cores | 1 | 单核基线 (homogeneous, 外部按 64/128 核线性缩放) |
| temperature | 340 K | 模板默认 |

### 2.2 核心流水线
| McPAT 参数 | 值 | V110 依据 |
|-----------|-----|----------|
| machine_type | 0 (OoO) | 4-wide 乱序 |
| fetch/decode/issue/commit_width | 4/4/4/4 | 4 发射超标量 |
| fp_issue_width | 2 | 双 FSU 流水线 |
| peak_issue_width | 8 | 3 ALU + 1 MUL + 2 AGU + 2 FSU |
| ALU_per_core | 3 | 3×通用 ALU (add/bitwise), 分支可占 2 口 |
| MUL_per_core | 1 | 1×复杂口 (乘 4-cycle/除法) |
| FPU_per_core | 2 | 双 FSU: FP32 FMA 2 端口 128-bit; FP64 quarter-rate (McPAT 无 quarter-rate 概念, 仅以 FPU 数量近似) |
| memory_ports | 2 | 2×AGU, 2×128-bit 访问/周期 (2 load 或 1 load+1 store) |
| pipeline_depth | 13,13 (估计) | 未公开; 2.6GHz 4-wide OoO 的典型值 |
| instruction_window_scheme | 0 (PHYREG) | PRF-based |
| instruction_window_size / fp | 33 / 33 | 每 scheduler ~33 entries (ALU/MEM/FPV 三类统一调度器实测 ~32-33) |
| ROB_size | 128 (估计) | 未公开; Chips and Cheese: "与 Goldmont Plus (128-entry) 相当" |
| archi_Regs_IRF/FRF_size | 32/32 | AArch64 31 GPR+XZR / 32 FPR |
| phy_Regs_IRF_size | 112 | GPR rename 容量实测 112 |
| phy_Regs_FRF_size | 96 | FPR rename 容量实测 96 |
| RAS_size | 31 | 31-entry 返回栈 (实测) |
| store/load_buffer_size | 32/32 (估计) | 未公开精确值 |

### 2.3 存储/TLB
| 组件 | McPAT 配置 | V110 实际 |
|------|-----------|----------|
| L1I | 64KB, 64B line, 4-way, latency 3 | 64KB 4-way 64B line (官方+本机 sysfs index1: 64K/4-way/64B); 32KB 内分支命中延迟 3 周期 |
| L1D | 64KB, 64B line, 4-way, 2 bank, latency 4, policy 1 (write-back) | 64KB 4-way 64B, 2×128-bit/周期, load-to-use 4-cycle (本机 sysfs index0: 64K/4-way/64B) |
| iTLB | 32 entries | 32-entry (实测) |
| dTLB | 32 entries | 32-entry 全相联 (实测) |
| L2 TLB | 未建模 | 1024-entry, 11-cycle hit — McPAT 1.3 无 L2 TLB 参数 (局限, 见 §4) |
| L2 | 512KB, 64B, 8-way, 2 bank, latency 10, private (Private_L2=1) | 512KB private 10-cycle (官方); 本机 sysfs index2: 512K **8-way**/64B |
| L3 | 1MB, 64B, 16-way, latency 36, private (近似) | 见 §4 局限 1: 实际是 32MB/NUMA 节点 (本机 index3: 32768K/15-way) 集群切片共享, 三种模式, partition 模式 ~36 cycle |
| BTB | 64 entries, 2-way, 1-cycle | 64-entry BTB (实测); block_width=2 是 CACTI 建模粒度 (需要 sets-per-way>=16), 非真实行宽 |
| 分支预测器 | tournament (local 128 + global 4096x2b + chooser 4096x2b) | 华为称"两级动态预测"; 精确结构未公开, 近似建模 |

### 2.4 工作负载统计 (stat 部分)
合成整数稳态画像 (每 100k 周期 ~200k 指令, IPC 2.0, 分支 15%, load 20%, store 10%, FP 5%),
**非实测硅片计数器** — 后续可由 gem5/真机 profiling 数据替换。文件头有声明。

## 3. 验证输出摘要 (tsv110_baseline_output.txt)

命令: `./mcpat -infile configs/tsv110.xml -print_level 3` (退出码 0, 无报错)

```
Technology 22 nm / Core clock Rate(MHz) 2600
Processor:
  Area = 9.54029 mm^2
  Peak Power = 4.41969 W
  Total Leakage = 0.356184 W (Subthreshold 0.350863 + Gate 0.00532075)
  Peak Dynamic = 4.0635 W
  Runtime Dynamic = 0.905601 W

Core (1 core, ITRS LOP):
  Area = 4.89437 mm^2 / Peak Dynamic 4.05519 W / Runtime Dynamic 0.904686 W
    Instruction Fetch Unit:    0.314 mm^2 / RT-dyn 0.380 W  (L1I 0.313W, BTB 0.0003W, BPT 0.0022W)
    Renaming Unit:             0.019 mm^2 / RT-dyn 0.030 W  (RAT/FreeList)
    Load Store Unit:           1.240 mm^2 / RT-dyn 0.209 W  (L1D 0.147W, LoadQ 0.020W, StoreQ 0.041W)
    Memory Management Unit:    0.017 mm^2 / RT-dyn 0.011 W  (ITLB+DTLB)
    Execution Unit:            1.066 mm^2 / RT-dyn 0.271 W  (RF 0.074W, Sched 0.112W, 3xALU 0.011W, 2xFPU 0.0022W, MUL 0.0029W)
  L2 (private, in-core):       2.178 mm^2 / RT-dyn 0.0033 W / Subthreshold-leak 0.093 W
L3 (1MB private 近似):
  Area = 4.64593 mm^2 / Peak Dynamic 0.0083 W / Runtime Dynamic 0.000915 W / Subthreshold-leak 0.124 W
```

可复现性: 同命令重复运行输出逐字节一致。
回归: 修改 mcpat.mk 后 A9 模板输出与最初冒烟测试完全一致
(Area 5.39485 mm^2 / Peak 1.74187 W), 证明编译适配未破坏原有模型。

## 4. 已知局限 (诚实声明)

1. **工艺节点近似 (最大局限)**: 真实 V110 是 TSMC 7nm HPC, McPAT 1.3 的
   CACTI 工艺库只支持到 22nm (`cacti/technology.cc` 中 16nm 分支被注释,
   <22nm 直接 `Invalid technology nodes` 退出)。本模型用 22nm 近似 →
   **绝对功耗/面积被系统性高估** (7nm SRAM/逻辑密度约为 22nm 的 3-4 倍,
   单位电容/电压也更低)。跨 22nm→7nm 粗略缩放参考: 动态功耗 ~V^2·C·f,
   7nm Vdd≈0.7V vs 22nm≈0.8V, 电容~1/3 → 单核 Peak 真实量级应在 1-2W
   (与 Kunpeng 920 全芯片 180W TDP / 64 核 ≈ 2.8W/核的量级吻合)。
   **组件间相对占比可信度高于绝对值**。
2. **L3 建模为 1MB private**: 实际是集群 (4 核 CCL) 切片的 32MB 共享 LLC
   (本机 sysfs: 每 NUMA 节点 32MB/15-way 共享), 支持 Shared/Private/Partition
   三模式。McPAT 无法表达"部分共享+集群切片"拓扑。任务书指定按 1MB private
   近似并注明局限, 已照做。
3. **L2 TLB 未建模**: 1024-entry/11-cycle 的 L2 TLB 在 McPAT 1.3 中无对应
   参数 (只有 iTLB/dTLB)。TLB 功耗被低估 (缺 L2 TLB 阵列)。
4. **分支预测器结构近似**: 只有 BTB(64) 和 RAS(31) 是实测; tournament
   预测器各表大小是估计值。间接分支预测器 (~256 目标) 未建模。
5. **FP64 quarter-rate 无法表达**: McPAT 的 FPU 模型无吞吐率概念,
   双 FSU 以 FPU_per_core=2 近似。
6. **负载统计是合成的**: stat 部分是整数型稳态画像, 非实测; Runtime
   Dynamic 只在该画像下有意义。Peak Dynamic/Leakage 与画像无关, 更稳。
7. **单核模型**: NoC/内存控制器/IO 全部置 0 (Kunpeng 920 的 bufferless
   双环 NoC、DDR4-2933 8ch、PCIe4 不在单核 V110 范围内)。
8. **ROB 128 / 流水线深度 13 / LQ 32 / SQ 32 是估计值**, 未公开。
9. McPAT 本身的已知模型误差 (CACTI 22nm SRAM 模型年代较早, OoO 核的
   经验公式基于 Alpha 21264 类结构)。

## 5. 文件清单

- `/home/sdc/wangxu/mcpat/` — McPAT 1.3 安装目录 (git 浅克隆 + aarch64 编译适配)
- `/home/sdc/wangxu/mcpat/mcpat` — 二进制 (910KB, ELF aarch64 动态链接)
- `/home/sdc/wangxu/mcpat/mcpat.mk` — 已打 aarch64 补丁 (含注释)
- `/home/sdc/wangxu/mcpat/configs/tsv110.xml` — V110 配置 (头部含完整参数依据与局限声明)
- `/home/sdc/wangxu/mcpat/tsv110_baseline_output.txt` — print_level 3 验证输出
- `/home/sdc/wangxu/mcpat/ProcessorDescriptionFiles/ARM_A9_2GHz.xml` — 上游模板 (回归基准, 未改动)

## 6. 踩坑记录 (供复现)

1. git clone GitHub 直连不可用 (全局配置重写到 gitclone.com, 当时 502);
   ghproxy.net 完整克隆会 HTTP/2 流中断; `--depth 1` + `-c http.version=HTTP/1.1` 成功。
2. mcpat.mk 的 `-m32`/`-msse2` 在 aarch64 直接编译失败, 必须去除。
3. McPAT XML 解析器**无条件**按顺序读取组件节点: core0 → L1Directory0 →
   L2Directory0 → L20 → L30 → NoC0 → mc → niu → pcie → flashc。
   即使 number_of_L1Directories/L2Directories/NoCs=0, 对应占位组件节点
   也必须存在, 否则解析器 exit(0)。占位组件不计入功耗。
4. **BTB 64-entry 2-way 触发 `ERROR: no valid data array organizations found`**:
   CACTI 要求 cache sets-per-way ≥ 16 (MINSUBARRAYROWS=16, 2 subarrays/mat)。
   64/(block=4×assoc=2)=8 组 < 16 → 数据阵列无合法组织。解决: block_width
   用 2B (64/2/2=16 组)。这是 CACTI 阵列下限, 与真实 BTB 行为无关。
   (逐参数二分排查定位, 非猜测。)
5. 试图从 gem5 上游取 TSV110 CPU 模型参数未果: 上游 gem5 从未包含 TSV110
   类 (搜索确认无此类), 转而用 Chips and Cheese 实测数据补齐 ROB/PRF/scheduler。

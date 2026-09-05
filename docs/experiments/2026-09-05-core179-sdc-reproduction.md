# CPU179 SDC 复现报告（0102 / 192 核鲲鹏920）

日期：2026-09-05
执行：sdcbench 会话（goal: 复现 0201/192核设备上 179 核的 SDC 问题）

## 事实澄清

- **故障机是 0102（172.168.160.42，192 核 HIP08 4×48），不是 0201（96 核）**。用户口述的"0201 这台 192 核设备"与实测板卡拓扑不符——0102 才有 cpu179（PkgID 19062 / NUMA node 7），0201 核数 96，无 179 号核。
- "179 核 SDC 问题"出自既有法证档案：`vmcore0102/gem5-fi/docs/cases/core179-*`（12 次开机的 135 次 spurious fault + 12 次 Oops 100% 单点 CPU179）+ `gem5-fi-wangxu/docs/cases/sdc1-01-02-core179-diagnostics/`（MRU 最小复现用例）。
- 本次开机 0102 dmesg 实测 **35→36 条 spurious translation fault 全部 CPU179**——故障当前活跃。

## 复现协议（沿用已验证配方，MRU 路线）

1. 构建 libc-only MRU（`mru_eigenmc.c` + `eigen_cabidrv.cpp`，Eigen 5.0.1 机器码内嵌）——纯 Cholesky numeric factorize（cdiv + rank-1 update + 间接寻址 + 长存活累加器交错序列）。
2. 同 socket 47 核满载（cpu 144-191 排除 179，每核跑 mrueig burner）。
3. `taskset -c 179 ./mrueig N 12345`。

## 复现结果（全部实测）

| 条件 | 结果 |
|---|---|
| **cpu179 + 47 核满载，3000 iter** | **SDC 复现**：x-crc mismatch 多次，末段核心转储（坏数据被解引用） |
| cpu179 + 满载，定量 3×1000 iter | **26/1000、13/1000、15/1000 fails（1.3%~2.6%）**，x[0] 数值漂移（0.0795443 vs golden 0.0795441）+ CRC 多位不符 |
| **cpu176（健康核）+ 同满载，1500 iter** | **0 fails**（对照） |
| **cpu179 单核无满载，2000 iter** | **0 fails**（负载依赖确认） |
| 本机（0103，健康机）冒烟 500 iter | 0 fails（探针自校验） |

失败模式与档案记录逐条吻合：损坏固定 x[0]、多位混叠（CRC 全变）、静默（无 EDAC/PMU 异常）、偶发 SEGV、单核 0% / 满载 1-3%。

## 与 sdcbench 序列的关系（诚实交代）

此前 60,431 次播放 0 issues 的 sdcbench 序列（纯寄存器链）**打不中此故障**——根因在 load 数据返回通路（fill-buffer/L1D 读出组装级），触发需要"间接寻址 + 长存活寄存器 + 特定交错"的乱序引擎状态泄漏序列。"用例太理想化"的批评被本次复现直接证实：gem5 寄存器翻转协议下 100% 检出率的序列，对真实 load 通路缺陷的检出率为零。**MRU（Eigen 指令序列）才是命中该缺陷的探针。**

## 结论

**CPU179 的 SDC 问题在 0102 上复现成功**：满载 1.3%~2.6% 失败率、固定 x[0] 多位混叠、健康核对照 0、单核 0。处置建议维持档案结论：永久 isolcpus=179 + 该 socket RMA。

## 复现命令索引

```bash
# 构建 (0103, Eigen 5.0.1 头 + gcc/g++)
cd gem5-fi-wangxu/docs/cases/sdc1-01-02-core179-diagnostics
EIG=/path/to/eigen bash build_mru_eigenmc.sh

# 复现 (0102)
SET=$(echo $(seq 144 178) $(seq 180 191) | tr ' ' ',')
for c in $(echo $SET | tr ',' ' '); do taskset -c $c ./mrueig 100000 888 & done   # 47核满载
taskset -c 179 ./mrueig 3000 12345    # → 26/1000 量级 fails
taskset -c 176 ./mrueig 1500 12345    # → 0 fails (对照)
```

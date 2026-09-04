# McPAT 升级为 submodule（wangxumarshall/mcpat）+ 端到端验证 + third_party 整理

日期: 2026-09-04
主机: 0103 (Kunpeng-920 aarch64, openEuler 24.03 LTS-SP4)
前置: [2026-09-03-mcpat-setup.md](2026-09-03-mcpat-setup.md)（HPE 官方 v1.3 + 手工 aarch64 补丁安装，装在 `~/wangxu/mcpat`，后目录丢失，`mcpat_eval.py` 断链）

## 结果总览

| 项 | 状态 | 说明 |
|----|------|------|
| submodule 替换 | 成功 | `third_party/mcpat` → `git@github.com:wangxumarshall/mcpat.git` master `3cf423f` |
| 构建回归 | 成功 | submodule 内 `make opt -j8`，ELF aarch64 |
| 上游 pytest | 成功 | `tests/` 3 passed（依赖 h5py 3.16.0，aliyun 镜像安装） |
| Kunpeng920 端到端 | 成功 | pypat convert.run → power_total 30.79 W, profile=arm64-kunpeng920 |
| 项目侧插件适配 | 成功 | `test_mcpat_eval.py` 5 passed（含真实 mcpat 调用） |
| third_party 整理 | 成功 | 12 个散文件 → `third_party/bazel_build_files/`，Bazel 构建通过 |

## 1. 为什么升级

1. 旧安装 `~/wangxu/mcpat` 目录已不存在 → `mcpat_eval.py` 硬编码路径断链（`test_mcpat_installed` 必挂）。
2. `third_party/mcpat` 是 HPE v1.3 浅克隆 + 本地未提交 aarch64 补丁，整个目录未被外仓跟踪——其他机器 clone 后拿不到。
3. 目标 fork（wangxumarshall/mcpat）含：ARM64 Kunpeng920 profile 支持、pypat（gem5→mcpat XML 转换）、tests/ 回归、**上游已修好 aarch64 编译**（mcpat.mk 用 uname 分派，x86 才加 -msse2/-mfpmath=sse，无 -m32），旧手工补丁无需迁移。

## 2. 关键适配点（后人必读）

### 2.1 新二进制输出口径变了

上游 commit `758d196` 起 `proc.displayEnergy(2, plevel)` 被注释，改为：

| 输出 | 旧 (HPE v1.3) | 新 (fork) |
|------|---------------|-----------|
| stdout | "Processor: Area = X mm^2 / Peak Power = X W / Runtime Dynamic = X W" 文本 | `dump_area(cout)` 一行 per-block **面积**数字 |
| 功耗 | stdout 文本 | **`out.ptrace`** 文件（块名 TAB 行 + per-block 功耗数字行），写到 mcpat 进程 **cwd** |
| 面积 | stdout 文本 | `out.area` 文件 |
| `-print_level` | 控制输出细度 | 仍被解析但 displayEnergy 已不调用，**不再影响输出** |

后果：任何用正则抓 `Runtime Dynamic = X W` 的代码在新二进制下会抓空（返回 None/0）。`run_mcpat()` 已改为 `subprocess cwd=tmpdir` + infile 绝对路径，解析 out.ptrace：`sum(逐块) = 总功耗`，`max(逐块) = 峰值块`。

### 2.2 新口径下 duty cycle 不再驱动可见功耗

- runtime 功耗（out.ptrace）由 XML 的**统计**驱动：`ialu/fpu/mul_accesses`、`load/store_instructions`、`inst_window_*`、`ROB_reads/writes`、`total_instructions`、各 cache 块内 `read/write_accesses`、dtlb `total_accesses`。
- duty cycle 只进 TDP/peak 计算，而文本版 peak 输出已被上游注释掉 → **改 duty 对输出无感**。
- `build_xml()` 现在双通道：duty 保留（原逻辑）+ 全套统计画像（按"该指令构成跑满 100k 周期"写全，与基线 `total_cycles=100000` 同量纲）。

### 2.3 主指标从 peak 改为 total

新口径 `max(逐块)` 恒为 ICache（对指令构成不敏感），`sum(逐块)` 随构成单调变化。实测区分度（cyc=100k 画像）：

| 指令构成 | total (W) |
|----------|-----------|
| tsv110 基线 | 1.135 |
| ALU 100% | 1.572 |
| MUL 100% | 1.782 |
| FPU 100% | 1.858 |
| LSU 100% | 2.913 |

**新旧数字不可直接对比**：旧口径文本版 Peak 4.42 W（TDP/duty 驱动）vs 新口径 sum-of-blocks 1.13 W（runtime 统计驱动），量纲不同。旧基线存档在 `tools/sdc_pipeline/mcpat_configs/tsv110_baseline_output.txt`。

### 2.4 tsv110.xml 迁移与 XML 合规修复

- 新位置：`tools/sdc_pipeline/mcpat_configs/tsv110.xml`（不放 submodule 内，保持 submodule 与上游同步干净）。
- 原文件 line 275 注释体内有裸 `--`（XML 规范禁止），mcpat 自带 xmlParser 宽容没报错，但 python3 ElementTree 报 invalid token；已修为 `- (dash)`，现在是合法 XML。

## 3. 验证实录（全部真实输出）

```
$ git submodule status
 3cf423f10090ac1935e4193c2dbea1a4abc8e878 third_party/mcpat (heads/master)

$ cd third_party/mcpat && make opt -j8
... g++ ... -o obj_opt/mcpat -Wno-unknown-pragmas -O0 -DNTHREADS=4 -pthread -lm
$ file mcpat
mcpat: ELF 64-bit LSB executable, ARM aarch64

$ ./mcpat -infile ProcessorDescriptionFiles/Xeon.xml -print_level 2; echo $?
0

$ python3 -m pytest tests/ -q
3 passed in 27.95s

# pypat 端到端 (gem5 config+stats → XML → mcpat → 功耗摘要)
$ python3 -c "...run('tests/data/arm64_kunpeng920_minimal'...)"
power_total: 30.790324602
power_peak_dynamic: 16.8733
template_profile: arm64-kunpeng920

$ python3 -m pytest tools/sdc_pipeline/test_mcpat_eval.py -q
5 passed in 27.94s

# third_party 整理后 Bazel 回归
$ bazel build -c opt --jobs=32 //tools:snap_tool
Build completed successfully, 869 total actions
$ bazel test -c opt --jobs=32 //util:crc32c_test
Executed 1 out of 1 test: 1 test passes.
```

## 4. third_party 整理后布局

```
third_party/
├── bazel_build_files/        # 11 个 BUILD.* + absl_endian_visibility.patch
│                              # (MODULE.bazel 8 处 build_file 引用已同步)
├── mcpat/                     # git submodule → wangxumarshall/mcpat master
└── silifuzz_libunwind/        # ucontext 保存/恢复汇编 (原有, 未动)
```

## 5. 其他机器 clone 后的恢复步骤

```bash
git clone --recurse-submodules <repo-url>
cd third_party/mcpat && make opt -j8   # 构建二进制 (构建产物不入库)
# Python 侧依赖 (跑 tests/ 或 pypat 时):
pip3 install -i https://mirrors.aliyun.com/pypi/simple/ h5py
```

## 6. 提交记录

- `239432b` feat(third_party): mcpat升级为git submodule
- `79ed0b9` fix(sdc_pipeline): mcpat_eval适配submodule新输出口径(out.ptrace)
- `0827aec` chore(third_party): BUILD文件与patch归入bazel_build_files子目录

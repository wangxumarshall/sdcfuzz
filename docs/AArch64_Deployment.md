# Silifuzz AArch64 SDC 自动化测试部署与复现指南

这份文档总结了如何在基于 AArch64 (ARM64) 架构的物理机（如搭载华为鲲鹏 Kunpeng CPU 的 openEuler 机器）上，端到端解决依赖问题、编译构建、以及配合 Centipede 自动产生 SDC (Silent Data Corruption) 漏洞挖掘用例的完整闭环过程。

本指南经过专门设计，**AI 可根据本文档所述步骤实现一键式自动复现**。

---

## 1. 依赖解决与基础环境预处理 (Dependency Resolutions)

在开始编译前，由于底层 OS 与国内网络环境的特殊性，必须前置处理以下问题：

### 1.1 修复 Clang/LLVM 内置库路径 (openEuler 专属)
默认的 Bazel 工具链在寻找 `compiler-rt` 静态库时会硬编码 `linux` 路径，而在 openEuler 下该库名带有 OS 标识。需建立系统软链接：
```bash
sudo mkdir -p /usr/lib64/clang/17/lib/linux
sudo ln -s /usr/lib/clang/17/lib/aarch64-openEuler-linux-gnu/libclang_rt.builtins.a /usr/lib64/clang/17/lib/linux/libclang_rt.builtins-aarch64.a
```

### 1.2 解决模块依赖断流与超时 (网络加速)
为了防止 `bazelisk` 构建时出现 `git fetch` 卡死，需要修改项目根目录的 `MODULE.bazel` 文件：
1. 找到 `fuzztest` 依赖，将 `remote` 改为加速代理，如：`https://ghproxy.net/https://github.com/google/fuzztest`。
2. 找到 `unicorn` 依赖，将其 `remote` 更换为 Gitee 的镜像仓库，以避免巨大的 C++ 仓库拉取时因网络断流导致进程僵死：`https://gitee.com/mirrors/Unicorn.git`。

---

## 2. 代码适配与补丁打入 (Codebase Patches for AArch64)

### 2.1 修复 CRC32 硬件加速编译报错
AArch64 的 `__builtin_arm_crc32cb` 需要编译器开启 CRC 支持。
修改 `util/BUILD` 中的 `crc32c` 模块，补充 `copts` 选择器：
```python
cc_library_plus_nolibc(
    name = "crc32c",
    ...
    copts = select({
        "@silifuzz//build_defs/platform:aarch64": ["-march=armv8-a+crc"],
        "//conditions:default": [],
    }),
)
```

### 2.2 修复华为鲲鹏 CPU (Implementer 0x48) 的架构识别
Silifuzz 默认不识别华为自研 CPU。必须修改 `util/platform.cc` 中的 `ArmPlatformIdFromMainId` 函数：
```cpp
// 找到 case 0x41: ... 后，增加华为 CPU 的 Implementer ID 处理：
case 0x48: // Huawei
  // 强制将其映射为 NeoverseN1 (ARMv8.2-A)
  return PlatformId::kArmNeoverseN1; 
```

---

## 3. 工具链编译与全局部署 (Build & Deployment)

环境适配完毕后，编译执行所需的核心组件：

```bash
# 编译所有必须的 runner 工具与调度器
bazelisk build -c opt //tools/... //runner/... //orchestrator/...

# 部署二进制文件到系统级 PATH，以便后续编排使用
sudo cp bazel-bin/tools/snap_tool /usr/local/bin/
sudo cp bazel-bin/runner/reading_runner_main_nolibc /usr/local/bin/
sudo cp bazel-bin/orchestrator/silifuzz_orchestrator_main /usr/local/bin/
sudo cp bazel-bin/tools/simple_fix_tool_main /usr/local/bin/
```

---

## 4. 自动化模糊测试与用例生成 (Automated Corpus Generation)

此阶段需要配合 Centipede 模糊测试引擎与 Unicorn 硬件模拟代理。
> **⚠️ 核心警告 (Prevent Hardware Crashes)**: 在拥有超多核 (如 128 核) 的服务器上，不要使用默认的 Bazel 满核并行编译或高并发跑 Fuzzing，否则极易触发内核 Machine Check Exceptions (MCE) 硬件过载从而导致物理重启。请严格遵守 `--jobs=32` 和 `-j=10` 的阈值。

你可以将以下脚本作为一个 Shell 脚本运行（或 AI 一键执行），统一输出在 `~/wangxu/silifuzz/output` 目录下：

```bash
#!/bin/bash
set -e
mkdir -p output

# 1. 获取 Centipede 覆盖率插桩 flags
COV_FLAGS_FILE="$(bazelisk info output_base)/external/fuzztest+/centipede/clang-flags.txt"
FLAGS=$(xargs < "${COV_FLAGS_FILE}" | sed -e 's/,/\\,/g' -e 's/ /,/g')

# 2. 以受限的 CPU 负载编译 Unicorn AArch64 代理，植入 fuzz 插桩
bazelisk build --jobs=32 -c opt --copt=-UNDEBUG --dynamic_mode=off \
  --per_file_copt="unicorn/.*@${FLAGS}" @silifuzz//proxies:unicorn_aarch64

# 3. 编译 Centipede 引擎本体
bazelisk build --jobs=32 -c opt @fuzztest//centipede:centipede

# 4. 运行 Centipede Fuzzing，生成包含异常输入的语料 (限制并行 worker 为 10)
bazel-bin/external/fuzztest+/centipede/centipede \
  --binary=bazel-bin/proxies/unicorn_aarch64 \
  --workdir=/tmp/centipede_wd \
  -j=10 --num_runs=10000

# 5. 抓取 Centipede 的原始 Fuzz 变异输出，通过实体机生成带有 Terminal States (终点状态) 的 Snapshot 分片
bazel-bin/tools/simple_fix_tool_main \
  --num_output_shards=10 \
  --output_path_prefix=$(pwd)/output/runnable-corpus \
  --runner=/usr/local/bin/reading_runner_main_nolibc \
  /tmp/centipede_wd/corpus.*

# 6. 生成 Orchestrator 编排器所需的元数据和分片清单
ls -1 $(pwd)/output/runnable-corpus.* > $(pwd)/output/shard_list
echo 'version: "local_corpus"' > $(pwd)/output/corpus_metadata

echo "✅ 自动化 SDC 用例生成闭环完成。"
```

---

## 5. 端到端验证与 7x24 巡检 (Validation)

当步骤 4 成功产出 `runnable-corpus.*` 切片文件后，即可直接在真机上验证 SDC 缺陷探测能力。

执行以下命令，Orchestrator 将接管所有 CPU 核心，长期循环向处理器投入生成的边界机器码。只要处理器的执行结果与预期不符，即立刻抛出 SDC 告警。
```bash
silifuzz_orchestrator_main --duration=24h \
     --runner=/usr/local/bin/reading_runner_main_nolibc \
     --shard_list_file=./output/shard_list \
     --corpus_metadata_file=./output/corpus_metadata
```

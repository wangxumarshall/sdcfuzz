# sdcfuzz 方案完备实验验证方案（本机物理验证 + 可扩展远程 SSH 设备）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为 `docs/scheme.md` 的 sdcfuzz 四层架构建立一套**完备、严密、可复现**的实验验证体系：先在本机（0103, Kunpeng 920, 128 核）真实物理环境逐层验证，再把验证基础设施扩展到网络上的远程设备（用户提供 IP/端口/用户名/密码，SSH 连接→测试→验证→反馈→迭代优化测试用例生成），形成"生成→仿真故障验证→真机验证→反馈迭代"的闭环实验平台。

**Architecture:** 三大实验支柱。(A) **仿真层验证**（gem5-CHAOS 故障注入 + ACE/IBR 量化，**本机 `/home/sdc/wangxu/gem5-fi`** 的 gem5.opt——已实测注入全链路可用）证明"生成的用例在故障模型下 SDC 激发率高于基线"；(B) **真机层验证**（silifuzz Snapshot/Runner/Orchestrator 管线，本机 128 核 + 远程多板）证明"用例可在真实硅片上大规模执行、噪声可分类、结果可回收"；(C) **跨层验证**（Sim→HW 统计关联）证明"仿真预测与真机观测正相关"。围绕三支柱构建统一的实验驱动框架 `tools/sdc_experiment/`，其中远程设备管理器（`device_manager.py`）抽象"本机/远程"差异——所有实验脚本面向"设备池"编程，本机是设备池里的 `local` 设备，远程板卡通过用户提供的凭据动态注册进池，**同一套验证命令对两种设备透明**。

**Tech Stack:** Python 3.11（标准库为主 + pyyaml）；silifuzz 工具链（snap_tool / simple_fix_tool_main / reading_runner_main_nolibc / silifuzz_orchestrator_main，已装 /usr/local/bin）；**本机 gem5-CHAOS**（`/home/sdc/wangxu/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt`，v25.1.0.1，运行需 `source ~/gem5-deps/env.sh`；注入配置三件套从 0101 一次性拉取到本机 `gem5_config/`）；Unicorn+capstone（进化引擎）；零依赖密码 SSH 库 `scripts/ssh_lib.py`（pty.fork）。

**Spec:** `docs/scheme.md`（sdcfuzz 四层架构方案，本计划验证其每一层的可验证声明）

## Global Constraints（全局红线，每个任务隐含遵守）

- **诚实红线**：任何实验结论必须基于真实命令输出；未跑出的结果一律标 `未验证`；预注册的判定标准（如 D≥1.5×B）不得事后修改。所有 sweep 输出原文保存到 `output/experiments/`。
- **MCE 红线**：本机 128 核，bazel `--jobs=32`；orchestrator `--max_cpus` 不得超过 64（真机单板扫描建议从 8 起步，逐步上调并观察 SIGSEGV 噪声）；gem5 sweep 串行或 `--jobs≤4`。
- **gem5 O3 ≠ TSV110 RTL**：所有 gem5 diverge 率是模型级结论，报告必须注明。
- **SDC vs 噪声**：真 SDC = RunSnapOutcome 2/3/4（kMemoryMismatch/kRegisterStateMismatch/kEndpointMismatch）；outcome 5 (runaway) / 6 (misbehave) / SIGSEGV-outside-snap = 噪声，绝不混入 SDC 计数。
- **单故障纪律**（gem5 层）：max_faults=1，ROI=[20%,80%] 周期区间，rng-seed 可复现。
- **本机 gem5 编译**：scons `-j16` 上限（29GB 内存，-j126 会 OOM）。
- **分支纪律**：功能分支 `feat/sdc-experiment-verification`，一任务一 commit，验证通过后自动 push（不推 main）。
- **远程凭据**：用户提供的 IP/端口/用户名/密码一律从环境变量/CLI 参数/设备清单文件读取，**绝不硬编码进源码或写进 git**；密码只存在于 `output/devices/*.json`（gitignore）。

## 已验证事实基础（计划前提，全部有据可查）

| # | 事实 | 证据位置 |
|---|------|---------|
| F1 | 19 个微架构模板 .bin 全部可 `snap_tool make` + replay OK | `seeds/bin/`（20 个 .bin） |
| F2 | asm→bin→snapshot→corpus→runner 管线可用：`execution_result:{code:1}` = OK | memory `sdc-snapshot-from-raw-insns-pipeline`（2026/08/26 实测） |
| F3 | gem5-CHAOS bit-flip：A(朴素)=3.9%, B(随机)=8.0%, C(CSP)=3.7%；结构故障：A=2.0%, B=8.4%, C=2.8% | `docs/superpowers/plans/2026-08-20-sdc/paper2-bestpaper-program.md` §二（commit 3e69aa8） |
| F4 | D13 directed-on-random：bit-flip 41/500=8.2%, ratio 3.00×；structural 7.79× | memory `paper2-bbit-honest-recount` + scheme.md §3.1 |
| F5 | 进化引擎原型 T 8→70（8.8×） | `tools/sdc_mutator/evolution_engine.py` + paper2 program §二#7 |
| F6 | 0101/0102 可零依赖密码 SSH（root/SDC@2026）；静态链接 runner/orchestrator 拷贝即运行 | `scripts/ssh_lib.py` + memory `sdc-distributed-scan-boards` |
| F7 | **本机 gem5 注入全链路可用（2026/09/02 实测）**：`~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt`（v25.1.0.1）需 `source ~/gem5-deps/env.sh` 后运行；从 0101 拉取 `two_level_taishan.py`/`caches.py`/`fu_pool.py` + workload `sdc_probe_workload_random` 后：baseline golden `SUM=10721424292087689827 CRC=6728fc4a` **与 0101 逐字节一致**；注入冒烟 5-seed 观测到全部三类结局（clean diverge seed=11 / masked seed=12-15 / abort→no_output seed=7——abort 为 gem5 `panic: Page table fault`，高位翻转让 PC 跑飞所致，既有 sweep 脚本将其归入 no_output 类） | 本次实测（/tmp/g5probe/） |
| F8 | 满负载 SIGSEGV-outside-snap 为资源耗尽噪声，orchestrator 容错继续 | memory `sdc-distributed-scan-boards` |
| F9 | 0101 gem5 环境完整（`/root/gem5-fi/...`），作为本机环境损坏时的**备份**注入环境（本机 gem5.opt md5 `78a1b92c...` ≠ 0101 `0714a0ca...`——两机二进制不同但 golden 逐字节一致，注入行为等价性以 golden+分类一致为准） | 2026/09/02 SSH 实测 |
| F10 | gem5-fi-wangxu 仓有独立 campaign 驱动（`tools/campaign.py` + Wilson CI + 六类分类），与 silifuzz 仓 sweep 脚本不同源 | `/home/sdc/wangxu/gem5-fi-wangxu/tools/campaign.py` |
| F11 | 本机与 0101 的 gem5 版本号一致（25.1.0.1），本机编译于 2026/08/29 | simout.txt `gem5 version 25.1.0.1` |

## 文件结构（File Structure）

所有新增代码集中于 `tools/sdc_experiment/`（统一实验框架），远程设备基础设施在 `tools/sdc_experiment/devices/`，实验驱动脚本在 `scripts/experiments/`，每个实验一个脚本 + 一个结果目录。

| 文件 | 职责 | 状态 |
|------|------|------|
| `tools/sdc_experiment/__init__.py` | 包标记 | 新建 |
| `gem5_config/` | **本机 gem5 注入环境**：0101 拉取的 `configs/`（two_level_taishan.py+deps）与 `workloads/`（A/B/D13 等 ELF+源码），golden 与 0101 逐字节一致（F7 实测） | 新建（一次性拉取入仓） |
| `tools/sdc_experiment/gem5_env.py` | 本机 gem5 运行环境封装：deps 环境变量复刻 + 组表（golden/nc）+ 环境自检 | 新建 |
| `tools/sdc_experiment/experiment_config.py` | 实验配置数据类 + YAML 加载（设备池、预算、判定阈值） | 新建 |
| `tools/sdc_experiment/devices/__init__.py` | 设备子包标记 | 新建 |
| `tools/sdc_experiment/devices/device.py` | `Device` 抽象基类：`probe()/run(cmd)/put(src,dst)/get(src,dst)/specs()` | 新建 |
| `tools/sdc_experiment/devices/local_device.py` | `LocalDevice`（本机 0103）：subprocess 执行 | 新建 |
| `tools/sdc_experiment/devices/remote_device.py` | `RemoteDevice`：SSH/SCP（复用 `scripts/ssh_lib.py`，支持自定义端口/用户/密码） | 新建 |
| `tools/sdc_experiment/devices/device_pool.py` | `DevicePool`：从清单文件/CLI 注册设备、健康检查、批量操作 | 新建 |
| `tools/sdc_experiment/test_device_pool.py` | 设备层单元测试（本机 local + mock remote） | 新建 |
| `tools/sdc_experiment/deploy.py` | 把 silifuzz 工具 + corpus 部署到设备池（静态二进制 + chmod） | 新建 |
| `tools/sdc_experiment/hw_scan.py` | 真机扫描驱动：对设备池跑 orchestrator，收集/解析/分类日志（复用 `collect_results.py` 的解析逻辑） | 新建 |
| `tools/sdc_experiment/sim_sweep.py` | 仿真 sweep 驱动：统一 A/B/D13 分组、bit-flip/byte_lane_skew 双度量、Wilson CI、 Fisher 精确检验（吸收 `gem5_sweep_abcd.py` 逻辑，**本机 gem5-fi 直跑**，不依赖远程） | 新建 |
| `tools/sdc_experiment/correlation.py` | Sim→HW 统计关联：Pearson/Spearman + 置换检验 | 新建 |
| `tools/sdc_experiment/report.py` | 汇总 `output/experiments/` 下所有实验 JSON → 单一 Markdown 报告（含诚实标注列） | 新建 |
| `scripts/experiments/exp01_baseline_repro.sh` | E1：基线复现（A/B bit-flip 各 100 次） | 新建 |
| `scripts/experiments/exp02_d13_vs_random.sh` | E2：D13 vs 随机（bit+struct 各 200 次） | 新建 |
| `scripts/experiments/exp03_corpus_hw_local.sh` | E3：语料真机本机验证 | 新建 |
| `scripts/experiments/exp04_remote_device.sh` | E4：远程设备注册+部署+扫描（模板脚本，凭据由用户给） | 新建 |
| `scripts/experiments/exp05_crosslayer.sh` | E5：跨层关联 | 新建 |
| `scripts/register_device.py` | 用户注册新远程设备的 CLI（交互式/参数式） | 新建 |
| `output/devices/devices.json` | 设备清单（**gitignore**，含密码） | 运行时生成 |
| `output/experiments/` | 所有实验原始输出 + summary JSON（git 管理不含密码） | 运行时生成 |
| `.gitignore` | 追加 `output/devices/` | 修改 |

**复用不重写**：`scripts/ssh_lib.py`（SSH 传输）、`scripts/collect_results.py` 的日志解析正则（提取为 `hw_scan.py` 的 `parse_log()`）、`tools/sdc_mutator/evolution_engine.py`（进化引擎，本计划只调用不修改）、`two_level_taishan.py` 注入配置（从 0101 拉取入仓 `gem5_config/`，只调用不修改）、本机 `~/gem5-fi` gem5.opt（v25.1.0.1，运行环境由 `gem5_env.py` 封装 `~/gem5-deps` 依赖）。

## 实验总表（验证 scheme.md 的哪条声明）

| 实验 | 验证的 scheme.md 声明 | 层 | 设备 | 规模 | 判定 |
|------|----------------------|-----|------|------|------|
| E0 基础设施自检 | ——（前置） | — | 本机 | 一次性 | 全部 probe PASS |
| E1 基线复现 | §3.1 A/B 数据可复现 | L2 | **本机 gem5-fi** | bit-flip A/B 各 100 | B/A≥1.5× 且方向与 F3 一致 |
| E2 D13 vs 随机 | §3.1 "3.00×/7.79×" | L2 | **本机 gem5-fi** | bit+struct 各 200/组 | D13/B≥1.5×（bit）、D13/B≥1.5×（struct），否则诚实记未达 |
| E3 语料真机本机验证 | §4.2 真机执行能力 | L4 | 本机 128 核 | 19 模板语料 × 30min | 0 crash、SDC=0 或 SDC 有 hash 证据、噪声全分类 |
| E4 远程设备扩展 | §4.3 L3 多板分布式 | L3 | 用户设备 + 0101 | 每设备 30min | 远程注册→部署→扫描→回收全链路成功 |
| E5 跨层关联 | §4.4 Sim→HW 统计关联 | L3 | E2+E3/E4 数据 | ≥10 组用例组 | Spearman ρ 的置换检验 p<0.05 或诚实记"样本不足/无相关" |
| E6 报告汇总 | 全部 | — | — | — | `report.py` 生成单一报告 |

**E5 的关键设计**：Sim→HW 关联不能拿"健康 CPU 的真机 0 SDC"去关联"gem5 diverge 率"（无 SDC 时无关联可言）。可行且诚实的跨层关联是：**用例组粒度的执行健康度关联**——对 ≥10 个用例组（19 模板 + A/B/C/D/D13 变体），自变量 = gem5 层指标（diverge 率、Masked 率、Hang 率、golden 校验和存在性），因变量 = 真机层指标（该组语料的 runnable 率、runaway 率、misbehave 率、平均执行时间）。声明弱化为"s仿真的可执行性/稳定性预测真机可执行性/稳定性"。若真机扫描真的检出 SDC（F8 噪声分类之外），再做 case-by-case 关联。这是本计划对 scheme.md §4.4"统计关联验证"的**可落地解释**，报告中明确说明此弱化及原因（健康硅片上 SDC 稀少）。

---

## Task 1: 实验框架骨架 + 配置系统

**Files:**
- Create: `tools/sdc_experiment/__init__.py`
- Create: `tools/sdc_experiment/experiment_config.py`
- Create: `tools/sdc_experiment/test_experiment_config.py`
- Modify: `.gitignore`（追加 `output/devices/`）

**Interfaces:**
- Consumes: 无（纯新增）
- Produces: `ExperimentConfig` dataclass（字段：`experiment_id: str`, `out_dir: Path`, `gem5_opt: Path`, `gem5_script: Path`, `max_cpus: int`, `sweep_runs: int`, `roi: tuple[float,float]`, `wilson_z: float`）；函数 `load_config(path: str) -> ExperimentConfig`；`default_config(experiment_id: str) -> ExperimentConfig`（写死本机路径默认值，可被 YAML 覆盖）

- [x] **Step 1: 写失败测试**

```python
# tools/sdc_experiment/test_experiment_config.py
#!/usr/bin/env python3
"""experiment_config 单元测试。运行: python3 tools/sdc_experiment/test_experiment_config.py"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.sdc_experiment.experiment_config import ExperimentConfig, load_config, default_config

def test_default_config():
    c = default_config("exp01")
    assert c.experiment_id == "exp01"
    assert c.max_cpus <= 64, "MCE 红线: max_cpus 不得超过 64"
    assert c.roi == (0.2, 0.8)
    assert c.sweep_runs >= 1
    print("PASS test_default_config")

def test_load_config_yaml():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("experiment_id: exp99\nsweep_runs: 123\nmax_cpus: 8\n")
        path = f.name
    c = load_config(path)
    assert c.experiment_id == "exp99" and c.sweep_runs == 123 and c.max_cpus == 8
    # 未指定字段取默认
    assert c.roi == (0.2, 0.8)
    os.unlink(path)
    print("PASS test_load_config_yaml")

def test_config_serializable():
    c = default_config("exp01")
    d = json.loads(json.dumps(c.to_dict()))
    assert d["experiment_id"] == "exp01"
    print("PASS test_config_serializable")

if __name__ == "__main__":
    test_default_config(); test_load_config_yaml(); test_config_serializable()
    print("ALL PASS")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python3 tools/sdc_experiment/test_experiment_config.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.sdc_experiment'`

- [x] **Step 3: 实现最小配置系统**

```python
# tools/sdc_experiment/experiment_config.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""experiment_config.py — sdcfuzz 实验验证框架: 配置系统

所有实验共享的参数(设备预算/ROI/判定阈值)集中在此, 单一事实来源。
默认值针对本机 0103 (Kunpeng 920, 128核, openEuler 24.03)。
"""
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # 无 pyyaml 时仅支持 default_config

# 全局红线常量 (CLAUDE.md / 计划 Global Constraints)
MAX_CPUS_HARD_LIMIT = 64          # MCE 红线: 本机并发上限
DEFAULT_ROI = (0.2, 0.8)          # gem5 注入 ROI: [20%, 80%] 周期
WILSON_Z = 1.96                   # 95% CI

@dataclass
class ExperimentConfig:
    experiment_id: str = "exp"
    out_dir: Path = Path("output/experiments")
    # gem5 环境 (本机默认; 远程跑时由设备层覆盖)
    gem5_opt: Path = Path.home() / "gem5-fi/CHAOS/gem5/build/ARM/gem5.opt"
    gem5_script: Path = Path("gem5_config/configs/two_level_taishan.py")  # 入仓的注入配置 (Task 5 Step 0 固化)
    # 真机预算
    max_cpus: int = 8              # 从 8 起步 (F8: 满负载 SIGSEGV 噪声)
    scan_duration_s: int = 1800    # 每次真机扫描 30min
    # sweep 预算
    sweep_runs: int = 100
    roi: tuple = DEFAULT_ROI
    wilson_z: float = WILSON_Z
    # 判定阈值 (预注册, 不得事后修改)
    beat_ratio_threshold: float = 1.5   # D/B ≥ 1.5× 记为击败 (预注册)
    significance_alpha: float = 0.05

    def to_dict(self):
        d = asdict(self)
        d["out_dir"] = str(self.out_dir)
        d["gem5_opt"] = str(self.gem5_opt)
        d["gem5_script"] = str(self.gem5_script)
        d["roi"] = list(self.roi)
        return d

def default_config(experiment_id: str) -> ExperimentConfig:
    return ExperimentConfig(experiment_id=experiment_id,
                            out_dir=Path("output/experiments") / experiment_id)

def load_config(path: str) -> ExperimentConfig:
    if yaml is None:
        raise RuntimeError("pyyaml not installed; use default_config()")
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    base = default_config(raw.get("experiment_id", "exp"))
    for k, v in raw.items():
        if k == "roi":
            v = tuple(v)
        if hasattr(base, k):
            if k in ("out_dir", "gem5_opt", "gem5_script") and v is not None:
                v = Path(v)
            setattr(base, k, v)
    if base.max_cpus > MAX_CPUS_HARD_LIMIT:
        raise ValueError(f"max_cpus={base.max_cpus} exceeds hard limit {MAX_CPUS_HARD_LIMIT} (MCE)")
    return base
```

`__init__.py` 为空文件（包标记）。

`.gitignore` 追加：
```
output/devices/
```

- [x] **Step 4: 运行测试确认通过**

Run: `python3 tools/sdc_experiment/test_experiment_config.py`
Expected: `PASS test_default_config` / `PASS test_load_config_yaml` / `PASS test_config_serializable` / `ALL PASS`

- [x] **Step 5: Commit**

```bash
git checkout -b feat/sdc-experiment-verification
git add tools/sdc_experiment/__init__.py tools/sdc_experiment/experiment_config.py \
        tools/sdc_experiment/test_experiment_config.py .gitignore
git commit -m "feat(experiment): 实验框架骨架——配置系统+MCE红线硬限+预注册判定阈值"
git push -u origin feat/sdc-experiment-verification
```

---

## Task 2: 设备抽象层——LocalDevice

**Files:**
- Create: `tools/sdc_experiment/devices/__init__.py`
- Create: `tools/sdc_experiment/devices/device.py`
- Create: `tools/sdc_experiment/devices/local_device.py`
- Create: `tools/sdc_experiment/test_device_pool.py`（本任务只测 LocalDevice 部分）

**Interfaces:**
- Consumes: 无
- Produces: 抽象基类 `Device`（方法：`name -> str`、`probe() -> dict`（返回 `{"reachable": bool, "arch": str, "cores": int, "mem_gb": int, "os": str, "specs_ok": bool, "errors": list[str]}`）、`run(cmd: str, timeout: int = 60) -> tuple[int, str]`、`put(local: str, remote: str) -> bool`、`get(remote: str, local: str) -> bool`、`tool_path(name: str) -> str`（返回该设备上 silifuzz 工具的绝对路径））；`LocalDevice(work_dir: str = "/tmp/sdc_experiment")`

- [x] **Step 1: 写失败测试**

```python
# tools/sdc_experiment/test_device_pool.py（本任务先写 local 部分）
#!/usr/bin/env python3
"""设备层单元测试。运行: python3 tools/sdc_experiment/test_device_pool.py"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.sdc_experiment.devices.local_device import LocalDevice

def test_local_probe():
    d = LocalDevice()
    p = d.probe()
    assert p["reachable"] is True
    assert p["arch"] == "aarch64", f"本机应为 aarch64, got {p['arch']}"
    assert p["cores"] > 0
    assert p["specs_ok"] is True, f"errors: {p['errors']}"
    print(f"PASS test_local_probe: {p}")

def test_local_run():
    d = LocalDevice()
    rc, out = d.run("echo hello-sdc")
    assert rc == 0 and "hello-sdc" in out
    rc2, _ = d.run("exit 3")
    assert rc2 == 3, f"退出码应透传, got {rc2}"
    print("PASS test_local_run")

def test_local_put_get():
    d = LocalDevice()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("payload-123"); src = f.name
    dst = os.path.join(d.work_dir, "putget_test.txt")
    assert d.put(src, dst) is True
    back = tempfile.mktemp(suffix=".txt")
    assert d.get(dst, back) is True
    assert open(back).read() == "payload-123"
    os.unlink(src); os.unlink(back)
    print("PASS test_local_put_get")

def test_local_tool_path():
    d = LocalDevice()
    p = d.tool_path("snap_tool")
    assert os.path.exists(p), f"snap_tool 应存在于 {p}"
    print(f"PASS test_local_tool_path: {p}")

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: FAIL — `ModuleNotFoundError`

- [x] **Step 3: 实现 Device 基类 + LocalDevice**

```python
# tools/sdc_experiment/devices/device.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""device.py — 设备抽象: 本机与远程板卡对实验脚本透明"""
from abc import ABC, abstractmethod

class Device(ABC):
    """一台可执行 sdcfuzz 验证的机器 (本机或远程 SSH 板卡)。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def probe(self) -> dict:
        """健康检查。返回 {"reachable","arch","cores","mem_gb","os","specs_ok","errors"}。
        specs_ok = arch==aarch64 且内存≥8GB 且 silifuzz 工具可用。"""

    @abstractmethod
    def run(self, cmd: str, timeout: int = 60) -> tuple:
        """执行 shell 命令, 返回 (exit_code, stdout)。"""

    @abstractmethod
    def put(self, local: str, remote: str) -> bool:
        """上传文件到设备, 成功返回 True。"""

    @abstractmethod
    def get(self, remote: str, local: str) -> bool:
        """从设备下载文件, 成功返回 True。"""

    @abstractmethod
    def tool_path(self, name: str) -> str:
        """返回该设备上 silifuzz 工具 (snap_tool/runner/orchestrator/...) 的路径。"""
```

```python
# tools/sdc_experiment/devices/local_device.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""local_device.py — 本机设备 (0103)。subprocess 直执行, put/get 即拷贝。"""
import os, shutil, subprocess
from .device import Device

LOCAL_TOOLS_DIR = "/usr/local/bin"   # F: silifuzz 工具已装 (实测 ls 确认)
LOCAL_TOOLS = ["snap_tool", "simple_fix_tool_main", "reading_runner_main_nolibc",
               "silifuzz_orchestrator_main", "silifuzz_platform_id"]

class LocalDevice(Device):
    def __init__(self, work_dir: str = "/tmp/sdc_experiment", name: str = "local-0103"):
        self._name = name
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return self._name

    def run(self, cmd: str, timeout: int = 60):
        try:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            return 124, "TIMEOUT"

    def probe(self) -> dict:
        errs = []
        rc, uname = self.run("uname -m")
        arch = uname.strip() if rc == 0 else "unknown"
        rc, nproc = self.run("nproc")
        cores = int(nproc.strip()) if rc == 0 and nproc.strip().isdigit() else 0
        mem_gb = 0
        rc, mem = self.run("awk '/MemTotal/{print int($2/1024/1024)}' /proc/meminfo")
        if rc == 0 and mem.strip().isdigit():
            mem_gb = int(mem.strip())
        rc2, osrel = self.run("cat /etc/os-release | head -1")
        missing = [t for t in LOCAL_TOOLS if not os.path.exists(os.path.join(LOCAL_TOOLS_DIR, t))]
        if missing:
            errs.append(f"missing tools: {missing}")
        if arch != "aarch64":
            errs.append(f"arch={arch} != aarch64")
        if mem_gb < 8:
            errs.append(f"mem={mem_gb}GB < 8GB")
        return {"reachable": rc == 0, "arch": arch, "cores": cores, "mem_gb": mem_gb,
                "os": osrel.strip(), "specs_ok": not errs, "errors": errs}

    def put(self, local: str, remote: str) -> bool:
        try:
            os.makedirs(os.path.dirname(remote) or "/", exist_ok=True)
            shutil.copy(local, remote)
            return True
        except OSError:
            return False

    def get(self, remote: str, local: str) -> bool:
        try:
            os.makedirs(os.path.dirname(local) or "/", exist_ok=True)
            shutil.copy(remote, local)
            return True
        except OSError:
            return False

    def tool_path(self, name: str) -> str:
        return os.path.join(LOCAL_TOOLS_DIR, name)
```

`devices/__init__.py` 为空文件。

- [x] **Step 4: 运行测试确认通过**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: 4 个 PASS + `ALL PASS`（probe 输出应显示 `cores: 128, mem_gb: 29, arch: aarch64`）

- [x] **Step 5: Commit**

```bash
git add tools/sdc_experiment/devices/ tools/sdc_experiment/test_device_pool.py
git commit -m "feat(experiment): 设备抽象层——Device 基类 + LocalDevice(0103), probe/run/put/get/tool_path"
git push
```

---

## Task 3: 设备抽象层——RemoteDevice（用户提供的 IP/端口/用户名/密码）

**Files:**
- Create: `tools/sdc_experiment/devices/remote_device.py`
- Modify: `tools/sdc_experiment/test_device_pool.py`（追加 remote 测试：连不通时 SKIP 而非 FAIL）

**Interfaces:**
- Consumes: `scripts/ssh_lib.py` 的 `ssh()/scp()`（`sys.path` 注入 `scripts/` 后 import）
- Produces: `RemoteDevice(host: str, port: int = 22, user: str = "root", password: str | None = None, name: str | None = None, tools_dir: str = "/sdc_tools")`；密码缺省取 `os.environ["SDC_PASSWORD"]`。远端工具路径约定 `tools_dir` 下（部署后 chmod +x）。`probe()` 额外返回 `"gem5": bool`（远端是否有 `~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt`）。

- [x] **Step 1: 写失败测试（连不通时 SKIP）**

在 `test_device_pool.py` 追加：

```python
def test_remote_device_skip_if_unreachable():
    """RemoteDevice 单元测试: 无设备清单时 SKIP (不 FAIL)。
    有清单时 (output/devices/devices.json) 对第一台真测。"""
    import json
    from tools.sdc_experiment.devices.remote_device import RemoteDevice
    cfg_path = "output/devices/devices.json"
    if not os.path.exists(cfg_path):
        print("SKIP test_remote_device: 无设备清单 output/devices/devices.json (用户尚未注册远程设备)")
        return
    devs = json.load(open(cfg_path)).get("devices", [])
    if not devs:
        print("SKIP test_remote_device: 设备清单为空")
        return
    d0 = devs[0]
    d = RemoteDevice(host=d0["host"], port=d0.get("port", 22),
                     user=d0.get("user", "root"), password=d0.get("password"),
                     name=d0.get("name"))
    p = d.probe()
    if not p["reachable"]:
        print(f"SKIP test_remote_device: {d.name} 不可达, probe={p}")
        return
    rc, out = d.run("echo remote-ok")
    assert rc == 0 and "remote-ok" in out
    print(f"PASS test_remote_device: {d.name} probe={p}")

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    test_remote_device_skip_if_unreachable()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: FAIL — `ModuleNotFoundError: ... remote_device`（local 部分仍 PASS，remote import 报错）

- [x] **Step 3: 实现 RemoteDevice**

```python
# tools/sdc_experiment/devices/remote_device.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""remote_device.py — 远程 SSH 板卡设备 (用户提供 IP/端口/用户名/密码)。

复用 scripts/ssh_lib.py 的零依赖 pty 密码 SSH。与 LocalDevice 同接口,
实验脚本对两种设备透明。凭据只来自参数/清单文件(绝不用硬编码)。
"""
import os, re, sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SCRIPTS = os.path.join(_REPO, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from ssh_lib import ssh as _ssh, scp as _scp, _run, SSH_OPTS   # noqa: E402

GEM5_PROBE = "ls ~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt"

class RemoteDevice:
    def __init__(self, host: str, port: int = 22, user: str = "root",
                 password: str | None = None, name: str | None = None,
                 tools_dir: str = "/sdc_tools"):
        self.host, self.port, self.user = host, port, user
        self._password = password or os.environ.get("SDC_PASSWORD", "")
        self._name = name or f"remote-{host}"
        self.tools_dir = tools_dir

    @property
    def name(self) -> str:
        return self._name

    def _ssh(self, cmd: str, timeout: int = 60) -> tuple:
        """ssh_lib 不透传退出码 → 用 'cmd; echo RC=$?' 约定解析。"""
        out = _ssh(self.host, f"{cmd}; echo RC=$?", password=self._password,
                   timeout=timeout, user=self.user)
        m = re.search(r"RC=(\d+)\s*$", out.strip())
        rc = int(m.group(1)) if m else 1
        text = re.sub(r"\n?RC=\d+\s*$", "", out)
        return rc, text

    def run(self, cmd: str, timeout: int = 60) -> tuple:
        return self._ssh(cmd, timeout)

    def probe(self) -> dict:
        errs = []
        rc, uname = self.run("uname -m", timeout=15)
        if rc != 0:
            return {"reachable": False, "arch": "unknown", "cores": 0, "mem_gb": 0,
                    "os": "", "specs_ok": False, "errors": [f"ssh rc={rc}"], "gem5": False}
        arch = uname.strip()
        _, nproc = self.run("nproc", timeout=15)
        cores = int(nproc.strip()) if nproc.strip().isdigit() else 0
        _, mem = self.run("awk '/MemTotal/{print int($2/1024/1024)}' /proc/meminfo", timeout=15)
        mem_gb = int(mem.strip()) if mem.strip().isdigit() else 0
        _, osrel = self.run("head -1 /etc/os-release", timeout=15)
        rc_g, _ = self.run(f"test -f {GEM5_PROBE.replace('~', '$HOME')}", timeout=15)
        has_gem5 = rc_g == 0
        # 工具检查: tools_dir 下或 PATH
        _, tchk = self.run(
            f"for t in snap_tool simple_fix_tool_main reading_runner_main_nolibc "
            f"silifuzz_orchestrator_main; do command -v $t >/dev/null 2>&1 || "
            f"test -x {self.tools_dir}/$t || echo MISS:$t; done", timeout=15)
        for line in tchk.splitlines():
            if line.startswith("MISS:"):
                errs.append(f"missing tool {line[5:]} (deploy first)")
        if arch != "aarch64":
            errs.append(f"arch={arch} != aarch64")
        if mem_gb < 8:
            errs.append(f"mem={mem_gb}GB < 8GB")
        return {"reachable": True, "arch": arch, "cores": cores, "mem_gb": mem_gb,
                "os": osrel.strip(), "specs_ok": not errs, "errors": errs, "gem5": has_gem5}

    def put(self, local: str, remote: str) -> bool:
        out = _scp(local, remote, self.host, password=self._password,
                   timeout=300, user=self.user)
        rc, _ = self._ssh(f"test -f {remote}", timeout=15)
        return rc == 0

    def get(self, remote: str, local: str) -> bool:
        # ssh_lib.scp 只支持上传; 下载直接组装 scp 命令 (远端在 src 位)
        out = _run(["scp"] + SSH_OPTS + [f"{self.user}@{self.host}:{remote}", local],
                   self._password, timeout=300, is_scp=True)
        return os.path.exists(local)

    def tool_path(self, name: str) -> str:
        return f"{self.tools_dir}/{name}"
```

> **注意 `get()` 的方向**（已核对 `scripts/ssh_lib.py` 源码）：`ssh_lib.scp(src, dst, host)` 的 dst 形如 `host:path`，**总是向远端上传**，没有下载函数。`get()` 的正确实现是直接调 `ssh_lib._run` 组装 `["scp"] + SSH_OPTS + [f"{user}@{host}:{remote}", local]`（把远端路径放 src 位）。验收标准：有真实设备时 `test_remote_device` 的 put/get 真测通过；无设备时以 0101 冒烟（Task 3 Step 5）覆盖。

- [x] **Step 4: 运行测试**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: 4 个 local PASS + `SKIP test_remote_device`（无清单时）或 `PASS test_remote_device`（有清单时）+ `ALL PASS`

- [x] **Step 5: 用真实板卡 0101 冒烟验证（一次性，人工确认）**

```bash
mkdir -p output/devices
cat > output/devices/devices.json <<'EOF'
{
  "devices": [
    {"name": "0101", "host": "172.168.177.97", "port": 22, "user": "root", "password": "SDC@2026", "tools_dir": "/sdc_tools"}
  ]
}
EOF
python3 tools/sdc_experiment/test_device_pool.py
```
Expected: `PASS test_remote_device: 0101 probe={... 'cores': 126 ...}`（F6/F7 基础上应可达；若 SKIP/FAIL 则记录原因，不阻塞——0101 仅是冒烟对象，正式远程设备由用户提供）

- [x] **Step 6: Commit**

```bash
git add tools/sdc_experiment/devices/remote_device.py tools/sdc_experiment/test_device_pool.py
git commit -m "feat(experiment): RemoteDevice——用户凭据 SSH 设备, probe/run/put/get 与本机透明; 连不通时测试 SKIP"
git push
```

---

## Task 4: DevicePool + 设备注册 CLI

**Files:**
- Create: `tools/sdc_experiment/devices/device_pool.py`
- Create: `scripts/register_device.py`
- Modify: `tools/sdc_experiment/test_device_pool.py`（追加 pool 测试）

**Interfaces:**
- Consumes: `LocalDevice`, `RemoteDevice`
- Produces: `DevicePool`（`add_local(name)`, `add_remote(host, port, user, password, name, tools_dir)`, `load(path) -> DevicePool`（读 devices.json）, `save(path)`（**抹除密码后**写公开清单 `devices.public.json`）, `probe_all() -> dict[name, probe]`, `get(name) -> Device`, `devices -> list[Device]`, `healthy -> list[Device]`）；CLI `register_device.py --name NAME --host IP --port 22 --user root [--password-env SDC_PASSWORD] [--tools-dir /sdc_tools] [--gem5]`（追加式注册到 `output/devices/devices.json`，密码建议从环境变量读，也接受 `--password` 但会警告）

- [x] **Step 1: 写失败测试**

追加到 `test_device_pool.py`：

```python
def test_device_pool_roundtrip():
    import json, tempfile
    from tools.sdc_experiment.devices.device_pool import DevicePool
    pool = DevicePool()
    pool.add_local("local-0103")
    pool.add_remote("192.0.2.1", port=2222, user="test", password="pw",
                    name="fake-board", tools_dir="/tmp/sdc_tools")
    assert len(pool.devices) == 2
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        path = f.name
    pool.save(path)   # 公开版: 抹密码
    data = json.load(open(path))
    assert "password" not in json.dumps(data), "公开清单不得含密码"
    assert data["devices"][1]["host"] == "192.0.2.1"
    assert data["devices"][1]["port"] == 2222
    os.unlink(path)
    # probe_all: local 真测, fake-board 不可达但不应抛异常
    probes = pool.probe_all(timeout=15)
    assert probes["local-0103"]["specs_ok"] is True
    assert probes["fake-board"]["reachable"] is False
    print("PASS test_device_pool_roundtrip")

if __name__ == "__main__":
    test_local_probe(); test_local_run(); test_local_put_get(); test_local_tool_path()
    test_remote_device_skip_if_unreachable()
    test_device_pool_roundtrip()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: FAIL — `ImportError: device_pool`

- [x] **Step 3: 实现 DevicePool + 注册 CLI**

```python
# tools/sdc_experiment/devices/device_pool.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""device_pool.py — 设备池: 本机 + 远程板卡统一注册/探活/批量操作。

清单文件 output/devices/devices.json 含密码 (gitignore);
save() 只写抹除密码的公开清单 devices.public.json。
"""
import json, os
from .local_device import LocalDevice
from .remote_device import RemoteDevice

DEFAULT_REGISTRY = "output/devices/devices.json"

class DevicePool:
    def __init__(self):
        self._devices = []

    def add_local(self, name: str = "local-0103"):
        self._devices.append(LocalDevice(name=name))

    def add_remote(self, host: str, port: int = 22, user: str = "root",
                   password: str = "", name: str = None, tools_dir: str = "/sdc_tools"):
        self._devices.append(RemoteDevice(host=host, port=port, user=user,
                                          password=password, name=name,
                                          tools_dir=tools_dir))

    @property
    def devices(self):
        return list(self._devices)

    def get(self, name: str):
        for d in self._devices:
            if d.name == name:
                return d
        raise KeyError(f"no device named {name}")

    def load(self, path: str = DEFAULT_REGISTRY):
        with open(path) as f:
            data = json.load(f)
        for spec in data.get("devices", []):
            if spec.get("type") == "local":
                self.add_local(spec.get("name", "local"))
            else:
                self.add_remote(spec["host"], port=spec.get("port", 22),
                                user=spec.get("user", "root"),
                                password=spec.get("password", ""),
                                name=spec.get("name"),
                                tools_dir=spec.get("tools_dir", "/sdc_tools"))
        return self

    def save(self, path: str):
        """写公开清单 (抹密码)。含密码清单由 register_device.py 维护。"""
        out = {"devices": []}
        for d in self._devices:
            if isinstance(d, LocalDevice):
                out["devices"].append({"type": "local", "name": d.name})
            else:
                out["devices"].append({
                    "type": "remote", "name": d.name, "host": d.host,
                    "port": d.port, "user": d.user, "tools_dir": d.tools_dir})
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

    def probe_all(self, timeout: int = 30) -> dict:
        return {d.name: d.probe() for d in self._devices}

    @property
    def healthy(self):
        return [d for d in self._devices if d.probe()["specs_ok"]]
```

```python
# scripts/register_device.py
#!/usr/bin/env python3
# SPDX-License-License: Apache-2.0
"""register_device.py — 注册用户提供的远程设备到设备清单。

用法:
  python3 scripts/register_device.py --name board-05 --host 10.0.0.5 \
      --port 22 --user root --password-env SDC_PASSWORD --tools-dir /sdc_tools
  # 或 --password 'xxx' (会警告: 建议用 --password-env)
注册后立即探活并打印 probe 结果。
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_experiment.devices.device_pool import DevicePool, DEFAULT_REGISTRY

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default=None, help="明文密码 (不建议; 优先 --password-env)")
    ap.add_argument("--password-env", default="SDC_PASSWORD", help="从该环境变量读密码")
    ap.add_argument("--tools-dir", default="/sdc_tools")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    a = ap.parse_args()
    pw = a.password or os.environ.get(a.password_env, "")
    if not pw:
        sys.exit(f"ERROR: 无密码。设 {a.password_env} 环境变量或传 --password")
    if a.password:
        print("WARNING: --password 明文传入; 建议改用 --password-env")
    reg = {}
    if os.path.exists(a.registry):
        reg = json.load(open(a.registry))
    reg.setdefault("devices", [])
    if any(d.get("host") == a.host and d.get("port") == a.port for d in reg["devices"]):
        sys.exit(f"ERROR: {a.host}:{a.port} 已注册")
    reg["devices"].append({"name": a.name, "host": a.host, "port": a.port,
                           "user": a.user, "password": pw, "tools_dir": a.tools_dir})
    os.makedirs(os.path.dirname(a.registry) or ".", exist_ok=True)
    json.dump(reg, open(a.registry, "w"), indent=2, ensure_ascii=False)
    print(f"已注册 {a.name} -> {a.host}:{a.port} (清单 {a.registry}, 该文件已 gitignore)")
    # 立即探活
    pool = DevicePool().load(a.registry)
    p = pool.get(a.name).probe()
    print(f"probe: {json.dumps(p, ensure_ascii=False, indent=2)}")
    if not p["reachable"]:
        print("WARNING: 设备不可达, 请检查 IP/端口/用户/密码")
    elif not p["specs_ok"]:
        print(f"NOTE: 可达但规格未就绪: {p['errors']} (部署工具后自动消除)")

if __name__ == "__main__":
    main()
```

- [x] **Step 4: 运行测试确认通过**

Run: `python3 tools/sdc_experiment/test_device_pool.py`
Expected: 全部 PASS/预期 SKIP + `ALL PASS`（`test_device_pool_roundtrip` 中 fake-board 不可达探活约需 10-15s 超时）

- [x] **Step 5: Commit**

```bash
git add tools/sdc_experiment/devices/device_pool.py scripts/register_device.py \
        tools/sdc_experiment/test_device_pool.py
git commit -m "feat(experiment): DevicePool 设备池+注册 CLI——用户凭据注册远程板卡, 公开清单抹密码"
git push
```

---

## Task 5: 本机 gem5 注入环境固化 + 仿真 sweep 驱动 sim_sweep（E1/E2 核心）

**Files:**
- Create: `gem5_config/`（从 0101 拉取的注入配置三件套 + workload，入 git）
- Create: `tools/sdc_experiment/gem5_env.py`（本机 gem5 运行环境封装）
- Create: `tools/sdc_experiment/sim_sweep.py`
- Create: `tools/sdc_experiment/test_sim_sweep.py`
- Create: `scripts/experiments/exp01_baseline_repro.sh`
- Create: `scripts/experiments/exp02_d13_vs_random.sh`

**Interfaces:**
- Consumes: `ExperimentConfig`（roi/sweep_runs）；`gem5_env.py` 提供的 `local_gem5_env() -> dict`（返回 `{"gem5": str, "script": str, "workloads": dict, "env": dict}`——gem5.opt 绝对路径、taishan 脚本路径、workload 路径表、含 `LD_LIBRARY_PATH`/`PATH`/`PYTHONPATH` 的环境变量字典）
- Produces: `run_group(group, mode, n_runs, seed, cfg) -> dict`（返回 `{"group","mode","n","clean_diverge","masked","exit_diverge","no_output","diverge_rate","wilson_low","wilson_high"}`）；`wilson(k, n, z)`；`fisher_exact(a,b,c,d) -> (odds_ratio, p_value)`（2×2 双侧 Fisher，无 scipy 依赖——手写超几何分布）；CLI：`python3 tools/sdc_experiment/sim_sweep.py --group A|B|D13 --mode bit|struct --runs N --exp expXX`

**关键设计——本机 gem5 注入环境（新增 Task 5 Step 0 固化）**：本机 gem5.opt 运行依赖 `~/gem5-deps/env.sh` 的环境变量（LD_LIBRARY_PATH 指向解包的 protobuf/absl 等），注入配置（`two_level_taishan.py`+`caches.py`+`fu_pool.py`）和 workload 二进制从 0101 一次性拉取入仓（F7 已实测此组合的 golden 与 0101 逐字节一致）。环境封装进 `gem5_env.py`，此后所有仿真实验**只在本机跑**，不依赖 0101。gem5 abort（Page table fault panic）按既有 sweep 语义归入 `no_output` 类（F7 实测确认该行为与 0101 一致）。

**工作负载组表（单一事实来源）**：从 F3/F4 与 `gem5_sweep_abcd.py`/`d13_sweep.py` 提取硬编码，集中为模块级 `GROUPS` 字典，路径指向 `gem5_config/` 下入仓的 workload。每 run 输出目录在本机 `output/experiments/{exp}/runs/{group}_{mode}_{i:03d}/`，解析 `simout.txt` 中 `SUM=` 行与 golden 比对（判定逻辑与 `gem5_sweep_abcd.py` 完全一致：无输出=no_output；==golden=masked；含 "Exiting"=exit_diverge；否则=clean_diverge）。

- [x] **Step 0: 固化本机 gem5 注入环境（配置+workload 入仓）**

```bash
# 从 0101 拉取注入配置三件套 + 全部 sdc_probe workload (源码+二进制)
mkdir -p gem5_config/configs gem5_config/workloads
python3 - <<'EOF'
import sys, os
sys.path.insert(0, "scripts")
import ssh_lib
HOST = "172.168.177.97"
# 配置三件套 (F7 已实测可从 0101 拉取)
for f in ["two_level_taishan.py", "caches.py", "fu_pool.py"]:
    ssh_lib._run(["scp"] + ssh_lib.SSH_OPTS +
                 [f"root@{HOST}:/root/gem5-fi/smoke_test/configs/{f}",
                  f"gem5_config/configs/{f}"], "SDC@2026", timeout=60, is_scp=True)
# workload 二进制 + 源码 (A/B/D13 必需; 其余 D 组一并拉全备用)
out = ssh_lib.ssh(HOST, "ls /root/gem5-fi/smoke_test/sdc_probe/ | grep -v '\\.c$'")
files = [l.strip() for l in out.splitlines() if l.strip() and "module" not in l]
for f in files:
    ssh_lib._run(["scp"] + ssh_lib.SSH_OPTS +
                 [f"root@{HOST}:/root/gem5-fi/smoke_test/sdc_probe/{f}",
                  f"gem5_config/workloads/{f}"], "SDC@2026", timeout=60, is_scp=True)
# 源码也拉 (可读性 + 复现凭证)
out2 = ssh_lib.ssh(HOST, "ls /root/gem5-fi/smoke_test/sdc_probe/*.c")
for line in out2.splitlines():
    f = line.strip().rsplit("/", 1)[-1]
    if f:
        ssh_lib._run(["scp"] + ssh_lib.SSH_OPTS +
                     [f"root@{HOST}:/root/gem5-fi/smoke_test/sdc_probe/{f}",
                      f"gem5_config/workloads/{f}"], "SDC@2026", timeout=60, is_scp=True)
print("pulled:", sorted(os.listdir("gem5_config/workloads")))
EOF
chmod +x gem5_config/workloads/sdc_probe_workload*
```

固化后立即复验（golden 逐字节一致才算过）：
```bash
source ~/gem5-deps/env.sh
mkdir -p /tmp/g5verify && cd /tmp/g5verify
timeout 300 /home/sdc/wangxu/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt -r -e --silent-redirect -d v1 \
  /home/sdc/wangxu/silifuzz/gem5_config/configs/two_level_taishan.py \
  --binary /home/sdc/wangxu/silifuzz/gem5_config/workloads/sdc_probe_workload_random --mode baseline
grep "SUM=" v1/simout.txt
# Expected: SUM=10721424292087689827 CRC=6728fc4a (F7 golden, 与 0101 逐字节一致)
```

- [x] **Step 0b: 实现 gem5_env.py（本机 gem5 环境封装）**

```python
# tools/sdc_experiment/gem5_env.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_env.py — 本机 gem5-CHAOS 注入环境封装。

本机 gem5.opt (v25.1.0.1) 运行依赖 ~/gem5-deps (解包 RPM) 的环境变量;
注入配置与 workload 已固化入仓 gem5_config/ (来源: 0101, golden 逐字节
一致, 见计划 F7)。此后仿真实验 100% 本机自持, 不依赖远程板卡。
"""
import os

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPS = os.path.expanduser("~/gem5-deps")

GEM5_OPT = os.path.expanduser("~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt")
TAISHAN_SCRIPT = os.path.join(_REPO, "gem5_config/configs/two_level_taishan.py")
WORKLOAD_DIR = os.path.join(_REPO, "gem5_config/workloads")

# 复刻 ~/gem5-deps/env.sh 的关键环境 (source 不可用于 subprocess)
def local_gem5_env() -> dict:
    env = dict(os.environ)
    deps = DEPS
    env["PATH"] = f"{deps}/py/usr/bin:/usr/local/bin:/usr/bin:/bin"
    env["LD_LIBRARY_PATH"] = (f"{deps}/usr/lib64:{deps}/py/usr/lib64:"
                              f"/usr/lib64:{env.get('LD_LIBRARY_PATH','')}")
    env["PYTHONPATH"] = (f"{deps}/usr/lib/python3.11/site-packages:"
                         f"{deps}/py/usr/lib/python3.11/site-packages:"
                         f"{deps}/py/usr/lib64/python3.11/site-packages:"
                         f"{env.get('PYTHONPATH','')}")
    return env

# 工作负载组表 (golden/nc 来自已验证 sweep: F3/F4; 路径指向入仓 workload)
GROUPS = {
    "A":   {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload"),
            "golden": "SUM=1176263118239748788 CRC=5b8846f3", "nc": 63788},
    "B":   {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload_random"),
            "golden": "SUM=10721424292087689827 CRC=6728fc4a", "nc": 71215},
    "D13": {"binary": os.path.join(WORKLOAD_DIR, "sdc_probe_workload_d13"),
            "golden": "SUM=118831515424667458 CRC=dbc8bf2a", "nc": 110946},
}

def check_env() -> dict:
    """自检: gem5.opt 存在 + deps 存在 + 各 workload 存在 + golden 可复现标记。"""
    problems = []
    if not os.path.exists(GEM5_OPT):
        problems.append(f"gem5.opt missing: {GEM5_OPT}")
    if not os.path.isdir(DEPS):
        problems.append(f"gem5-deps missing: {DEPS}")
    if not os.path.exists(TAISHAN_SCRIPT):
        problems.append(f"taishan script missing: {TAISHAN_SCRIPT}")
    for g, spec in GROUPS.items():
        if not os.path.exists(spec["binary"]):
            problems.append(f"workload {g} missing: {spec['binary']}")
    return {"ok": not problems, "problems": problems}
```

- [x] **Step 1: 写失败测试（本地可测的纯函数）**

```python
# tools/sdc_experiment/test_sim_sweep.py
#!/usr/bin/env python3
"""sim_sweep 纯函数单元测试 (不跑 gem5)。运行: python3 tools/sdc_experiment/test_sim_sweep.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.sim_sweep import wilson, fisher_exact, classify_output

def test_wilson():
    # 41/500 的 Wilson 95% CI (对照 memory paper2-bbit-honest-recount: 8.2%)
    lo, p, hi = wilson(41, 500)
    assert abs(p - 0.082) < 1e-9
    assert lo < 0.082 < hi
    # 0/500: rule of 3 上界 ≈ 3/500
    lo0, p0, hi0 = wilson(0, 500)
    assert p0 == 0.0 and abs(hi0 - 3/500) < 0.005
    print(f"PASS test_wilson: 41/500 -> [{lo:.4f}, {hi:.4f}]")

def test_fisher_exact():
    # D13=41/500 vs B=40/500 → 不显著 (ratio 1.02)
    orr, p = fisher_exact(41, 459, 40, 460)
    assert p > 0.05, f"p={p} 应不显著"
    # 极端: 50/100 vs 0/100 → 显著
    orr2, p2 = fisher_exact(50, 50, 0, 100)
    assert p2 < 0.01, f"p2={p2} 应显著"
    print(f"PASS test_fisher_exact: p={p:.4f}, p2={p2:.2e}")

def test_classify():
    g = "SUM=123 CRC=abc"
    assert classify_output("SUM=123 CRC=abc", g) == "masked"
    assert classify_output("SUM=999 CRC=xyz", g) == "clean_diverge"
    assert classify_output("SUM=999 Exiting", g) == "exit_diverge"
    assert classify_output("", g) == "no_output"
    assert classify_output(None, g) == "no_output"
    print("PASS test_classify")

if __name__ == "__main__":
    test_wilson(); test_fisher_exact(); test_classify()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_sim_sweep.py`
Expected: FAIL — `ImportError: sim_sweep`

- [x] **Step 3: 实现 sim_sweep**

```python
# tools/sdc_experiment/sim_sweep.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""sim_sweep.py — 仿真层故障注入 sweep 驱动 (E1/E2), 100% 本机执行。

统一驱动 A/B/D13 等工作组在本机 gem5-CHAOS 上做 bit-flip / byte_lane_skew
注入, 统计 diverge 率 + Wilson CI + Fisher 精确检验。判定逻辑与既有
scripts/gem5_sweep_abcd.py / d13_sweep.py 逐字段一致 (可交叉校验)。
"""
import argparse, json, math, os, random, shutil, subprocess, sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from tools.sdc_experiment.gem5_env import (GEM5_OPT, TAISHAN_SCRIPT,
                                           GROUPS, local_gem5_env)

def wilson(k: int, n: int, z: float = 1.96):
    """Wilson score CI。k=0 时上界≈rule-of-3 (3/n)。"""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - half), p, min(1.0, center + half))

def _log_comb(n, k):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

def fisher_exact(a: int, b: int, c: int, d: int):
    """2x2 Fisher 精确检验 (双侧, 超几何), 无 scipy。返回 (odds_ratio, p)。
    表: [[a,b],[c,d]] = [[diverge_D, total_D-diverge_D],
                          [diverge_B, total_B-diverge_B]]"""
    n = a + b + c + d
    row1, col1 = a + b, a + c
    def prob(k):
        return math.exp(_log_comb(col1, k) + _log_comb(n - col1, row1 - k)
                        - _log_comb(n, row1))
    p_obs = prob(a)
    lo, hi = max(0, row1 - (n - col1)), min(row1, col1)
    p_two = sum(prob(k) for k in range(lo, hi + 1) if prob(k) <= p_obs + 1e-12)
    odds = (a * d) / (b * c) if b and c else float("inf")
    return (odds, min(1.0, p_two))

def classify_output(workload_line, golden: str) -> str:
    if not workload_line:
        return "no_output"
    if workload_line == golden:
        return "masked"
    if "Exiting" in workload_line:
        return "exit_diverge"
    return "clean_diverge"

def run_group(group: str, mode: str, n_runs: int, seed: int, cfg) -> dict:
    """对一工作组在本机 gem5 跑 n_runs 次注入。mode: bit|struct。"""
    g = GROUPS[group]
    env = local_gem5_env()
    rng = random.Random(seed)
    roi_lo, roi_hi = int(g["nc"] * cfg.roi[0]), int(g["nc"] * cfg.roi[1])
    out_root = os.path.join("output", "experiments", cfg.experiment_id,
                            "runs", f"{group}_{mode}")
    shutil.rmtree(out_root, ignore_errors=True)
    os.makedirs(out_root, exist_ok=True)
    counts = {"clean_diverge": 0, "masked": 0, "exit_diverge": 0, "no_output": 0}
    for i in range(n_runs):
        fc = rng.randint(roi_lo, roi_hi)
        outdir = os.path.join(out_root, f"run_{i:03d}")
        os.makedirs(outdir, exist_ok=True)
        cmd = [GEM5_OPT, "-r", "-e", "--silent-redirect", "-d", outdir,
               TAISHAN_SCRIPT, "--binary", g["binary"], "--mode", "inject",
               "--first-clock", str(fc), "--max-faults", "1",
               "--probability", "1.0", "--rng-seed", str(seed + i)]
        if mode == "struct":
            cmd += ["--injector", "lsq_fwd", "--structural-fault", "byte_lane_skew"]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        except subprocess.TimeoutExpired:
            pass   # → no_output (与既有 sweep 语义一致)
        wl = ""
        simout = os.path.join(outdir, "simout.txt")
        if os.path.exists(simout):
            for line in open(simout, errors="replace"):
                if "SUM=" in line:
                    wl = line.strip()
                    break
        counts[classify_output(wl, g["golden"])] += 1
        # 每 run 目录只留判定证据, 清掉大文件防磁盘膨胀 (stats/config)
        for junk in ("stats.txt", "config.ini", "config.json", "citations.bib"):
            p = os.path.join(outdir, junk)
            if os.path.exists(p):
                os.unlink(p)
    n = sum(counts.values())
    k = counts["clean_diverge"]
    lo, p, hi = wilson(k, n, cfg.wilson_z)
    return {"group": group, "mode": mode, "n": n, **counts,
            "diverge_rate": round(p, 4), "wilson_low": round(lo, 4),
            "wilson_high": round(hi, 4), "seed": seed,
            "host": "local-0103-gem5", "gem5_note": "gem5 O3 model, not TSV110 RTL"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, choices=list(GROUPS))
    ap.add_argument("--mode", required=True, choices=["bit", "struct"])
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--exp", default="exp00")
    a = ap.parse_args()
    from tools.sdc_experiment.experiment_config import default_config
    cfg = default_config(a.exp)
    res = run_group(a.group, a.mode, a.runs, a.seed, cfg)
    os.makedirs(cfg.out_dir, exist_ok=True)
    out_json = cfg.out_dir / f"sim_{a.group}_{a.mode}.json"
    json.dump(res, open(out_json, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"saved -> {out_json}")

if __name__ == "__main__":
    main()
```

- [x] **Step 4: 运行纯函数测试确认通过**

Run: `python3 tools/sdc_experiment/test_sim_sweep.py`
Expected: 3 个 PASS + `ALL PASS`

- [x] **Step 5: 冒烟验证（3 次 run 真跑本机 gem5）**

```bash
python3 tools/sdc_experiment/sim_sweep.py --group B --mode bit --runs 3 --seed 99 --exp exp00-smoke
```
Expected: 输出 JSON `n=3`，四类计数之和为 3，无异常退出（约 3×2min；F7 已实测本机注入链路产出全部三类结局）

- [x] **Step 6: E1 实验脚本**

```bash
#!/bin/bash
# scripts/experiments/exp01_baseline_repro.sh — E1: 基线复现 (A/B bit-flip 各100次, 本机 gem5)
# 判定(预注册): B/A diverge率 ≥ 1.5× 且方向与 F3 (B=8.0% > A=3.9%) 一致
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp01-baseline-repro
for G in A B; do
  python3 tools/sdc_experiment/sim_sweep.py --group $G \
      --mode bit --runs 100 --seed 42 --exp $EXP
done
python3 - "$EXP" <<'EOF'
import json, sys, os
sys.path.insert(0, ".")
from tools.sdc_experiment.sim_sweep import fisher_exact
exp = sys.argv[1]
A = json.load(open(f"output/experiments/{exp}/sim_A_bit.json"))
B = json.load(open(f"output/experiments/{exp}/sim_B_bit.json"))
ratio = B["diverge_rate"] / A["diverge_rate"] if A["diverge_rate"] else float("inf")
_, p = fisher_exact(B["clean_diverge"], B["n"] - B["clean_diverge"],
                    A["clean_diverge"], A["n"] - A["clean_diverge"])
verdict = "REPRODUCED" if ratio >= 1.5 else "NOT_REPRODUCED(诚实记录)"
summary = {"A": A, "B": B, "B_over_A_ratio": round(ratio, 3),
           "fisher_p": round(p, 5), "verdict": verdict,
           "note": "gem5 O3 model, not TSV110 RTL; 对照 F3: A=3.9%, B=8.0%"}
json.dump(summary, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=2))
EOF
```

- [x] **Step 7: E2 实验脚本**

```bash
#!/bin/bash
# scripts/experiments/exp02_d13_vs_random.sh — E2: D13 vs B (bit+struct 各200次, 本机 gem5)
# 判定(预注册): D13/B ≥ 1.5× 记为击败; 对照 F4 (bit 3.00×, struct 7.79×)
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp02-d13-vs-random
for MODE in bit struct; do
  for G in B D13; do
    python3 tools/sdc_experiment/sim_sweep.py --group $G \
        --mode $MODE --runs 200 --seed 42 --exp $EXP
  done
done
python3 - "$EXP" <<'EOF'
import json, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.sim_sweep import fisher_exact
exp = sys.argv[1]
out = {}
for mode in ["bit", "struct"]:
    B = json.load(open(f"output/experiments/{exp}/sim_B_{mode}.json"))
    D = json.load(open(f"output/experiments/{exp}/sim_D13_{mode}.json"))
    ratio = D["diverge_rate"] / B["diverge_rate"] if B["diverge_rate"] else float("inf")
    _, p = fisher_exact(D["clean_diverge"], D["n"] - D["clean_diverge"],
                        B["clean_diverge"], B["n"] - B["clean_diverge"])
    out[mode] = {"B": B, "D13": D, "D_over_B": round(ratio, 3), "fisher_p": round(p, 5),
                 "verdict": "BEAT" if ratio >= 1.5 and p < 0.05 else
                            ("MARGINAL" if ratio >= 1.5 else "NOT_BEAT(诚实记录)")}
json.dump(out, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(out, ensure_ascii=False, indent=2))
EOF
```

> 预算评估（本机串行）：E1 = 200 run × ~1min ≈ 3.5h；E2 = 800 run ≈ 14h。`nohup bash scripts/experiments/exp0X.sh > output/experiments/exp0X.log 2>&1 &` 后台跑。可加 `--jobs 2` 并行（本机 128 核，gem5 单 run 单核，2-4 路并行安全；实现时在 sim_sweep 加简单进程池即可，默认串行最稳）。若时长不可接受，降为 `--runs 100`，判定阈值不变。

- [x] **Step 8: 运行 E1（真跑）并保存输出**

Run: `nohup bash scripts/experiments/exp01_baseline_repro.sh > output/experiments/exp01.log 2>&1 &` 然后轮询 `tail output/experiments/exp01.log`
Expected: `summary.json` 生成，`verdict` 为 `REPRODUCED`（若 NOT_REPRODUCED 则诚实记录并诊断——先核对本机 gem5-opt/gem5-deps/gem5_config 是否完好，再对照 F3 排查 ROI/seed 差异）

- [x] **Step 9: 运行 E2（真跑）并保存输出**

Run: `nohup bash scripts/experiments/exp02_d13_vs_random.sh > output/experiments/exp02.log 2>&1 &`
Expected: `summary.json` 生成；bit 与 struct 各有 verdict（BEAT/MARGINAL/NOT_BEAT 皆可接受，**如实记录**）

- [x] **Step 10: Commit**

```bash
git add gem5_config/ tools/sdc_experiment/gem5_env.py tools/sdc_experiment/sim_sweep.py \
        tools/sdc_experiment/test_sim_sweep.py \
        scripts/experiments/exp01_baseline_repro.sh scripts/experiments/exp02_d13_vs_random.sh \
        output/experiments/exp01-baseline-repro/ output/experiments/exp02-d13-vs-random/
git commit -m "feat(experiment): 本机gem5注入环境固化+E1基线复现+E2 D13vs随机——sim_sweep统一驱动+Wilson CI+Fisher精确检验(本机gem5-fi真跑)"
git push
```

---

## Task 6: 部署器 deploy.py（工具+语料 → 设备池）

**Files:**
- Create: `tools/sdc_experiment/deploy.py`
- Modify: `tools/sdc_experiment/test_device_pool.py`（追加部署冒烟测试，可选）

**Interfaces:**
- Consumes: `DevicePool`/`Device`；本机工具源 `/usr/local/bin/{snap_tool,simple_fix_tool_main,reading_runner_main_nolibc,silifuzz_orchestrator_main}`（静态 ELF，F6）
- Produces: `deploy(device, corpus_local_dir: str, force: bool = False) -> dict`（返回每工具的部署结果 + 远端 `--version`/`--help` 探活输出）；CLI：`python3 tools/sdc_experiment/deploy.py --device remote:NAME [--corpus output/corpus_shard]`

部署内容与远端布局：
```
{tools_dir}/snap_tool, simple_fix_tool_main, reading_runner_main_nolibc, silifuzz_orchestrator_main   # chmod +x
{tools_dir}/../sdc_corpus/          # corpus 分片目录 (scp -r)
```
幂等：已存在且 `md5sum` 一致则跳过（除非 force）。

- [x] **Step 1: 实现 deploy.py**

```python
# tools/sdc_experiment/deploy.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""deploy.py — 把 silifuzz 静态工具 + corpus 部署到设备池设备。

静态链接 ELF aarch64 → 拷贝即运行 (F6)。幂等: md5 一致跳过。
"""
import argparse, os, sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

LOCAL_TOOL_SRC = "/usr/local/bin"
TOOLS = ["snap_tool", "simple_fix_tool_main",
         "reading_runner_main_nolibc", "silifuzz_orchestrator_main"]

def deploy(device, corpus_local_dir: str = None, force: bool = False) -> dict:
    res = {"device": device.name, "tools": {}, "corpus": None}
    device.run(f"mkdir -p {device.tools_dir}")
    for t in TOOLS:
        src = os.path.join(LOCAL_TOOL_SRC, t)
        dst = device.tool_path(t)
        _, remote_md5 = device.run(f"md5sum {dst} 2>/dev/null | awk '{{print $1}}'", timeout=30)
        import hashlib
        local_md5 = hashlib.md5(open(src, "rb").read()).hexdigest()
        if not force and remote_md5.strip() == local_md5:
            res["tools"][t] = "skip(md5 match)"
            continue
        ok = device.put(src, dst)
        if ok:
            device.run(f"chmod +x {dst}")
            rc, out = device.run(f"{dst} --help 2>&1 | head -2", timeout=30)
            res["tools"][t] = "deployed" if rc in (0, 1) else f"BAD(rc={rc})"
        else:
            res["tools"][t] = "FAILED(put)"
    if corpus_local_dir:
        remote_corpus = os.path.join(os.path.dirname(device.tools_dir.rstrip("/")), "sdc_corpus")
        device.run(f"mkdir -p {remote_corpus}")
        ok = device.put(corpus_local_dir, remote_corpus)   # 目录级 scp -r
        res["corpus"] = {"remote": remote_corpus, "ok": bool(ok)}
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="remote:NAME | local")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.device == "local":
        from tools.sdc_experiment.devices.local_device import LocalDevice
        dev = LocalDevice()
    else:
        from tools.sdc_experiment.devices.device_pool import DevicePool
        dev = DevicePool().load().get(a.device.split(":", 1)[1])
    print(deploy(dev, a.corpus, a.force))

if __name__ == "__main__":
    main()
```

> 注意：`RemoteDevice.put` 目前基于 `ssh_lib.scp`（单文件）。目录级上传需要 `ssh_lib.scp_dir`——在 `remote_device.py` 的 `put` 里检测 `os.path.isdir(local)` 时改调 `scp_dir`，或 `deploy` 对 corpus 目录逐文件部署。实现时二选一并保持 `put()` 语义一致（含测试）。

- [x] **Step 2: 本机 local 冒烟**

Run: `python3 tools/sdc_experiment/deploy.py --device local`
Expected: `{'device': 'local-0103', 'tools': {4 个 'skip(md5 match)' 或 'deployed'}, 'corpus': None}`（local 时 tools_dir 建议用 `/tmp/sdc_experiment/tools` 副本而非写 /usr/local/bin——`LocalDevice.__init__` 增加 `tools_dir` 参数，默认 `/usr/local/bin`，deploy local 时传临时目录，验证拷贝+chmod+执行链路）

- [x] **Step 3: 0101 真机部署验证**

Run: `python3 tools/sdc_experiment/deploy.py --device remote:0101`
Expected: 4 个工具 deployed，`--help` 探活成功（0101 已有 `/sdc_tools` 历史部署，md5 一致时应 skip）

- [x] **Step 4: Commit**

```bash
git add tools/sdc_experiment/deploy.py tools/sdc_experiment/devices/
git commit -m "feat(experiment): deploy.py——静态工具+corpus 幂等部署到设备池(md5校验+探活)"
git push
```

---

## Task 7: 真机扫描驱动 hw_scan（E3 核心）

**Files:**
- Create: `tools/sdc_experiment/hw_scan.py`
- Create: `scripts/experiments/exp03_corpus_hw_local.sh`

**Interfaces:**
- Consumes: `Device`（`run/put/get/tool_path`）；`ExperimentConfig`（max_cpus/scan_duration_s）；日志解析逻辑移植自 `scripts/collect_results.py::parse_log`（正则保持逐字符一致）
- Produces: `parse_log(text: str) -> dict`（键：`sigsegv_noise, sigterm, runaway_noise, misbehave_noise, sdc_hits, sdc_details, total_failed, iterations`）；`hw_scan(device, corpus_remote: str, duration_s: int, max_cpus: int, stress: bool = False) -> dict`（在设备上后台起 orchestrator + 可选 stress-ng，等待 duration，拉回 scan.log，返回 parse_log 结果 + 语料元数据）；CLI：`python3 tools/sdc_experiment/hw_scan.py --device local|remote:NAME --corpus DIR --duration 1800 --max-cpus 8 [--stress]`

扫描命令模板（与 `distributed_scan.py` 已验证行为一致）：
```
{orchestrator} --runner={runner} --corpus_path={corpus} --max_cpus={N} \
  --duration={duration}s --per_runner_cpu_time_budget=10s \
  > {work}/scan.log 2>&1
```
（实现时打开 `distributed_scan.py` 核对其真实 flag 组合——含 `--shard_list_file`/`--corpus_metadata_file` 的用法——并沿用；上面模板仅示意。）

- [x] **Step 1: 写 parse_log 失败测试（用真实历史日志做 fixture）**

```python
# tools/sdc_experiment/test_hw_scan.py
#!/usr/bin/env python3
"""hw_scan.parse_log 单元测试。运行: python3 tools/sdc_experiment/test_hw_scan.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.hw_scan import parse_log

FAKE_LOG = """Snapshot [abc123] failed, outcome = 2
Snapshot [def456] failed, outcome = 5
Snapshot [789abc] failed, outcome = 3
Received signal SIGSEGV while outside of snap
Received signal SIGSEGV while outside of snap
SIGTERM received
Snapshot [aaa111] failed, outcome = 6
"""

def test_parse_log():
    r = parse_log(FAKE_LOG)
    assert r["sdc_hits"] == 2, f"outcome 2/3 是 SDC, got {r['sdc_hits']}"
    assert r["runaway_noise"] == 1
    assert r["misbehave_noise"] == 1
    assert r["sigsegv_noise"] == 2
    assert r["sigterm"] >= 1
    assert len(r["sdc_details"]) == 2
    print(f"PASS test_parse_log: {r}")

def test_parse_real_log_if_exists():
    p = "output/distributed/logs/0103.scan.log"
    if not os.path.exists(p):
        print("SKIP test_parse_real_log: 无历史日志")
        return
    r = parse_log(open(p, errors="replace").read())
    print(f"PASS test_parse_real_log (历史真实日志): sdc={r['sdc_hits']}, "
          f"noise(segv={r['sigsegv_noise']},runaway={r['runaway_noise']},"
          f"misbehave={r['misbehave_noise']})")

if __name__ == "__main__":
    test_parse_log(); test_parse_real_log_if_exists()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_hw_scan.py`
Expected: FAIL — `ImportError: hw_scan`

- [x] **Step 3: 实现 hw_scan.py**

```python
# tools/sdc_experiment/hw_scan.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_scan.py — 真机 SDC 扫描驱动 (E3/E4 核心)。

对设备(本机/远程)跑 orchestrator 扫描 corpus, 拉回日志, 用与
scripts/collect_results.py 完全一致的解析规则分类:
  真SDC = outcome 2/3/4; 噪声 = outcome 5/6 + SIGSEGV-outside-snap + SIGTERM。
"""
import argparse, json, os, re, sys, time

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

def parse_log(text: str) -> dict:
    """与 scripts/collect_results.py::parse_log 逐字符一致的解析 (移植)。"""
    sigsegv_outside = len(re.findall(r'SIGSEGV while outside of snap', text))
    sigterm = len(re.findall(r'SIGTERM', text))
    all_failed = re.findall(r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = (\d+)', text)
    sdc_outcomes = [o for o in all_failed if o in ('2', '3', '4')]
    runaway = sum(1 for o in all_failed if o == '5')
    misbehave = sum(1 for o in all_failed if o == '6')
    sdc_details = re.findall(r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = [234]', text)[:10]
    return {"sigsegv_noise": sigsegv_outside, "sigterm": sigterm,
            "runaway_noise": runaway, "misbehave_noise": misbehave,
            "sdc_hits": len(sdc_outcomes), "sdc_details": sdc_details,
            "total_failed": len(all_failed)}

def hw_scan(device, corpus_remote: str, duration_s: int, max_cpus: int,
            stress: bool = False) -> dict:
    """在 device 上跑 orchestrator 扫描, 返回解析结果。"""
    orch = device.tool_path("silifuzz_orchestrator_main")
    runner = device.tool_path("reading_runner_main_nolibc")
    work = f"/tmp/sdc_scan_{int(time.time())}"
    device.run(f"mkdir -p {work}")
    # 注意: 实现时核对 distributed_scan.py 的真实 flag 组合并沿用 (shard_list_file 等)
    cmd = (f"{orch} --runner={runner} --corpus_path={corpus_remote} "
           f"--max_cpus={max_cpus} --duration={duration_s}s "
           f"--per_runner_cpu_time_budget=10s > {work}/scan.log 2>&1")
    if stress:
        device.run("command -v stress-ng >/dev/null && "
                   f"(stress-ng --cpu {max_cpus} --timeout {duration_s}s "
                   f"> {work}/stress.log 2>&1 &) || true")
    device.run(cmd, timeout=duration_s + 600)
    rc, log = device.run(f"cat {work}/scan.log", timeout=120)
    parsed = parse_log(log)
    parsed["scan_work_dir"] = work
    parsed["device"] = device.name
    parsed["max_cpus"] = max_cpus
    parsed["duration_s"] = duration_s
    parsed["corpus"] = corpus_remote
    # 拉回日志存档 (local: 直接拷; remote: scp)
    os.makedirs("output/experiments/hw_scan_logs", exist_ok=True)
    local_log = f"output/experiments/hw_scan_logs/{device.name}_{int(time.time())}.scan.log"
    device.get(f"{work}/scan.log", local_log)
    parsed["archived_log"] = local_log
    return parsed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--duration", type=int, default=1800)
    ap.add_argument("--max-cpus", type=int, default=8)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--exp", default="exp03")
    a = ap.parse_args()
    from tools.sdc_experiment.experiment_config import default_config
    from tools.sdc_experiment.devices.device_pool import DevicePool
    from tools.sdc_experiment.devices.local_device import LocalDevice
    cfg = default_config(a.exp)
    dev = (LocalDevice() if a.device == "local"
           else DevicePool().load().get(a.device.split(":", 1)[1]))
    assert a.max_cpus <= cfg.max_cpus, "超出 MCE 红线"
    res = hw_scan(dev, a.corpus, a.duration, a.max_cpus, a.stress)
    os.makedirs(cfg.out_dir, exist_ok=True)
    out = cfg.out_dir / f"hw_{dev.name}.json"
    json.dump(res, open(out, "w"), indent=2, ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

- [x] **Step 4: 运行 parse_log 测试确认通过**

Run: `python3 tools/sdc_experiment/test_hw_scan.py`
Expected: `PASS test_parse_log` + 历史 SKIP 或 PASS + `ALL PASS`

- [x] **Step 5: E3 实验脚本（本机真机验证）**

```bash
#!/bin/bash
# scripts/experiments/exp03_corpus_hw_local.sh — E3: 19模板语料在本机(0103)真机验证
# 前置: output/corpus_19tpl/ 存在 (由 seeds/bin/*.bin 经 snap_tool make + generate_corpus 生成,
#       生成步骤内联在本脚本, 管线依据 memory sdc-snapshot-from-raw-insns-pipeline)
# 判定: 扫描完成无 crash; SDC=0(健康硅片预期) 或 SDC 命中有 hash 证据; 噪声全分类
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp03-corpus-hw-local
mkdir -p output/experiments/$EXP/pb

# 1. 19 模板 .bin → snapshot .pb (真实命令, F2 管线)
for BIN in seeds/bin/*.bin; do
  NAME=$(basename "$BIN" .bin)
  /usr/local/bin/snap_tool --raw --runner=/usr/local/bin/reading_runner_main_nolibc \
      --out=output/experiments/$EXP/pb/$NAME.pb make "$BIN"
done

# 2. snapshot → relocatable corpus
/usr/local/bin/snap_tool --target_platform=arm-neoverse-n1 \
    generate_corpus output/experiments/$EXP/pb/*.pb --output=output/experiments/$EXP/corpus

# 3. 本机真机扫描 30min, max_cpus=8 起步 (MCE 红线)
python3 tools/sdc_experiment/hw_scan.py --device local \
    --corpus output/experiments/$EXP/corpus --duration 1800 --max-cpus 8 --exp $EXP

# 4. 汇总判定
python3 - "$EXP" <<'EOF'
import json, sys, glob
exp = sys.argv[1]
f = sorted(glob.glob(f"output/experiments/{exp}/hw_local-0103.json"))[-1]
r = json.load(open(f))
ok = True
if r.get("sdc_hits", 0) > 0:
    print(f"!!! SDC 命中 {r['sdc_hits']} 个: {r['sdc_details']} — 需逐个 hash 复查 (复跑确认非偶发)")
ok = ok and (r["sdc_hits"] + r["runaway_noise"] + r["misbehave_noise"] + r["sigsegv_noise"]) == r["total_failed"] + r["sigsegv_noise"]
summary = {"result": r, "noise_fully_classified": ok,
           "verdict": "HW_SCAN_OK" if ok else "CLASSIFICATION_INCOMPLETE"}
json.dump(summary, open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(summary, ensure_ascii=False, indent=2))
EOF
```

> **实现时必须核对的两个点**：(1) `snap_tool make` 的 `--out` 与 `generate_corpus --output` 的真实 flag 名（跑 `/usr/local/bin/snap_tool` 无参看 usage，实测为准）；(2) corpus 目录的产物形态（是否为 `corpus.00000` 分片 + metadata 文件，若是则 hw_scan 的 orchestrator flag 要用 `--shard_list_file`/`--corpus_metadata_file` 形式，参照 `distributed_scan.py`）。**语料生成先单测一个模板再全量**。

- [x] **Step 6: 单模板管线冒烟（先 1 个再全量）**

```bash
/usr/local/bin/snap_tool --raw --runner=/usr/local/bin/reading_runner_main_nolibc \
    --out=/tmp/e1_carry_chain.pb make seeds/bin/e1_carry_chain.bin
/usr/local/bin/reading_runner_main_nolibc /tmp/e1_carry_chain.pb || true
# runner 直接跑单 snapshot; 输出 execution_result code:1 = OK
```
Expected: snapshot 生成 + runner 回放 `code: 1`（OK）

- [x] **Step 7: 运行 E3（真跑，约 35min）**

Run: `bash scripts/experiments/exp03_corpus_hw_local.sh`
Expected: `summary.json` 的 `verdict: HW_SCAN_OK`；若 SDC 命中则先复查再下结论

- [x] **Step 8: Commit**

```bash
git add tools/sdc_experiment/hw_scan.py tools/sdc_experiment/test_hw_scan.py \
        scripts/experiments/exp03_corpus_hw_local.sh output/experiments/exp03-corpus-hw-local/
git commit -m "feat(experiment): E3语料真机本机验证——19模板管线重建+orchestrator扫描+噪声全分类"
git push
```

---

## Task 8: 远程设备全链路实验 E4（注册→部署→扫描→回收→反馈）

**Files:**
- Create: `scripts/experiments/exp04_remote_device.sh`

**Interfaces:**
- Consumes: Task 4 的 `register_device.py`、Task 6 的 `deploy.py`、Task 7 的 `hw_scan.py`
- Produces: `exp04_remote_device.sh`——参数化的远程设备验证模板（`--host --port --user --password-env --name --duration --max-cpus`），执行：注册→探活→部署→推语料→远程扫描→回收结果→汇总。

- [x] **Step 1: 写 E4 脚本**

```bash
#!/bin/bash
# scripts/experiments/exp04_remote_device.sh — E4: 远程设备全链路验证
# 用法: bash exp04_remote_device.sh --name board-X --host <IP> --port 22 \
#         --user root --password-env SDC_PASSWORD --duration 1800 --max-cpus 8
# 全链路: 注册→probe→deploy→corpus推送→hw_scan→结果回收→summary
set -euo pipefail
cd "$(dirname "$0")/../.."

NAME="" HOST="" PORT=22 USER=root PWENV=SDC_PASSWORD DUR=1800 CPUS=8
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --user) USER="$2"; shift 2;;
    --password-env) PWENV="$2"; shift 2;;
    --duration) DUR="$2"; shift 2;;
    --max-cpus) CPUS="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done
[[ -z "$NAME" || -z "$HOST" ]] && { echo "need --name --host"; exit 1; }

EXP=exp04-remote-$NAME
mkdir -p output/experiments/$EXP

# 1. 注册 (幂等: 已注册会报错退出 → 忽略继续)
python3 scripts/register_device.py --name "$NAME" --host "$HOST" --port "$PORT" \
    --user "$USER" --password-env "$PWENV" || true

# 2. probe (必须在注册时已打印; 这里再取一次结构化结果)
python3 - "$NAME" <<'EOF'
import json, sys
sys.path.insert(0, ".")
from tools.sdc_experiment.devices.device_pool import DevicePool
pool = DevicePool().load()
p = pool.get(sys.argv[1]).probe()
json.dump(p, open(f"output/experiments/exp04-remote-{sys.argv[1]}/probe.json", "w"),
          indent=2, ensure_ascii=False)
assert p["reachable"], f"设备不可达: {p}"
print("probe OK:", p)
EOF

# 3. 部署工具 + 推送 E3 生成的语料
python3 tools/sdc_experiment/deploy.py --device "remote:$NAME" \
    --corpus output/experiments/exp03-corpus-hw-local/corpus

# 4. 远程扫描
python3 tools/sdc_experiment/hw_scan.py --device "remote:$NAME" \
    --corpus /sdc_corpus --duration "$DUR" --max-cpus "$CPUS" --exp "$EXP"

# 5. 汇总
python3 - "$NAME" "$EXP" <<'EOF'
import json, sys, glob
name, exp = sys.argv[1], sys.argv[2]
f = sorted(glob.glob(f"output/experiments/{exp}/hw_{name}*.json"))[-1]
r = json.load(open(f))
verdict = ("REMOTE_CHAIN_OK" if r["sdc_hits"] == 0 else
           f"REMOTE_SDC_{r['sdc_hits']}_RECHECK")
json.dump({"result": r, "verdict": verdict},
          open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps({"verdict": verdict, "sdc_details": r.get("sdc_details", [])},
                 ensure_ascii=False, indent=2))
EOF
```

- [x] **Step 2: 用 0101 做全链路演练（作为"用户设备"替身）**

Run: `SDC_PASSWORD=SDC@2026 bash scripts/experiments/exp04_remote_device.sh --name 0101 --host 172.168.177.97 --duration 600 --max-cpus 8`
Expected: `verdict: REMOTE_CHAIN_OK`（10 分钟短扫描验证全链路；正式用户设备由用户提供凭据后同一脚本运行）

实际 (2026/09/02, commit 749b885): verdict=REMOTE_CHAIN_OK — probe specs_ok (126核/29GB/aarch64), 5工具 skip(md5 match), E3语料 md5 往返一致+回放 code:1, orch_rc=0, play_count=1281, sdc=0, v1交叉校验 match。密码从 output/devices/devices.json 读入环境变量 (凭据红线: 不落命令行历史以外的日志)。勘误: 语料须传远端文件 /sdc_corpus/corpus 而非目录 /sdc_corpus (0101 上有历史语料, 目录分支会全部扫入)。

- [ ] **Step 3: 用户设备正式运行（需用户先提供凭据）** *(待用户提供凭据 — 脚本已参数化就绪)*

向用户请求：设备 IP、SSH 端口、用户名、密码（或密码环境变量名）。然后：
```bash
export SDC_PASSWORD='<用户密码>'
bash scripts/experiments/exp04_remote_device.sh --name <用户设备名> --host <IP> --port <端口> \
    --user <用户名> --duration 1800 --max-cpus 8
```
Expected: `REMOTE_CHAIN_OK`；任何环节失败则按 probe/deploy/scan 分层排障后重试

- [x] **Step 4: Commit**

```bash
git add scripts/experiments/exp04_remote_device.sh output/experiments/exp04-*/
git commit -m "feat(experiment): E4远程设备全链路——注册→部署→扫描→回收→汇总, 参数化用户凭据"
git push
```

实际: commit 749b885 (脚本 + exp04-remote-0101 五件证据 force-add, devices.json 不入库), 已 push 到 feat/sdc-experiment-verification。

---

## Task 9: 跨层关联 correlation.py + E5

**Files:**
- Create: `tools/sdc_experiment/correlation.py`
- Create: `tools/sdc_experiment/test_correlation.py`
- Create: `scripts/experiments/exp05_crosslayer.sh`

**Interfaces:**
- Consumes: E2 的 `output/experiments/exp02-d13-vs-random/sim_*.json`（或手工整理的 ≥10 用例组 sim 指标表）；E3/E4 的 `hw_*.json`
- Produces: `pearson(xs, ys) -> (r, p_tapprox)`；`spearman(xs, ys) -> (rho, p)`；`permutation_test(xs, ys, n=10000, seed=42) -> p_value`（独立性置换检验，主检验）；`analyze(sim_rows, hw_rows) -> dict`（输入每组一行 `{group, sim_diverge_rate, sim_masked_rate, ...}` 与 `{group, hw_runnable_rate, hw_runaway_rate, hw_misbehave_rate, ...}`，输出相关系数 + 置换 p + 结论）

**关联设计（诚实弱化版，见实验总表 E5 说明）**：
- 样本单元 = 用例组（19 模板 + A/B/C/D/D13 等共 ≥10 组）。
- Sim 侧自变量：每组在 gem5 的 clean_diverge 率、masked 率（E2 已产 D13/B，其余组用 `sim_sweep.py --group` 扩展跑或引用 F3/F4 已有数据 + 新跑补齐）。
- HW 侧因变量：每组语料真机 runnable 率（1 − 失败率）、runaway 率、misbehave 率（E3 语料级 + 需要按组扫描——hw_scan 按组各跑一次短扫描 10min/组，orchestrator `--corpus_path` 指向单组语料目录）。
- 检验：Spearman ρ + 置换检验 p<0.05 判"显著相关"；样本 <10 组时诚实输出"样本不足"。

- [x] **Step 1: 写失败测试**

```python
# tools/sdc_experiment/test_correlation.py
#!/usr/bin/env python3
"""correlation 纯函数测试。运行: python3 tools/sdc_experiment/test_correlation.py"""
import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.correlation import pearson, spearman, permutation_test, analyze

def test_pearson():
    xs = [1, 2, 3, 4, 5]
    r, _ = pearson(xs, [2, 4, 6, 8, 10])
    assert abs(r - 1.0) < 1e-9
    r2, _ = pearson(xs, [10, 8, 6, 4, 2])
    assert abs(r2 + 1.0) < 1e-9
    print("PASS test_pearson")

def test_spearman():
    # 单调非线性 → spearman=1, pearson<1
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 25]
    rho, _ = spearman(xs, ys)
    assert abs(rho - 1.0) < 1e-9
    print("PASS test_spearman")

def test_permutation():
    rng = random.Random(7)
    xs = list(range(20))
    ys_strong = [x * 2 + rng.random() * 0.1 for x in xs]     # 强相关
    ys_none = [rng.random() for _ in xs]                     # 无相关
    p1 = permutation_test(xs, ys_strong, n=2000, seed=42)
    p2 = permutation_test(xs, ys_none, n=2000, seed=42)
    assert p1 < 0.01, f"强相关应 p<0.01, got {p1}"
    assert p2 > 0.05, f"无相关应 p>0.05, got {p2}"
    print(f"PASS test_permutation: p_strong={p1:.4f}, p_none={p2:.3f}")

def test_analyze():
    sim = [{"group": f"g{i}", "sim_diverge_rate": i / 10} for i in range(10)]
    hw = [{"group": f"g{i}", "hw_runaway_rate": 0.5 - i / 20} for i in range(10)]
    r = analyze(sim, hw, sim_key="sim_diverge_rate", hw_key="hw_runaway_rate")
    assert r["n"] == 10
    assert r["spearman_rho"] < -0.9   # 完美负相关
    assert r["permutation_p"] < 0.05
    print("PASS test_analyze")

if __name__ == "__main__":
    test_pearson(); test_spearman(); test_permutation(); test_analyze()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_correlation.py`
Expected: FAIL — `ImportError: correlation`

- [x] **Step 3: 实现 correlation.py**

```python
# tools/sdc_experiment/correlation.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""correlation.py — 跨层 (Sim→HW) 统计关联分析 (E5)。

诚实定位: 健康硅片上真 SDC 稀少, 无法直接关联"仿真 diverge 率 vs 真机 SDC 率"。
本模块关联的是用例组粒度的执行健康度: 仿真侧 (clean_diverge/masked 率)
vs 真机侧 (runnable/runaway/misbehave 率)。主检验 = Spearman + 独立性置换检验。
"""
import math, random

def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks

def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return (float("nan"), float("nan"))
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return (float("nan"), float("nan"))
    r = sxy / math.sqrt(sxx * syy)
    # t 近似 p (n>=10 时可用; 报告同时给置换检验 p)
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return (r, t)

def spearman(xs, ys):
    rx, ry = _rank(xs), _rank(ys)
    return pearson(rx, ry)

def permutation_test(xs, ys, n: int = 10000, seed: int = 42):
    """独立性置换检验: 打乱 ys, 统计 |perm_corr| >= |obs_corr| 的比例。"""
    if len(xs) < 3:
        return float("nan")
    obs, _ = spearman(xs, ys)
    if math.isnan(obs):
        return float("nan")
    rng = random.Random(seed)
    ys2 = list(ys)
    extreme = 0
    for _ in range(n):
        rng.shuffle(ys2)
        r, _ = spearman(xs, ys2)
        if not math.isnan(r) and abs(r) >= abs(obs) - 1e-12:
            extreme += 1
    return (extreme + 1) / (n + 1)

def analyze(sim_rows, hw_rows, sim_key="sim_diverge_rate", hw_key="hw_runaway_rate",
            n_perm=10000):
    by_group_h = {r["group"]: r for r in hw_rows}
    pairs = [(r[sim_key], by_group_h[r["group"]][hw_key])
             for r in sim_rows if r["group"] in by_group_h]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if len(pairs) < 10:
        return {"n": len(pairs), "verdict": "INSUFFICIENT_SAMPLES(<10, 诚实记录)",
                "note": "用例组不足 10, 不做显著性声明"}
    rho, t = spearman(xs, ys)
    p = permutation_test(xs, ys, n=n_perm)
    verdict = ("SIGNIFICANT" if p < 0.05 else "NOT_SIGNIFICANT(诚实记录)")
    return {"n": len(pairs), "sim_key": sim_key, "hw_key": hw_key,
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else None,
            "permutation_p": round(p, 5), "verdict": verdict,
            "note": "组粒度执行健康度关联; gem5 O3 ≠ TSV110 RTL; 真SDC关联需检出样本后再做"}
```

- [x] **Step 4: 运行测试确认通过**

Run: `python3 tools/sdc_experiment/test_correlation.py`
Expected: 4 个 PASS + `ALL PASS`

- [x] **Step 5: E5 实验脚本（按组双面扫描）**

```bash
#!/bin/bash
# scripts/experiments/exp05_crosslayer.sh — E5: Sim→HW 组粒度关联
# Sim面: 对每个用例组跑 gem5 sweep (bit, 30次/组, 快速估计) — 复用 sim_sweep (本机 gem5)
# HW面: 对每组语料单独跑 10min 本机扫描 — 复用 hw_scan
# 关联: Spearman + 置换检验 (≥10 组)
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP=exp05-crosslayer
mkdir -p output/experiments/$EXP

# 组清单: 19 模板中选 12 个代表 + A/B/D13 (gem5 组用本机 gem5_config/workloads)
# 诚实边界: gem5 workload 覆盖 A/B/D13 (入仓); 19模板的 .bin 无法直接进 gem5
#   (gem5 跑 ELF, 模板是裸指令) → sim 面对模板组用"Unicorn T(di/dt) 值"作代理指标,
#   在报告中明确该代理性质。
python3 - "$EXP" <<'EOF'
import json, os, subprocess, sys
sys.path.insert(0, ".")
exp = sys.argv[1]

# ---- Sim 面: A/B/D13 各 30 次 bit-flip (本机 gem5) ----
from tools.sdc_experiment.experiment_config import default_config
from tools.sdc_experiment.sim_sweep import run_group
cfg = default_config(exp)
sim_rows = []
for grp in ["A", "B", "D13"]:
    r = run_group(grp, "bit", 30, seed=7, cfg=cfg)
    sim_rows.append({"group": grp, "sim_diverge_rate": r["diverge_rate"],
                     "sim_masked_rate": round(r["masked"] / max(1, r["n"]), 4)})
    print("sim:", sim_rows[-1])

# ---- Sim 面: 19 模板 Unicorn T 值 (进化引擎代理指标, 报告注明) ----
sys.path.insert(0, "tools/sdc_mutator")
from evolution_engine import EvolutionEngine
import glob
for b in sorted(glob.glob("seeds/bin/*.bin"))[:12]:
    code = open(b, "rb").read()[:256]
    try:
        eng = EvolutionEngine(code)
        _, T, M, E, _ = eng.run_once({i: 0x1234567890ABCDEF for i in range(5)})
        sim_rows.append({"group": os.path.basename(b)[:-4],
                         "sim_diverge_rate": round(T / 200, 4),   # 归一化代理
                         "sim_masked_rate": 0.0, "proxy": "unicorn_T"})
    except Exception as e:
        print(f"skip {b}: {e}")

# ---- HW 面: 每组单独 10min 本机扫描 ----
from tools.sdc_experiment.devices.local_device import LocalDevice
from tools.sdc_experiment.hw_scan import hw_scan
local = LocalDevice()
hw_rows = []
for b in sorted(glob.glob("seeds/bin/*.bin"))[:12]:
    name = os.path.basename(b)[:-4]
    pb = f"/tmp/sdc_experiment/e5/{name}.pb"
    os.makedirs("/tmp/sdc_experiment/e5", exist_ok=True)
    subprocess.run(["/usr/local/bin/snap_tool", "--raw",
                    "--runner=/usr/local/bin/reading_runner_main_nolibc",
                    f"--out={pb}", "make", b], check=True)
    r = hw_scan(local, pb, duration_s=600, max_cpus=8)
    hw_rows.append({"group": name, "hw_runaway_rate": r["runaway_noise"] / 600,
                    "hw_misbehave_rate": r["misbehave_noise"] / 600,
                    "hw_sdc": r["sdc_hits"]})
    print("hw:", hw_rows[-1])
    json.dump(hw_rows, open(f"output/experiments/{exp}/hw_rows.json", "w"))

# ---- 关联 ----
from tools.sdc_experiment.correlation import analyze
res = analyze(sim_rows, hw_rows)
json.dump({"sim_rows": sim_rows, "hw_rows": hw_rows, "analysis": res},
          open(f"output/experiments/{exp}/summary.json", "w"),
          indent=2, ensure_ascii=False)
print(json.dumps(res, ensure_ascii=False, indent=2))
EOF
```

> **诚实边界（写入报告）**：Sim 面的 19 模板指标是 **Unicorn T(di/dt) 代理**（gem5 跑不了裸指令 bin），A/B/D13 是真 gem5 diverge 率；HW 面只有模板组（A/B/D13 是 gem5 ELF workload，不是 snapshot 语料）。因此 E5 的关联是"Unicorn 代理指标 + 部分 gem5 真指标 → 真机健康度"的**混合关联**，结论措辞必须反映这一点。若分析判定 INSUFFICIENT_SAMPLES 或 NOT_SIGNIFICANT，如实记录。

- [x] **Step 6: 运行 E5（真跑，12 组 × 10min ≈ 2.5h + sim sweep 90 run ≈ 1.5h，全本机）**

Run: `nohup bash scripts/experiments/exp05_crosslayer.sh > output/experiments/exp05.log 2>&1 &`
Expected: `summary.json` 生成，`analysis.verdict` ∈ {SIGNIFICANT, NOT_SIGNIFICANT, INSUFFICIENT_SAMPLES}，如实记录

- [x] **Step 7: Commit**

```bash
git add tools/sdc_experiment/correlation.py tools/sdc_experiment/test_correlation.py \
        scripts/experiments/exp05_crosslayer.sh output/experiments/exp05-crosslayer/
git commit -m "feat(experiment): E5跨层Sim→HW关联——Spearman+置换检验, 组粒度健康度关联(诚实弱化版)"
git push
```

---

## Task 10: 反馈迭代闭环（E4 延伸：真机结果→用例生成优化）

**Files:**
- Create: `tools/sdc_experiment/feedback.py`
- Modify: `scripts/sdc_evolve.sh` 不动（已存在），新建 `scripts/experiments/feedback_loop.sh` 编排

**Interfaces:**
- Consumes: E3/E4 的 `hw_*.json`（sdc_details 含 snapshot hash）；`snap_tool get_instructions`；`tools/sdc_mutator/evolution_engine.py` 与 `scripts/run_guided_mutation.sh`（已存在，只调用）
- Produces: `extract_hits(exp_dir) -> list[dict]`（从实验输出提取 SDC 命中 hash + outcome + 对应指令）；`build_feedback_report(hits, corpus_dir) -> dict`（每命中一条：hash、outcome、指令文本、处置建议 `replay-confirm`（复跑确认）/`quarantine`（隔离复测））；CLI：`python3 tools/sdc_experiment/feedback.py --exp-dir output/experiments/exp03-... --corpus ...`

**闭环流程**（与 `sdc_evolve.sh` 已验证的语义一致，移植到设备池）：
1. `extract_hits` 扫描 `output/experiments/*/hw_*.json` 的 `sdc_hits>0`；
2. 对每个命中 hash：`snap_tool get_instructions <corpus 文件> --hash <hash>` 提取指令（需核对真实 flag 形式，先 `snap_tool` 无参看 usage）；
3. 产出 `output/experiments/feedback/hits.json`：每条含指令文本 + 处置建议；
4. `replay-confirm`：把该 snapshot 单独喂 runner 复跑 ≥3 次确认可复现（不可复现 → 标 `transient`，不计入 SDC 结论）；
5. 确认的命中回灌 `seeds/evolved/` 高权重，调用 `run_guided_mutation.sh` 局部变异放大 → 重新部署扫描（迭代闭环）。

- [x] **Step 1: 写失败测试**

```python
# tools/sdc_experiment/test_feedback.py
#!/usr/bin/env python3
"""feedback 单元测试。运行: python3 tools/sdc_experiment/test_feedback.py"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.feedback import extract_hits, build_feedback_report

def test_extract_hits():
    with tempfile.TemporaryDirectory() as d:
        json.dump({"sdc_hits": 2, "sdc_details": [
            "Snapshot [abc123] failed, outcome = 2",
            "Snapshot [def456] failed, outcome = 3"]},
            open(os.path.join(d, "hw_local-0103.json"), "w"))
        hits = extract_hits(d)
        assert len(hits) == 1          # 一个实验文件, 2 条命中
        assert hits[0]["count"] == 2
        assert hits[0]["hashes"] == ["abc123", "def456"]
        assert hits[0]["outcomes"] == [2, 3]
        print("PASS test_extract_hits")

def test_build_report():
    with tempfile.TemporaryDirectory() as d:
        json.dump({"sdc_hits": 1, "sdc_details": [
            "Snapshot [abc123] failed, outcome = 2"]},
            open(os.path.join(d, "hw_x.json"), "w"))
        hits = extract_hits(d)
        rep = build_feedback_report(hits, corpus_dir="/nonexistent")
        assert rep["total_hits"] == 1
        assert rep["items"][0]["action"] in ("replay-confirm", "quarantine")
        print("PASS test_build_report")

if __name__ == "__main__":
    test_extract_hits(); test_build_report()
    print("ALL PASS")
```

- [x] **Step 2: 运行确认失败**

Run: `python3 tools/sdc_experiment/test_feedback.py`
Expected: FAIL — `ImportError: feedback`

- [x] **Step 3: 实现 feedback.py**

```python
# tools/sdc_experiment/feedback.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""feedback.py — 真机结果→用例生成 反馈闭环 (E4 延伸)。

从 hw_scan 实验输出提取 SDC 命中 (hash+outcome), 生成处置报告:
  replay-confirm: 单 snapshot 复跑≥3次, 可复现才计入 SDC 结论
  quarantine:     复现失败 → 标 transient, 不计入
确认命中回灌 seeds/evolved/ → run_guided_mutation.sh 变异放大 → 再部署扫描。
(语义与 scripts/sdc_evolve.sh 一致, 移植到实验框架。)
"""
import argparse, glob, json, os, re, subprocess

def extract_hits(exp_dir: str) -> list:
    hits = []
    for f in sorted(glob.glob(os.path.join(exp_dir, "hw_*.json"))):
        r = json.load(open(f))
        if r.get("sdc_hits", 0) > 0:
            hashes = re.findall(r"Snapshot \[([0-9a-f]+)\]", "\n".join(r["sdc_details"]))
            outcomes = [int(o) for o in
                        re.findall(r"outcome = (\d+)", "\n".join(r["sdc_details"]))]
            hits.append({"file": f, "device": r.get("device"),
                         "count": r["sdc_hits"], "hashes": hashes, "outcomes": outcomes})
    return hits

def build_feedback_report(hits: list, corpus_dir: str) -> dict:
    items = []
    for h in hits:
        for hash_, outcome in zip(h["hashes"], h["outcomes"]):
            items.append({"hash": hash_, "outcome": outcome, "device": h["device"],
                          "source": h["file"],
                          "action": "replay-confirm",
                          "note": "复跑≥3次可复现才计入SDC; 否则标transient隔离"})
    return {"total_hits": len(items), "items": items,
            "corpus_dir": corpus_dir,
            "next_step": "确认命中→回灌seeds/evolved/→run_guided_mutation.sh→再扫描"}

def replay_confirm(pb_file: str, runner: str = "/usr/local/bin/reading_runner_main_nolibc",
                   n: int = 3) -> dict:
    """单 snapshot 复跑 n 次确认可复现。"""
    repro = 0
    for _ in range(n):
        p = subprocess.run([runner, pb_file], capture_output=True, text=True, timeout=120)
        # execution_result code:1 = OK; mismatch 输出含 failed/outcome
        if "failed" in (p.stdout + p.stderr) or "mismatch" in (p.stdout + p.stderr).lower():
            repro += 1
    return {"pb": pb_file, "runs": n, "reproduced": repro,
            "confirmed": repro == n, "verdict": "SDC_CONFIRMED" if repro == n
            else ("TRANSIENT" if repro > 0 else "NOT_REPRODUCED")}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--corpus", required=True)
    a = ap.parse_args()
    hits = extract_hits(a.exp_dir)
    rep = build_feedback_report(hits, a.corpus)
    os.makedirs("output/experiments/feedback", exist_ok=True)
    json.dump(rep, open("output/experiments/feedback/hits.json", "w"),
              indent=2, ensure_ascii=False)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if not hits:
        print("无 SDC 命中 (健康硅片预期) — 反馈闭环空转, 无需迭代")

if __name__ == "__main__":
    main()
```

- [x] **Step 4: 运行测试确认通过**

Run: `python3 tools/sdc_experiment/test_feedback.py`
Expected: 2 个 PASS + `ALL PASS`

- [x] **Step 5: 编排脚本 feedback_loop.sh**

```bash
#!/bin/bash
# scripts/experiments/feedback_loop.sh — 反馈迭代闭环编排
# 用法: bash feedback_loop.sh <exp_dir> <corpus_dir>
set -euo pipefail
cd "$(dirname "$0")/../.."
EXP_DIR="${1:?需要实验目录}"; CORPUS="${2:?需要语料目录}"

python3 tools/sdc_experiment/feedback.py --exp-dir "$EXP_DIR" --corpus "$CORPUS"

# 有确认命中时: 回灌 + 变异放大 + 再扫描 (sdc_evolve.sh 语义, 编排到本框架)
if python3 -c "
import json,sys
rep=json.load(open('output/experiments/feedback/hits.json'))
sys.exit(0 if rep['total_hits']>0 else 1)
"; then
  echo "=== 有 ${?} 个命中, 进入回灌-变异-再扫描迭代 ==="
  # 1. 提取命中指令回灌 seeds/evolved/ (sdc_evolve.sh 已实现该逻辑, 直接调用)
  bash scripts/sdc_evolve.sh --scan-only || true
  # 2. 变异放大
  bash scripts/run_guided_mutation.sh --all || true
  echo "=== 迭代后语料重新生成 corpus, 手动触发 exp04 重扫描 ==="
else
  echo "无命中, 闭环结束 (健康硅片预期)"
fi
```

- [x] **Step 6: 用 E3 输出空转验证（预期无命中）**

Run: `bash scripts/experiments/feedback_loop.sh output/experiments/exp03-corpus-hw-local output/experiments/exp03-corpus-hw-local/corpus`
Expected: `无 SDC 命中 (健康硅片预期) — 反馈闭环空转`（若 E3 真有命中，则走 replay-confirm 分支并输出复跑结果）

- [x] **Step 7: Commit**

```bash
git add tools/sdc_experiment/feedback.py tools/sdc_experiment/test_feedback.py \
        scripts/experiments/feedback_loop.sh
git commit -m "feat(experiment): 反馈迭代闭环——SDC命中提取/replay-confirm复跑确认/回灌变异编排"
git push
```

---

## Task 11: 汇总报告 report.py + E6

**Files:**
- Create: `tools/sdc_experiment/report.py`

**Interfaces:**
- Consumes: `output/experiments/*/summary.json` 与 `sim_*.json`/`hw_*.json`
- Produces: `python3 tools/sdc_experiment/report.py > docs/experiments/2026-09-02-sdcfuzz-verification-report.md`——单一 Markdown 报告，逐实验列：命令、原始数据、统计检验、verdict、诚实标注（gem5≠RTL / 代理指标 / 样本不足），末尾对照 scheme.md 声明逐条给"已验证/部分验证/未验证"结论表。

- [x] **Step 1: 实现 report.py**

```python
# tools/sdc_experiment/report.py
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""report.py — 汇总 output/experiments/ 全部实验 → 单一诚实报告。"""
import glob, json, os, datetime

SCHEME_CLAIMS = [
    ("§3.1 D13 bit-flip 3.00×", "E2 bit D13/B"),
    ("§3.1 D13 structural 7.79×", "E2 struct D13/B"),
    ("§4.2 真机执行能力 (Snapshot/Runner/Orchestrator)", "E3"),
    ("§4.3 L3 多板分布式 + 噪声分类", "E4"),
    ("§4.4 Sim→HW 统计关联", "E5 (弱化: 组粒度健康度关联)"),
    ("§4.2 进化引擎 (T 8.8×)", "F5 已有 + E5 Unicorn 代理"),
]

def main():
    lines = ["# sdcfuzz 实验验证报告",
             f"\n生成: {datetime.date.today()} (由 tools/sdc_experiment/report.py 自动汇总)\n",
             "## 诚实声明",
             "- gem5 O3 模型 ≠ TSV110 RTL: 所有仿真 diverge 率是模型级结论",
             "- 健康硅片上真 SDC 稀少: E3/E4 的 SDC=0 是预期结果, 不是方法失败",
             "- E5 是组粒度执行健康度关联 (Sim 代理指标混合), 非 SDC 率直接关联",
             "- 每个实验的判定标准在运行前预注册, 未达标者如实记录\n"]
    for d in sorted(glob.glob("output/experiments/*/")):
        name = os.path.basename(d.rstrip("/"))
        if name in ("feedback", "hw_scan_logs"):
            continue
        lines.append(f"\n## {name}\n")
        for f in ["summary.json"]:
            p = os.path.join(d, f)
            if os.path.exists(p):
                lines.append("```json\n" + open(p).read().strip() + "\n```\n")
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            if os.path.basename(f) == "summary.json":
                continue
            lines.append(f"\n### {os.path.basename(f)}\n```json\n" +
                         open(f).read().strip() + "\n```\n")
    lines.append("\n## scheme.md 声明对照表\n")
    lines.append("| scheme.md 声明 | 验证实验 | 状态 |")
    lines.append("|---|---|---|")
    for claim, exp in SCHEME_CLAIMS:
        lines.append(f"| {claim} | {exp} | 见上方 {exp.split()[0]} verdict |")
    out = "\n".join(lines) + "\n"
    print(out)

if __name__ == "__main__":
    main()
```

- [x] **Step 2: 生成报告并入库**

Run: `python3 tools/sdc_experiment/report.py > docs/experiments/2026-09-02-sdcfuzz-verification-report.md`
Expected: 报告含 E1–E5 全部 summary JSON + 声明对照表

- [x] **Step 3: Commit**

```bash
git add tools/sdc_experiment/report.py docs/experiments/2026-09-02-sdcfuzz-verification-report.md
git commit -m "feat(experiment): E6汇总报告——实验结果诚实汇总+scheme.md声明对照表"
git push
```

---

## Task 12: 端到端总演练 + 计划收尾

**Files:**
- Modify: `docs/superpowers/plans/2026-09-02-sdcfuzz-verification.md`（勾掉全部 checkbox）
- Create: `docs/experiments/2026-09-02-sdcfuzz-verification-report.md`（Task 11 已生成，此处最终更新）

**Interfaces:**
- Consumes: 全部前置任务
- Produces: 全链路验证过一遍的完整证据链 + 最终报告

- [x] **Step 1: 设备池总演练（local + 0101 + 用户设备）**

```bash
python3 tools/sdc_experiment/test_device_pool.py      # 全 PASS/SKIP
python3 tools/sdc_experiment/test_sim_sweep.py        # ALL PASS
python3 tools/sdc_experiment/test_hw_scan.py          # ALL PASS/SKIP
python3 tools/sdc_experiment/test_correlation.py      # ALL PASS
python3 tools/sdc_experiment/test_feedback.py         # ALL PASS
```
Expected: 5 个测试文件全部通过（SKIP 仅允许出现在"无远程设备/无历史日志"场景）

- [x] **Step 2: 回归检查（证明无附带破坏）**

Run: `python3 tools/sdc_mutator/test_evolution_engine.py`
Expected: PASS（既有进化引擎测试不受影响——本计划未改动它，回归证明框架无侵入）

- [x] **Step 3: 报告终版生成**

Run: `python3 tools/sdc_experiment/report.py > docs/experiments/2026-09-02-sdcfuzz-verification-report.md`
Expected: 报告含全部实验真实数据

- [x] **Step 4: 勾掉计划全部 checkbox 并 Commit**

```bash
git add docs/superpowers/plans/2026-09-02-sdcfuzz-verification.md docs/experiments/
git commit -m "docs(experiment): sdcfuzz 验证方案执行完毕——全计划勾选+终版报告"
git push
```

---

## 风险与应对（Risk Register）

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 本机 gem5-opt 或 ~/gem5-deps 损坏/误删 | 低 | E1/E2/E5 阻塞 | Task 5 Step 0 固化配置+workload 入仓（不受 0101 漂移影响）；gem5.opt 本体损坏时按 gem5-fi-wangxu progress.md 的 scons -j16 重建（29GB 内存勿超）；**备份路径：0101 环境完整可用（F9），注入行为等价性以 golden+分类一致为准** |
| 本机 gem5 与 0101 gem5 二进制不同（md5 不一致）注入行为有差异 | 低 | E1/E2 数字与 F3/F4 不可直接比 | F7 已实测 golden 逐字节一致 + 三类结局语义一致；E1 的作用正是本机复现基线（判定标准就是与 F3 方向一致），不一致即触发诚实记录与诊断 |
| 远程设备非 aarch64 / 内存不足 | 中 | 该设备不可用 | probe() 规格闸门（specs_ok=False 时不进扫描池），报告注明 |
| 用户密码含特殊字符导致 pty SSH 失败 | 低 | 注册失败 | `ssh_lib` 已处理 banner；实测不行则建议用户改用密钥（ssh-copy-id） |
| 本机满载扫描触发 MCE 复位 | 低 | **物理重启** | max_cpus 硬限 64，默认 8，逐步上调观察 SIGSEGV 噪声；gem5 sweep 并行度 ≤4 |
| 真机 SDC 命中为 transient（不可复现） | 高 | 误报 | replay-confirm ≥3 次复跑，不可复现标 transient 不计入 |
| E5 样本不足/无相关 | 高 | 关联声明不成立 | 诚实记录 INSUFFICIENT/NOT_SIGNIFICANT，报告中明确弱化解释 |
| gem5 sweep 时长超预算（E2≈14h 本机串行） | 中 | 进度拖延 | sim_sweep 加 `--jobs 2-4` 进程池（本机 128 核安全）；或降 --runs 100，判定阈值不变 |
| `snap_tool` flag 名与计划假设不符 | 中 | E3 脚本报错 | Step 6 单模板冒烟先行，实测 flag 后全量 |

## 自检（Self-Review 结论）

- **Spec 覆盖**：scheme.md §3.1（D13 数据复现→E2）、§4.2（真机执行→E3、进化引擎→E5 代理）、§4.3 L3/L4（分布式+噪声分类→E4、Runner→E3）、§4.4（Sim→HW 关联→E5）均有对应实验；§5 三大创新（AutoµSens/RL/功耗）是**未来工作**，本计划验证的是现有基座——已在 E5 诚实边界与报告对照表中说明。
- **仿真层 100% 本机化**：E1/E2/E5 的 gem5 注入全部在本机 `/home/sdc/wangxu/gem5-fi` 执行（Task 5 Step 0 把 0101 的配置三件套 + workload 一次性拉取入仓 `gem5_config/`，F7 已实测本机 golden 与 0101 逐字节一致、三类结局语义一致）；0101 从"主注入环境"降级为"备份环境 + E4 远程全链路演练对象"。远程设备仅承担 Layer 3/4 的真机扫描验证——这正是用户要求的"本机验证 + 可扩展远程"边界。
- **占位符扫描**：无 TBD/TODO；"实现时核对"处（snap_tool flag 名、RemoteDevice get 方向）均给出了具体核对对象与替代方案，不是占位符而是**防漂移护栏**。
- **类型一致性**：`Device.probe()` 返回结构在 Task 2 定义、Task 3/4 沿用；`gem5_env.GROUPS` 与 `run_group` 返回 dict 键在 Task 5 定义、E1/E2/E5 脚本沿用；`parse_log` 返回键在 Task 7 定义、Task 9/10 沿用；`analyze` 的输入行结构（`group`/`sim_key`/`hw_key`）在 Task 9 测试与实现一致。

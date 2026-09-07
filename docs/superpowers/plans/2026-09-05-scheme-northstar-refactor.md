# scheme.md 北极星对齐重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 docs/scheme.md 四层架构为北极星，修复仓库中六个"代码没跟上北极星"的断链点，使 L1→L4 数据流闭环从"三段孤岛"变为"接线可通"。

**Architecture:** 全部是增量修复，不搬迁目录、不重写模块：gem5 环境路径接入真实安装位置；kunpeng920 平台切换遗留的 2 个红测试修复（fixture 重新生成）；seeds/evolved 回灌接线到 guided mutation 消费端；操作数字典从三处值级拷贝合一为引用；hw 日志解析三处拷贝合一为单模块；根目录构建产物清理。

**Tech Stack:** Python 3.11（pytest 裸跑，无 Bazel）、bash 脚本、bazel-bin/tools/snap_tool。

**Spec:** `docs/scheme.md`（北极星）+ `.planning/2026-09-05-scheme-northstar-claude-md-refactor/findings.md` F3（差距分析：R1-R5、R10 的论证）。

## Global Constraints

- one-patch-per-unit：每个 Task = 一个 commit，验证通过才提交，提交后自动 push 到 `refactor/scheme-northstar-alignment` 分支（已创建，CLAUDE.md 更新 commit 9bdeb5b5 已在其上）。
- 自验证 100% 真实：每个 Task 的验证命令必须实跑并引用真实输出，禁止"应该能过"。
- MCE 红线：bazel 构建 `--jobs=32` 上限，Centipede `-j=10` 上限。本计划只有 Task 2 需要 bazel build。
- 本计划禁止目录物理重组（R7 已否决）、禁止实现新功能（R6/R8 已否决，超出重构范围）。
- 测试运行方式：`python3 -m pytest tools/sdc_experiment/ tools/sdc_pipeline/ tools/sdc_mutator/ -q`（现状 89 collect，87 pass + 2 fail——Task 3 就是修这 2 个 fail）。
- 已知基线：`git status` 里有大量未跟踪文件（.entire/ .planning/ build.log 等），Task 1 会处理根目录的；`.planning/` 和 `.entire/` 不属于本计划清理范围（是会话工作区）。
- pytest 会误收集 `tools/minimizer/passes_test.py`（Bazel cc_test），所以验证命令统一用 `python3 -m pytest tools/sdc_experiment/ tools/sdc_pipeline/ tools/sdc_mutator/ -q` 这三个目录，不带 `tools/` 根。

---

### Task 1: R10 — 根目录构建产物清理 + gitignore 补漏

**Files:**
- Modify: `.gitignore`
- Delete (untracked debris): `build.log`, `build_fuzz.log`, `http.log`, `test.log`, `cpython.tar.gz`, `lss.tar.gz`, `patch.py`
- Untrack: `scripts/__pycache__/ssh_lib.cpython-311.pyc`（git rm --cached；.gitignore 已有 `__pycache__/` 规则，删缓存即可防再犯）

**Interfaces:**
- Consumes: 无（独立卫生任务）
- Produces: 干净的 `git status`（根目录无未跟踪垃圾）；后续 Task 的 `git add -A` 语义安全

- [ ] **Step 1: 确认删除对象是纯构建产物/一次性脚本**

Run: `head -3 patch.py && ls -la build.log build_fuzz.log http.log test.log cpython.tar.gz lss.tar.gz`
Expected: patch.py 是一次性 platform.cc 补丁脚本（内容含 `filepath = '.../util/platform.cc'`，platform 专属 ID 已在 commit 2d04539 落地，脚本完成使命）；其余是日志/tarball。`output/sdcbench_*` 等产物目录已被 `output/` 规则忽略，不在处理范围。

- [ ] **Step 2: 删除未跟踪垃圾 + untrack pyc**

```bash
rm build.log build_fuzz.log http.log test.log cpython.tar.gz lss.tar.gz patch.py
git rm --cached scripts/__pycache__/ssh_lib.cpython-311.pyc
rm scripts/__pycache__/ssh_lib.cpython-311.pyc
```

注意：`cpython.tar.gz`（47MB）与 `lss.tar.gz` 是 MODULE.bazel 依赖镜像源（`http://127.0.0.1:8000/lss.tar.gz` 的本地源文件）。删除前先确认 `/home/sdc/wangxu/` 下另有副本或 http server 目录有源（`ls ~/wangxu/*.tar.gz 2>/dev/null`）；若根目录是唯一副本，先把两个 tarball 移到 `~/wangxu/`（mv 不 rm），并把这一事实写进 commit message。

- [ ] **Step 3: .gitignore 补漏**

在 `.gitignore` 末尾追加（`scripts/__pycache__` 已被 `__pycache__/` 覆盖，无需单独加；tarball/日志按模式防再犯）：

```
*.log
*.tar.gz
```

注意：`*.log` 会忽略未来想入库的日志吗——本仓库文档引用日志都走 docs/experiments/ 的转述，无入库日志先例，安全。`*.tar.gz` 同理（lss 依赖从本地 http server 取，不入库）。

- [ ] **Step 4: 验证**

Run: `git status --porcelain | grep '^??' | grep -v '/' `
Expected: 空输出（根目录无未跟踪文件）。

Run: `git ls-files | grep __pycache__`
Expected: 空输出。

Run: `git ls-files | grep -c pycache` 和 `python3 -m pytest tools/sdc_experiment/test_hw_scan.py -q 2>&1 | tail -1`
Expected: 0；hw_scan 测试 pass（证明删 pyc 无副作用）。

- [ ] **Step 5: Commit**

```bash
git add .gitignore && git add -u scripts/__pycache__ 2>/dev/null; git commit -m "chore(hygiene): 清理根目录构建产物 + untrack pyc + gitignore 补漏"
git push
```

---

### Task 2: R1 — gem5 环境路径修复（L2 层恢复可用）

**Files:**
- Modify: `tools/sdc_experiment/gem5_env.py:15-27`（`_find_gem5_opt` 候选列表）
- Modify: `tools/sdc_experiment/sdcbench_eval.py:18-21`（GEM5/CFG/ENV 硬编码改为从 gem5_env 取）
- Test: `tools/sdc_experiment/test_gem5_env.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `tools/sdc_experiment.gem5_env.GEM5_OPT` 解析到真实存在的 `~/gem5-fi-wangxu/build/ARM/gem5.opt`；新增 `CHAOS_SE_SCRIPT = ~/gem5-fi-wangxu/configs/se/arm_chaos.py`（sdcbench 协议用的 se 脚本，区别于 TAISHAN_SCRIPT）；`check_env()` 返回 `ok: True`。sdcbench_eval.py 的 `GEM5`/`CFG`/`ENV` 改为 `from tools.sdc_experiment.gem5_env import ...`（需 sys.path 处理，见 Step 3）。

背景（实证，findings.md F2 断链点 5）：本机唯一存在的 gem5 是 `~/gem5-fi-wangxu/`（v25.1.0.1，sdcbench_eval 用它跑通了 1000 序列评估）；`gem5_env.py` 的两个候选路径都不存在，`check_env()` 实跑 `ok: False`。

- [ ] **Step 1: 写失败测试**

新建 `tools/sdc_experiment/test_gem5_env.py`：

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gem5_env 路径解析测试。运行: python3 -m pytest tools/sdc_experiment/test_gem5_env.py -q"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment import gem5_env  # noqa: E402


def test_gem5_opt_resolves_to_existing_file():
    """GEM5_OPT 必须指向真实存在的 gem5.opt (本机 ~/gem5-fi-wangxu)。"""
    assert os.path.isfile(gem5_env.GEM5_OPT), \
        f"GEM5_OPT 不存在: {gem5_env.GEM5_OPT}"
    assert gem5_env.GEM5_OPT.endswith("build/ARM/gem5.opt")


def test_check_env_ok_on_this_host():
    """check_env 在本机应报 ok (gem5.opt + deps + taishan script + workloads)。"""
    r = gem5_env.check_env()
    assert r["ok"], f"check_env 报错: {r['problems']}"


def test_chaos_se_script_exists():
    """sdcbench 协议的 se 注入脚本路径存在。"""
    assert os.path.isfile(gem5_env.CHAOS_SE_SCRIPT), \
        f"CHAOS_SE_SCRIPT 不存在: {gem5_env.CHAOS_SE_SCRIPT}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tools/sdc_experiment/test_gem5_env.py -q`
Expected: 前 2 个 FAIL（GEM5_OPT 指向不存在的 `~/wangxu/gem5-fi/CHAOS/...`），第 3 个 FAIL（CHAOS_SE_SCRIPT 属性不存在）。

- [ ] **Step 3: 修改 gem5_env.py**

`_find_gem5_opt` 候选列表加入 `~/gem5-fi-wangxu/`（放首位——它是本机实测唯一存在的）：

```python
def _find_gem5_opt():
    cands = [os.path.expanduser(p) for p in (
        "~/gem5-fi-wangxu/build/ARM/gem5.opt",           # 本机实测唯一存在 (sdcbench 1000 序列评估所用)
        "~/wangxu/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt",  # 历史 0103 布局
        "~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt",          # 常规布局
    )]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]
```

在 `TAISHAN_SCRIPT = ...` 行后追加：

```python
# sdcbench 协议 (sdcbench_eval.py) 的 SE 注入脚本 — 与 TAISHAN_SCRIPT
# (two_level_taishan.py, sdc_pipeline gem5_runner 协议) 是两套配置, 见
# findings F2 断链点4: 两套 gem5 协议并存是已知现状, 本 task 只统一路径来源。
CHAOS_SE_SCRIPT = os.path.expanduser(
    "~/gem5-fi-wangxu/configs/se/arm_chaos.py")
```

- [ ] **Step 4: 修改 sdcbench_eval.py 头部**

把：

```python
GEM5 = "/home/sdc/wangxu/gem5-fi-wangxu/build/ARM/gem5.opt"
CFG = "/home/sdc/wangxu/gem5-fi-wangxu/configs/se/arm_chaos.py"
```

改为（保持模块其余处 `GEM5`/`CFG` 名字不变，改动最小）：

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools.sdc_experiment.gem5_env import GEM5_OPT as GEM5, CHAOS_SE_SCRIPT as CFG
```

注意：sdcbench_eval.py 目前没有 `import sys`（有 `import os, sys, json, ...`——实际第 11 行已有 sys，确认后直接用）。ENV 保持不动（它内联复制了 gem5-deps 的 LD_LIBRARY_PATH，与 local_gem5_env 的差异是 sdcbench 特有的 PATH 简化；统一 ENV 属于行为变更，超出本 task 范围，不碰）。

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest tools/sdc_experiment/test_gem5_env.py -q`
Expected: 3 passed。

Run: `python3 -m pytest tools/sdc_experiment/test_sim_sweep.py tools/sdc_pipeline/test_gem5_runner.py -q`
Expected: 全 pass（gem5_env 的既有消费者无回归）。

- [ ] **Step 6: 功能验证（真实 gem5 冒烟）**

Run: `timeout 120 /home/sdc/wangxu/gem5-fi-wangxu/build/ARM/gem5.opt --version 2>&1 | head -1`
Expected: 输出版本号（如 `gem5 version 25.1.0.1`）——证明路径真实可达（LD_LIBRARY_PATH 需要时用 `LD_LIBRARY_PATH=/home/sdc/gem5-deps/py/usr/lib64:/home/sdc/gem5-deps/usr/lib64` 前缀）。

Run: `python3 -c "import sys; sys.path.insert(0,'.'); from tools.sdc_experiment.gem5_env import check_env; print(check_env())"`
Expected: `{'ok': True, 'problems': []}`。

- [ ] **Step 7: Commit**

```bash
git add tools/sdc_experiment/gem5_env.py tools/sdc_experiment/sdcbench_eval.py tools/sdc_experiment/test_gem5_env.py
git commit -m "fix(gem5-env): 路径解析接入 ~/gem5-fi-wangxu 真实安装 + sdcbench_eval 去硬编码"
git push
```

---

### Task 3: R2 — 修复 test_feedback 2 个红测试（kunpeng920 平台切换遗留）

**Files:**
- Modify: `tools/sdc_experiment/feedback.py:33-34`（SNAP_TOOL 解析：优先 bazel-bin，fallback /usr/local/bin）
- Modify: `tools/sdc_experiment/test_feedback.py:33-40`（HEALTHY_PB 指向重新生成的 kunpeng920 平台 fixture）
- Create: `output/experiments/exp03-corpus-hw-local/pb/` 下的 fixture 重生脚本或直接重生 `e1_carry_chain.pb`（output/ 被 gitignore，fixture 不入库——但测试依赖它存在，需处理 skip 语义）

**Interfaces:**
- Consumes: Task 1/2 无依赖
- Produces: `tools/sdc_experiment.feedback.SNAP_TOOL` 变为函数级解析（或模块级三元判断）；test_feedback 8/8 pass。

背景（实证）：旧 `/usr/local/bin/snap_tool`（2026-08-25 部署）不认识 `arm-kunpeng920` 枚举（实跑报 `Illegal value`）；旧 fixture `output/experiments/exp03-corpus-hw-local/pb/e1_carry_chain.pb` 的 end state 只有 `arm-neoverse-n1` 平台位（snap_tool print 实证），新 snap_tool 用 kunpeng920 打包报 `no expected end state` → `package_pb_as_corpus` 返回 None → `replay_gate` 里 `item["replay"]` 无 `reproduced` 键 → KeyError。修复两步：(a) feedback.py 用 bazel-bin 新 snap_tool；(b) fixture 用 kunpeng920 平台重新生成（已实证可行：`snap_tool --raw --runner=... --target_platform=arm-kunpeng920 --out=/tmp/e1_new.pb make output/bin_stage_a/e1_carry_chain.bin` 成功，print 确认 `Platforms: arm-kunpeng920`，generate_corpus 成功，旧 runner 二进制复跑 `code:1` 即 OK）。

- [ ] **Step 1: 重新生成 fixture pb（kunpeng920 平台）**

```bash
bazel-bin/tools/snap_tool --raw \
  --runner=/usr/local/bin/reading_runner_main_nolibc \
  --target_platform=arm-kunpeng920 \
  --out=output/experiments/exp03-corpus-hw-local/pb/e1_carry_chain.pb \
  make output/bin_stage_a/e1_carry_chain.bin
```

Expected: `Re-made snapshot successfully.`

注意：output/ 在 .gitignore 里，fixture 是本地测试资源，不入库（现有测试已经是这个约定——`_have_tools()` 缺文件就 skip）。但为了让 fixture 可重生，把重生命令写进 test_feedback.py 的模块 docstring（见 Step 3）。

- [ ] **Step 2: 修 feedback.py 的 SNAP_TOOL 解析**

把：

```python
SNAP_TOOL = "/usr/local/bin/snap_tool"
RUNNER = "/usr/local/bin/reading_runner_main_nolibc"
```

改为：

```python
# snap_tool 优先 bazel-bin 新构建 (认识 arm-kunpeng920 枚举);
# /usr/local/bin 的 2026-08-25 部署版先于专属 PlatformId (2d04539), 会拒绝
# --target_platform=arm-kunpeng920 (实测 Illegal value), 仅作 fallback。
_BAZEL_SNAP_TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bazel-bin/tools/snap_tool")
SNAP_TOOL = _BAZEL_SNAP_TOOL if os.path.isfile(_BAZEL_SNAP_TOOL) \
    else "/usr/local/bin/snap_tool"
RUNNER = "/usr/local/bin/reading_runner_main_nolibc"
```

- [ ] **Step 3: test_feedback.py 补 fixture 重生说明**

模块 docstring（现有 docstring 之后）追加：

```python
# fixture 重生 (kunpeng920 平台切换 2026-09-05 后旧 N1 fixture 失配):
#   bazel-bin/tools/snap_tool --raw \
#     --runner=/usr/local/bin/reading_runner_main_nolibc \
#     --target_platform=arm-kunpeng920 \
#     --out=output/experiments/exp03-corpus-hw-local/pb/e1_carry_chain.pb \
#     make output/bin_stage_a/e1_carry_chain.bin
```

同时确认 `_have_tools()` 已覆盖 skip 语义（现有代码已做，无需改）。

- [ ] **Step 4: 验证（修复目标测试）**

Run: `python3 -m pytest tools/sdc_experiment/test_feedback.py -q`
Expected: `8 passed`（原 2 failed + 6 passed）。

- [ ] **Step 5: 回归验证**

Run: `python3 -m pytest tools/sdc_experiment/ tools/sdc_pipeline/ tools/sdc_mutator/ -q 2>&1 | tail -1`
Expected: `89 passed`（87+2，全绿）。

Run: `python3 -m pytest tools/sdc_experiment/test_hw_scan.py -q 2>&1 | tail -1`
Expected: pass（无关测试无回归）。

- [ ] **Step 6: Commit**

```bash
git add tools/sdc_experiment/feedback.py tools/sdc_experiment/test_feedback.py
git commit -m "fix(feedback): snap_tool 优先 bazel-bin 新构建 + fixture 重生为 kunpeng920 平台"
git push
```

---

### Task 4: R3 — seeds/evolved 回灌接线（L3→L1 反馈闭环通路）

**Files:**
- Modify: `scripts/run_guided_mutation.sh:48-50`（阶段 A 拷入 seeds/evolved/*.bin）
- Test: 手工功能验证（bash 脚本，无 pytest 惯例；验证方式见 Step 3）

**Interfaces:**
- Consumes: `feedback.py::reseed` 写入的 `seeds/evolved/<hash>.bin`（.bin 格式与 `seeds/bin/*.bin` 相同——raw 指令字节，feedback.py docstring 实证 `cmp 逐字节一致`）
- Produces: `output/bin_stage_a/` 含 evolved 种子 → `build_sdc_corpus.sh` 阶段 A 自动消费（已存在，无需改）→ 下一轮真机扫描包含确认命中的序列。北极星 Layer3→Layer1 反馈闭环接线完成。

背景（实证）：feedback.py reseed 写 `seeds/evolved/`，但 `run_guided_mutation.sh` 只拷 `seeds/bin/*.bin`（第 49 行），`build_sdc_corpus.sh` 只扫 `output/bin_stage_a/`——回灌文件进死胡同。run_e2e.sh 第 10 行注释声称"回灌 seeds/evolved/ → (loop 时) 再变异再扫描"但从未接线。

- [ ] **Step 1: 修改 run_guided_mutation.sh run_stage_a**

在第 49 行 `cp "$SEED_DIR"/bin/*.bin "$BIN_DIR_A"/ 2>/dev/null || true` 后追加：

```bash
  # 回灌接线 (R3): feedback.py reseed 确认命中 → seeds/evolved/<hash>.bin
  # (与 seeds/bin 同格式, cmp 逐字节一致)。拷入阶段 A 池, 使 build_sdc_corpus
  # 阶段 A 消费 → 下一轮扫描包含确认命中序列。北极星 L3→L1 闭环接线点。
  cp "$SEED_DIR"/evolved/*.bin "$BIN_DIR_A"/ 2>/dev/null || \
    echo "  (seeds/evolved/ 为空或不存在, 无回灌种子 — 正常)"
```

- [ ] **Step 2: 语法检查**

Run: `bash -n scripts/run_guided_mutation.sh && echo SYNTAX-OK`
Expected: `SYNTAX-OK`。

- [ ] **Step 3: 功能验证（真实接线冒烟）**

```bash
# 造一个假 evolved 种子 (用现有模板 bin 冒充 — 验证拷贝路径, 不真跑 fuzz)
mkdir -p seeds/evolved
cp seeds/bin/e1_carry_chain.bin seeds/evolved/fakehash_test.bin
# 只跑阶段 A (SKIP 阶段 B: 环境变量控制不存在的话, 用 dry 检查方式)
bash -c 'source /dev/stdin <<"EOF"
$(sed -n "/^run_stage_a()/,/^}/p" scripts/run_guided_mutation.sh)
SEED_DIR=seeds; VAR_DIR=/tmp/var_test; BIN_DIR_A=/tmp/bin_a_test; MUTATOR=tools/sdc_mutator/operand_mutator.py
mkdir -p "$VAR_DIR" "$BIN_DIR_A"
run_stage_a
ls /tmp/bin_a_test/fakehash_test.bin && echo "EVOLVED-WIRED-OK"
EOF'
rm -rf seeds/evolved /tmp/var_test /tmp/bin_a_test
```

Expected: 输出含 `EVOLVED-WIRED-OK`（evolved bin 确实进了阶段 A 池）。注意清理步骤必须执行（`rm -rf seeds/evolved`），防止假种子残留污染后续真实运行。

再验证空目录分支（诚实分支）：

```bash
bash -c 'SEED_DIR=seeds; BIN_DIR_A=/tmp/bin_a_test2; VAR_DIR=/tmp/var_test2
mkdir -p "$BIN_DIR_A" "$VAR_DIR"
cp "$SEED_DIR"/bin/*.bin "$BIN_DIR_A"/ 2>/dev/null || true
cp "$SEED_DIR"/evolved/*.bin "$BIN_DIR_A"/ 2>/dev/null || echo "  (seeds/evolved/ 为空或不存在, 无回灌种子 — 正常)"'
```

Expected: 打印"为空"提示行，退出码 0。

- [ ] **Step 4: 回归验证**

Run: `bash -n scripts/run_e2e.sh && bash -n scripts/build_sdc_corpus.sh && echo SCRIPTS-OK`
Expected: `SCRIPTS-OK`（下游脚本语法完好）。

Run: `python3 -m pytest tools/sdc_experiment/test_feedback.py -q 2>&1 | tail -1`
Expected: pass（feedback 侧无回归）。

- [ ] **Step 5: Commit**

```bash
git add scripts/run_guided_mutation.sh
git commit -m "feat(feedback-wiring): seeds/evolved 回灌种子接入 guided mutation 阶段A池"
git push
```

---

### Task 5: R4 — 操作数字典溯源注记（降级为文档化，不合并）

**Files:**
- Modify: `tools/sdc_experiment/sdcbench_gen.py:24-25`（OPERAND_FAMILIES 注释改为准确的溯源说明）
- Test: 无新增测试（纯注释改动，验证 = 注释与实证审计结果一致）

**Interfaces:**
- Consumes: 本 plan 编写期间完成的逐值审计（见下）
- Produces: 准确的溯源注释；无行为变化。

背景（**计划期间已实证审计，推翻了"纯值级拷贝"的原假设**）：逐值比对 `sdcbench_gen.OPERAND_FAMILIES`（18 族）与 `csp_targeted_generator` 的三个表（CARRY_CHAIN_TARGETED 10 项 / MUL_EXTREME_TARGETED 7 项 / TOGGLE_RATE_TARGETED 6 项，结构是 `(label, x1, x2, desc)` 四元组，语义是"两操作数对"）：

- **8 个族同名同值**（cc32_boundary / cc48 / cc_sign_overflow / cc64_plus_alt / cc_bit31_walk / cc_bit63_walk / cc_byte_boundary / toggle_plus_carry）——这部分确实是 CSP 值的借用；
- **2 个改名借用**（cc64_full ≈ cc64_full_zero、cc64_nonzero ≈ cc64_full_nonzero，值相同名字简化）；
- **8 个是 sdcbench 原创新设计**（alt01_step / alt10_step / maxpos_step / maxneg_step / golden_step / sparse_walk / densr_walk / rand_mix）——其中 golden_step 的 0x9E3779B97F4A7C15 可溯源到校准实验 sdcbench2.c 的步进常量（会话历史实证），它们是为 (init, step) 步进链语义设计的，CSP 表里没有对应物。

**结论：这不是可消除的重复——是"借 8 + 改 2 + 原创 8"的演化关系，且两侧语义不同（CSP=x1/x2 操作数对 vs sdcbench=init/step 步进链）。强行合并会造出一个假抽象（两种语义塞一张表）。** 正确的重构是：把第 24 行不准确的注释（"来自 csp_targeted_generator.py 的实证族"暗示全部拷贝）改为如实的溯源说明，消除下一个读者的"这是重复代码"误判。这是 findings.md F3 重构候选评估时风险/收益判断的修正：R4 从"合一"降级为"溯源注记"，理由是实证审计发现前提不成立。

- [ ] **Step 1: 修改注释**

把 `tools/sdc_experiment/sdcbench_gen.py` 第 24 行：

```python
# 操作数字典 — CSP 定向族 (来自 csp_targeted_generator.py 的实证族)
```

改为：

```python
# 操作数字典 — (name, init, step) 步进链族。溯源 (2026-09-05 逐值审计):
#   - 8 族值借自 csp_targeted_generator.CARRY_CHAIN_TARGETED (同名同值);
#   - cc64_full/cc64_nonzero 是其 cc64_full_zero/cc64_full_nonzero 改名简化;
#   - 8 族 (alt01_step/golden_step/sparse_walk 等) 为 sdcbench 原创步进链设计
#     (golden_step=0x9E3779B97F4A7C15 溯源校准实验 sdcbench2.c), CSP 表无对应物。
#   注意语义差异: CSP 表是 (x1,x2) 操作数对, 本表是 (init,step) 步进对 —
#   不做强行合并 (两语义塞一张表是假抽象)。
```

- [ ] **Step 2: 验证（注释与审计事实一致 + 零行为变化）**

Run: `python3 -c "
import sys; sys.path.insert(0,'tools/sdc_experiment'); sys.path.insert(0,'.')
from sdcbench_gen import OPERAND_FAMILIES
assert len(OPERAND_FAMILIES) == 18
names = [f[0] for f in OPERAND_FAMILIES]
for n in ('cc32_boundary','cc48','golden_step','rand_mix'): assert n in names
print('18 族不变式 OK')
"`
Expected: `18 族不变式 OK`。

Run: `python3 -m pytest tools/sdc_experiment/test_feedback.py -q 2>&1 | tail -1`
Expected: pass（无行为变化）。

- [ ] **Step 3: Commit**

```bash
git add tools/sdc_experiment/sdcbench_gen.py
git commit -m "docs(sdcbench): OPERAND_FAMILIES 溯源注记——逐值审计证伪'纯拷贝'假设, 借8改2原创8"
git push
```

---

### Task 6: R5 — hw 日志解析合一（三处拷贝 → 单模块）

**Files:**
- Create: `tools/sdc_experiment/hw_log_parser.py`（唯一权威解析）
- Modify: `tools/sdc_experiment/hw_scan.py:30-52`（parse_log 改为 thin wrapper 调用共享模块）
- Modify: `scripts/collect_results.py:32-60`（parse_log 改 import 共享模块）
- Modify: `tools/sdc_experiment/feedback.py:41-44`（_HASH_RE/_OUTCOME_RE 改 import 共享正则）
- Test: `tools/sdc_experiment/test_hw_log_parser.py`（新建）；既有 `test_hw_scan.py` 不改（它的 parse_log 断言成为共享模块的回归网）

**Interfaces:**
- Consumes: 三处现状拷贝的正则（逐字符一致——hw_scan.py docstring 自证"与 collect_results.py::parse_log 逐字符一致的解析 (移植)"，已核对两边正则相同）
- Produces: `tools.sdc_experiment.hw_log_parser.parse_log(text) -> dict`（键：sigsegv_noise/sigterm/runaway_noise/misbehave_noise/sdc_hits/sdc_details/total_failed，与现三处输出**完全同构**）；`HASH_RE`/`OUTCOME_RE` 模块级编译正则（feedback.py 消费）。

背景：SDC 判定口径（outcome 2/3/4 = SDC，5/6 = 噪声）散落三处靠人工保持一致——runner.cc:687 行形态是唯一事实源。合一后单点维护。

- [ ] **Step 1: 写失败测试**

新建 `tools/sdc_experiment/test_hw_log_parser.py`：

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_log_parser 单一权威解析测试。
运行: python3 -m pytest tools/sdc_experiment/test_hw_log_parser.py -q"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from tools.sdc_experiment.hw_log_parser import parse_log, HASH_RE, OUTCOME_RE  # noqa: E402

FAKE_LOG = """Snapshot [abc123def456abc123def456abc123def456abcd] failed, outcome = 2
Snapshot [def456] failed, outcome = 5
Snapshot [789abc] failed, outcome = 3
Snapshot [aaa000] failed, outcome = 6
Received signal SIGSEGV while outside of snap
Received signal SIGSEGV while outside of snap
SIGTERM received
"""


def test_parse_log_counts():
    r = parse_log(FAKE_LOG)
    assert r["sdc_hits"] == 2          # outcome 2+3
    assert r["runaway_noise"] == 1     # outcome 5
    assert r["misbehave_noise"] == 1   # outcome 6
    assert r["sigsegv_noise"] == 2
    assert r["sigterm"] == 1
    assert r["total_failed"] == 4
    assert len(r["sdc_details"]) == 2


def test_parse_log_empty():
    r = parse_log("")
    assert r == {"sigsegv_noise": 0, "sigterm": 0, "runaway_noise": 0,
                 "misbehave_noise": 0, "sdc_hits": 0, "sdc_details": [],
                 "total_failed": 0}


def test_regexes_feedback_shape():
    """feedback.py 消费的 hash/outcome 提取正则。"""
    m = HASH_RE.search("Snapshot [abc123] failed, outcome = 2")
    assert m and m.group(1) == "abc123"
    m = OUTCOME_RE.search("Snapshot [abc123] failed, outcome = 2")
    assert m and m.group(1) == "2"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tools/sdc_experiment/test_hw_log_parser.py -q`
Expected: collection error（`hw_log_parser` 模块不存在）。

- [ ] **Step 3: 创建 hw_log_parser.py**

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""hw_log_parser.py — runner/orchestrator 日志的单一权威解析。

SDC 判定口径唯一定义点 (此前三处拷贝: hw_scan.py / collect_results.py /
feedback.py, 靠人工保持一致):
  runner RunSnapOutcome 枚举 (common/snapshot_enums.h):
    0=kAsExpected 1=kPlatformMismatch 2=kMemoryMismatch
    3=kRegisterStateMismatch 4=kEndpointMismatch
    5=kExecutionRunaway 6=kExecutionMisbehave
  真 SDC = outcome 2/3/4 (计算结果与预期不符, 静默数据损坏);
  outcome 5 (满负载调度延迟超时) / 6 (信号) = 噪声;
  SIGSEGV-outside-snap (fork/mmap 资源耗尽击中 snap 外路径) / SIGTERM = 噪声。
日志行形态 (runner.cc:687): Snapshot [<40位hex>] failed, outcome = <n>
"""
import re

_FAILED_RE = re.compile(
    r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = (\d+)')
_SDC_DETAIL_RE = re.compile(
    r'Snapshot \[[0-9a-f]+\][^\n]*failed, outcome = [234]')
_SIGSEGV_RE = re.compile(r'SIGSEGV while outside of snap')
_SIGTERM_RE = re.compile(r'SIGTERM')

# feedback.py 消费的单值提取正则 (hash / outcome)
HASH_RE = re.compile(r"Snapshot \[([0-9a-f]+)\]")
OUTCOME_RE = re.compile(r"outcome = (\d+)")


def parse_log(text: str) -> dict:
    """解析 runner/orchestrator 日志文本 → 结构化计数。"""
    sigsegv_outside = len(_SIGSEGV_RE.findall(text))
    sigterm = len(_SIGTERM_RE.findall(text))
    all_failed = _FAILED_RE.findall(text)
    sdc_outcomes = [o for o in all_failed if o in ('2', '3', '4')]
    runaway = sum(1 for o in all_failed if o == '5')
    misbehave = sum(1 for o in all_failed if o == '6')
    sdc_details = _SDC_DETAIL_RE.findall(text)[:10]
    return {"sigsegv_noise": sigsegv_outside, "sigterm": sigterm,
            "runaway_noise": runaway, "misbehave_noise": misbehave,
            "sdc_hits": len(sdc_outcomes), "sdc_details": sdc_details,
            "total_failed": len(all_failed)}
```

- [ ] **Step 4: 三处消费方切换**

**hw_scan.py**：`parse_log` 函数体替换为转发（保留函数签名与 docstring 的口径说明，docstring 改为指向权威模块）：

```python
from tools.sdc_experiment.hw_log_parser import parse_log as _parse_log  # 权威解析
# (放在文件头部 import 区; hw_scan.py 已有 sys.path.insert 到 repo 根的模式吗?
#  hw_scan.py 作为被 import 的模块由 test 以 repo 根路径加载, 直接
#  from tools.sdc_experiment.hw_log_parser import ... 即可)

def parse_log(text: str) -> dict:
    """单一权威解析在 hw_log_parser.py (口径: outcome 2/3/4=SDC)。"""
    return _parse_log(text)
```

（若 hw_scan.py 是被 `python3 tools/sdc_experiment/hw_scan.py` 直接运行的脚本，需要在其 main 入口前加 `sys.path.insert(0, repo根)` 惯例——参照 test_hw_scan.py 第 10 行的既有做法。）

**collect_results.py**：删除第 32-60 行的本地 `parse_log` 定义，改为：

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.sdc_experiment.hw_log_parser import parse_log  # noqa: E402
```

（collect_results.py 现有 `sys.path.insert(0, os.path.dirname(__file__))` 是为 import ssh_lib——保留它，另加一行 repo 根路径。）

**feedback.py**：删除第 41-44 行的 `_HASH_RE`/`_OUTCOME_RE` 本地定义，改为：

```python
from tools.sdc_experiment.hw_log_parser import HASH_RE as _HASH_RE, OUTCOME_RE as _OUTCOME_RE
```

（feedback.py 被 test 以 repo 根加载，无需额外 path 处理。）

- [ ] **Step 5: 验证**

Run: `python3 -m pytest tools/sdc_experiment/test_hw_log_parser.py tools/sdc_experiment/test_hw_scan.py tools/sdc_experiment/test_feedback.py -q 2>&1 | tail -1`
Expected: 全 pass（新测试 + 既有 hw_scan 断言网 + feedback 回归）。

Run: `python3 -c "
import sys; sys.path.insert(0,'.')
from scripts_style_check import *
" 2>/dev/null; python3 -c "
import subprocess, sys
# collect_results.py 的 import 链路冒烟 (不真跑 main, 只 import)
r = subprocess.run([sys.executable, '-c', '''
import sys, types
sys.path.insert(0, \".\")
sys.argv = [\"collect_results.py\", \"--help\"]
exec(open(\"scripts/collect_results.py\").read())
'''], capture_output=True, text=True, timeout=10)
print('import+help rc:', r.returncode)
"`
Expected: rc 0（--help 能打印说明 import 链路完好）。

Run: `python3 -m pytest tools/sdc_experiment/ tools/sdc_pipeline/ tools/sdc_mutator/ -q 2>&1 | tail -1`
Expected: 全 pass（Task 3 后基线 89 + 本 task 新增测试数）。

- [ ] **Step 6: Commit**

```bash
git add tools/sdc_experiment/hw_log_parser.py tools/sdc_experiment/test_hw_log_parser.py tools/sdc_experiment/hw_scan.py tools/sdc_experiment/feedback.py scripts/collect_results.py
git commit -m "refactor(parser): hw 日志解析三处拷贝合一为 hw_log_parser 单一权威模块"
git push
```

---

### Task 7: 收尾验证 + 全链冒烟

**Files:**
- 无新文件（纯验证任务）

**Interfaces:**
- Consumes: Task 1-6 全部产出
- Produces: 全链验证记录（写进本 plan 的勾选与 commit 记录）

- [ ] **Step 1: 全量测试**

Run: `python3 -m pytest tools/sdc_experiment/ tools/sdc_pipeline/ tools/sdc_mutator/ -q 2>&1 | tail -1`
Expected: 全 pass，0 failed（基线 89 + Task 2 新增 3 + Task 6 新增 3 = 95；Task 5 已降级为注释改动无新测试）。

- [ ] **Step 2: e2e 脚本 dry-run 冒烟**

Run: `bash scripts/run_e2e.sh --dry-run --scan-mode local --duration 10s --loop 1 --feedback none 2>&1 | tail -10`
Expected: dry-run 模式输出各步骤计划，无报错退出（脚本自身支持 --dry-run flag，见 run_e2e.sh 参数解析）。
（注意：DRY_RUN 环境变量形式在本计划执行期间曾被 run_e2e.sh:33 的初始化覆盖触发过一次真实满核扫描，该缺陷已由本 commit 修复为 ${DRY_RUN:-}）

- [ ] **Step 3: bazel 回归（证明 C++ 侧零改动零破坏）**

Run: `bazel build -c opt --jobs=32 //tools:snap_tool //runner:reading_runner_main_nolibc 2>&1 | tail -2`
Expected: 构建成功（本计划未碰 C++，此为回归证明）。

- [ ] **Step 4: git 状态清洁确认**

Run: `git status --porcelain | grep '^??' | grep -v '/'`
Expected: 空输出。

Run: `git log --oneline main..HEAD`
Expected: 7 个 commit（1 CLAUDE.md + 6 重构），全部已 push。

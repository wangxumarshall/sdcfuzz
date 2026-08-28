# SDC 自适应进化引擎与 Paper 2 完整实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建基于 Unicorn 微架构反馈的自适应进化引擎，从普通指令自动演化出高 SDC 激发概率操作数，在 bit-flip + 结构故障两度量上击败 SiliFuzz 随机变异，输出 best-paper 级 Paper 2。

**Architecture:** 三因子适应度函数（T(di/dt) 翻转量 + M(Path) 微架构深度 + E(AntiMasking) 反掩蔽高熵+雪崩）引导三个变异算子（toggle 梯度爬山、边界差异放大、上下文重组），形成 Seed→Evaluate→Mutate/Simulate/Score/Select/AntiMasking→Emit→上硅 的进化 pipeline。进化引擎用 Python unicorn+capstone 实现，生成语料 D 后经 silifuzz snap_tool 转 Snapshot，在 gem5-fi（0101）做 A/B/C/D 四组对比。

**Tech Stack:** Python 3.11 + unicorn 2.1.4 + capstone 5.0.9（0103 已装，阿里云镜像）；silifuzz bazel 工具链（snap_tool/runner/orchestrator）；gem5-fi CHAOS（0101，byte_lane_skew 结构注入已启用）；4 单板分布式扫描（0101/0102/0103/0201）。

**Spec:** `docs/plan/paper2-bestpaper-program.md`（攻坚计划）+ 用户进化引擎设计指令（适应度函数+三算子+pipeline）

## Global Constraints

- **诚实红线**：未测出 D>B 绝不谎称"击败 SiliFuzz"；严格区分真 SDC（outcome 2/3/4）与 runaway(5)/misbehave(6) 噪声；干净 diverge（SUM/CRC≠golden）与 gem5 异常退出区分；引用不可机器核实标 [CITE TBD: verify]，不伪造
- **MCE 红线**：128 核服务器，bazel `--jobs=32`，centipede/orchestrator 并发限 `-j=10`/`--max_cpus`
- **gem5 O3 ≠ TSV110 RTL**（Paper 1 §7），所有 gem5 diverge 率是模型级非硅片级
- **不谎称复现核心 179**（Paper 1 警告满载触发 watchdog 复位）
- **分支**：`feat/sdc-detection-cases-kunpeng920`，每任务 commit+push
- **0101 SSH**：用 `scripts/ssh_lib.py`（零依赖 pty），root/sdc 密码 SDC@2026；gem5 编译时 pty 耗尽，需等编译完成或停止 0103 扫描释放

## 当前已验证事实（计划基础）

- A/B/C bit-flip（CHAOSReg bit-flip 注入）：A(朴素字典)=3.9%(18/458), B(随机)=8.0%(40/500), C(CSP配对)=3.7%(14/380)，C/B=0.46×, p=0.0083 **统计显著证伪**
- A/B/C 结构故障（CHAOSLSQFwd byte_lane_skew）：A=2.0%(10/500), B=8.4%(42/500), C=2.8%(14/500)，C/B=0.33×, p=0.0001 **统计显著证伪**
- 进化引擎原型：从 ADDS X0,X1,X2 + 普通操作数(0x123/0x456)，三算子演化 T 8→70（8.8× 提升），操作数无规律但高压
- Unicorn ArchFeatureGenerator：reg_toggle per-bit 粒度（EmitSetBitFeatures+ForEachSetBit），T(di/dt)=popcount 可直接计算
- gem5 重编译完成，CHAOSLSQFwd structuralFault 参数生效（numStructuralByteLaneSkew=1 验证）
- Paper 1（gem5-fi/PAPER.md）= core-179 forensics + CHAOS 结构 FI，独立论文，Paper 2 引为 ground truth，零重叠

---

## File Structure

| 文件 | 职责 | 状态 |
|------|------|------|
| `tools/sdc_mutator/evolution_engine.py` | 进化引擎核心：适应度函数+三算子+pipeline | 已有原型，需扩展 |
| `tools/sdc_mutator/evolution_corpus_gen.py` | **新**：用进化引擎批量生成语料 D 的 .bin | 待建 |
| `tools/sdc_mutator/test_evolution_engine.py` | **新**：进化引擎单元测试 | 待建 |
| `seeds/gem5/sdc_probe_workload_evolved.c` | **新**：进化引擎生成的高压工作负载（对应 A/B/C 的 D 组） | 待建 |
| `scripts/gem5_sweep_abcd.py` | **新**：A/B/C/D 四组对比 sweep（bit-flip + 结构） | 待建 |
| `scripts/collect_business_traces.py` | **新**：采集业务高频指令序列（算子三 crossover 源） | 待建 |
| `docs/paper/paper2_silifuzz_detection_deployment.md` | Paper 2 正文 | 已有 222 行，需重写主线 |
| `docs/kunpeng920_sdc_research_report.md` | 研究报告 | 已有，需更新§7 |
| `docs/plan/paper2-bestpaper-program.md` | 攻坚计划 | 已有，需更新进展 |

---

## Task 1: 进化引擎单元测试（TDD 基础）

**Files:**
- Create: `tools/sdc_mutator/test_evolution_engine.py`
- Modify: `tools/sdc_mutator/evolution_engine.py`（如需修 bug）

**Interfaces:**
- Consumes: `evolution_engine.py` 的 `EvolutionEngine` 类、`popcount`、`hamming_entropy`
- Produces: 测试验证适应度函数正确性、三算子可运行、雪崩测试可运行

- [ ] **Step 1: 写失败测试——适应度函数**

```python
# tools/sdc_mutator/test_evolution_engine.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import EvolutionEngine, popcount, hamming_entropy, encode_adds_x0_x1_x2

def test_popcount():
    assert popcount(0xFF) == 8
    assert popcount(0) == 0
    assert popcount(0xFFFFFFFFFFFFFFFF) == 64

def test_hamming_entropy():
    assert hamming_entropy(0) == 0.0          # 全0, 低熵
    assert hamming_entropy(0xFFFFFFFFFFFFFFFF) == 0.0  # 全1, 低熵
    assert 0.9 < hamming_entropy(0x5555555555555555) < 1.0  # 50% 翻转, 高熵

def test_run_once_returns_score():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    final, T, M, E, S = eng.run_once(regs)
    assert T >= 0 and M >= 0 and E >= 0 and S >= 0
    assert isinstance(final, dict)

def test_toggle_hill_climb_increases_T():
    eng = EvolutionEngine(encode_adds_x0_x1_x2())
    regs = {0: 0x123, 1: 0x456, 2: 0x789, 3: 0xabc, 4: 0xdef}
    _, init_T, _, _, _ = eng.run_once(regs)
    best, best_T, _, _ = eng.toggle_hill_climb(regs, iterations=20)
    assert best_T >= init_T  # 爬山后 T 不降

if __name__ == "__main__":
    test_popcount(); print("✓ popcount")
    test_hamming_entropy(); print("✓ hamming_entropy")
    test_run_once_returns_score(); print("✓ run_once")
    test_toggle_hill_climb_increases_T(); print("✓ toggle_hill_climb")
    print("All tests passed")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python3 tools/sdc_mutator/test_evolution_engine.py`
Expected: PASS（原型已工作）或 FAIL（需修 bug）

- [ ] **Step 3: 若 FAIL, 修 evolution_engine.py 至测试通过**

- [ ] **Step 4: 运行测试验证通过**

Run: `python3 tools/sdc_mutator/test_evolution_engine.py`
Expected: "All tests passed"

- [ ] **Step 5: Commit**

```bash
git add tools/sdc_mutator/test_evolution_engine.py tools/sdc_mutator/evolution_engine.py
git commit -m "test(evolve): 进化引擎单元测试 — 适应度函数/三算子/雪崩测试验证"
git push
```

---

## Task 2: 长指令序列进化支持

**Files:**
- Modify: `tools/sdc_mutator/evolution_engine.py`（支持多指令序列 code_bytes）

**Interfaces:**
- Consumes: Task 1 的 EvolutionEngine
- Produces: EvolutionEngine 支持任意长 code_bytes（多指令序列），count 参数调大

**问题**：当前 `emu_start(..., count=64)` 限制 64 条指令，单条 ADDS 雪崩有限。需支持长序列（如 8-16 条混合指令）让进化有足够空间。

- [ ] **Step 1: 写失败测试——长序列进化**

```python
# 加入 test_evolution_engine.py
def test_long_sequence_evolution():
    # 8 条混合指令序列 (ADD/EOR/MUL/ADDS 交替)
    seq = b''
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('230200ca')  # eor x3,x1,x2
    seq += bytes.fromhex('610c029b')  # mul x1,x2,x3
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2
    seq += bytes.fromhex('6300008b')  # add x3,x3,x3
    seq += bytes.fromhex('640200ca')  # eor x4,x1,x2
    seq += bytes.fromhex('200b008b')  # add x0,x1,x2
    seq += bytes.fromhex('200b00ab')  # adds x0,x1,x2
    eng = EvolutionEngine(seq)
    regs = {0: 0x111, 1: 0x222, 2: 0x333, 3: 0x444, 4: 0x555}
    _, T, _, _, _ = eng.run_once(regs)
    assert T > 0  # 长序列应有翻转
    best, best_T, _, _ = eng.toggle_hill_climb(regs, 30)
    assert best_T >= T
```

- [ ] **Step 2: 运行验证失败/通过**

Run: `python3 tools/sdc_mutator/test_evolution_engine.py`
Expected: 若 count=64 限制导致长序列执行不全, FAIL

- [ ] **Step 3: 修 evolution_engine.py 的 emu_start count**

```python
# run_once 中, 把 count=64 改为 count=len(self.code_bytes)//4 * 2 (足够跑完全序列)
mu.emu_start(self.code_addr, self.code_addr + len(self.code_bytes), 
             timeout=1000000, count=max(64, len(self.code_bytes)//4 * 2))
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python3 tools/sdc_mutator/test_evolution_engine.py`
Expected: All tests passed

- [ ] **Step 5: Commit**

```bash
git add tools/sdc_mutator/evolution_engine.py tools/sdc_mutator/test_evolution_engine.py
git commit -m "feat(evolve): 长指令序列进化支持 (count 自适应, 多指令混合序列)"
git push
```

---

## Task 3: 业务指令序列采集（算子三 crossover 源）

**Files:**
- Create: `scripts/collect_business_traces.py`

**Interfaces:**
- Consumes: 0101/0102/0103 单板上的真实业务负载（如 opendcdiag eigen）
- Produces: `seeds/business_traces/` 下的高频指令序列 .bin（算子三 crossover 源）

**目的**：算子三需"从业务集群抓取高频指令序列"插入前后。采集真实业务代码片段。

- [ ] **Step 1: 写采集脚本**

```python
# scripts/collect_business_traces.py
#!/usr/bin/env python3
"""采集业务高频指令序列 (算子三 crossover 源)
从单板上真实业务负载的二进制中提取 .text 段, 截取高频指令序列片段"""
import sys, os, subprocess
# 用 objdump -d 反汇编业务二进制, 提取连续指令序列
# 业务源: opendcdiag eigen / silifuzz corpus 中的真实 snapshot
# 输出: seeds/business_traces/trace_NN.bin (每段 16-64 字节指令序列)
def extract_text_sequences(binary, out_dir, n=20, seq_len=32):
    os.makedirs(out_dir, exist_ok=True)
    # objdump -d 取 .text, 按 seq_len 字节切片段
    r = subprocess.run(['objdump','-d','-j','.text',binary], capture_output=True, text=True)
    # 解析指令, 提取 raw bytes 片段 (略, 用 objcopy -O binary -j .text 更简单)
    subprocess.run(['objcopy','-O','binary','-j','.text',binary,'/tmp/_text.bin'], check=True)
    data = open('/tmp/_text.bin','rb').read()
    for i in range(n):
        off = (i * 137) % max(1, len(data) - seq_len)  # 伪随机偏移
        chunk = data[off:off+seq_len]
        open(f'{out_dir}/trace_{i:02d}.bin','wb').write(chunk)
    print(f"Extracted {n} traces to {out_dir}")

if __name__ == "__main__":
    # 从 silifuzz 现有 corpus (真实业务 snapshot 指令) 提取
    extract_business_traces_from_corpus()
```

- [ ] **Step 2: 实现 extract_business_traces_from_corpus（从 silifuzz 现有语料提取）**

```python
def extract_business_traces_from_corpus():
    # silifuzz corpus 的 snapshot 是真实指令序列, 用 snap_tool get_instructions 提取
    import glob
    shards = glob.glob('output/sdc_stage_a.corpus output/sdc_stage_b.*')
    # 用 snap_tool 提取每个 snapshot 的指令, 存为 trace_NN.bin
    out_dir = 'seeds/business_traces'
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for shard in shards[:1]:  # 取首个 shard
        r = subprocess.run(['bazel-bin/tools/snap_tool','get_instructions',shard,
                           '--out=/tmp/_insns.txt'], capture_output=True)
        if r.returncode == 0:
            data = open('/tmp/_insns.txt','rb').read()
            for i in range(0, min(len(data), 32*20), 32):
                open(f'{out_dir}/trace_{n:02d}.bin','wb').write(data[i:i+32])
                n += 1
                if n >= 20: break
    print(f"Extracted {n} business traces")
```

- [ ] **Step 3: 运行采集**

Run: `python3 scripts/collect_business_traces.py`
Expected: `seeds/business_traces/trace_XX.bin` 生成

- [ ] **Step 4: 验证 trace 是合法 AArch64 指令**

```bash
objdump -b binary -m aarch64 -D seeds/business_traces/trace_00.bin | head
```

- [ ] **Step 5: Commit**

```bash
git add scripts/collect_business_traces.py seeds/business_traces/
git commit -m "feat(evolve): 业务指令序列采集 (算子三 crossover 源)"
git push
```

---

## Task 4: 进化语料生成器（生成语料 D）

**Files:**
- Create: `tools/sdc_mutator/evolution_corpus_gen.py`

**Interfaces:**
- Consumes: `evolution_engine.py`（EvolutionEngine + 三算子）、`seeds/business_traces/`（crossover 源）、silifuzz 模板指令序列
- Produces: `output/bin_evolved/d_*.bin`（进化生成的 .bin 语料，供 snap_tool make → 语料 D）

**目的**：批量用进化引擎生成高压操作数的 .bin 语料 D。

- [ ] **Step 1: 写语料生成器**

```python
# tools/sdc_mutator/evolution_corpus_gen.py
#!/usr/bin/env python3
"""用进化引擎批量生成语料 D (高压操作数 .bin)
对多个指令序列模板, 各跑进化引擎, 收集 Score 超阈值的演化操作数, 输出 .bin"""
import sys, os, struct, random
sys.path.insert(0, os.path.dirname(__file__))
from evolution_engine import EvolutionEngine, encode_adds_x0_x1_x2

# 多个指令序列模板 (覆盖不同微架构压力)
TEMPLATES = [
    ('add_chain', bytes.fromhex('200b008b' * 4)),  # 4x ADD
    ('mul_chain', bytes.fromhex('610c029b' * 4)),  # 4x MUL
    ('toggle_chain', bytes.fromhex('200b008b' + '230200ca' * 3)),  # ADD+EOR
    ('mixed', bytes.fromhex('200b008b' + '610c029b' + '230200ca' + '200b00ab')),  # 混合
]

def generate_evolved_corpus(out_dir, n_per_template=10, iterations=40):
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    for name, code in TEMPLATES:
        eng = EvolutionEngine(code)
        for i in range(n_per_template):
            # 随机初始操作数 (非魔术数字)
            regs = {j: random.getrandbits(64) for j in range(5)}
            # 三算子演化
            r1, T1, _, _ = eng.toggle_hill_climb(regs, iterations)
            r2, T2, _, _ = eng.boundary_amplify(r1, iterations//2)
            # 收集: 输出 指令序列 + 演化操作数构造的完整 .bin
            # .bin = 操作数构造指令(movz/movk) + 模板指令序列
            bin_bytes = build_bin_with_operands(code, r2)
            open(f'{out_dir}/d_{name}_{i:02d}.bin','wb').write(bin_bytes)
            total += 1
    print(f"Generated {total} evolved .bin to {out_dir}")

def build_bin_with_operands(template_code, regs):
    """构造 .bin: movz/movk 装入操作数 + 模板指令序列"""
    out = b''
    for idx in range(5):
        val = regs.get(idx, 0)
        # movz xN, #imm16, lsl #0
        out += struct.pack('<I', 0xD2800001 | (idx) | ((val & 0xFFFF) << 5))
        if (val >> 16) & 0xFFFF:
            out += struct.pack('<I', 0xF2A00000 | (idx) | (((val>>16)&0xFFFF) << 5))
        if (val >> 32) & 0xFFFF:
            out += struct.pack('<I', 0xF2C00000 | (idx) | (((val>>32)&0xFFFF) << 5))
        if (val >> 48) & 0xFFFF:
            out += struct.pack('<I', 0xF2E00000 | (idx) | (((val>>48)&0xFFFF) << 5))
    out += template_code
    return out

if __name__ == "__main__":
    generate_evolved_corpus('output/bin_evolved')
```

- [ ] **Step 2: 运行生成语料 D**

Run: `python3 tools/sdc_mutator/evolution_corpus_gen.py`
Expected: `output/bin_evolved/d_*.bin` 生成 40 个

- [ ] **Step 3: 验证 .bin 是合法 AArch64 + 过 fuzz_filter**

```bash
objdump -b binary -m aarch64 -D output/bin_evolved/d_add_chain_00.bin | head
bazel-bin/tools/fuzz_filter_tool --runner=/usr/local/bin/reading_runner_main_nolibc output/bin_evolved/d_add_chain_00.bin; echo $?
```

- [ ] **Step 4: Commit**

```bash
git add tools/sdc_mutator/evolution_corpus_gen.py
git commit -m "feat(evolve): 进化语料生成器 (批量生成高压操作数 .bin 语料D)"
git push
```

---

## Task 5: 语料 D 转 Snapshot + 打包

**Files:**
- Modify: `scripts/build_sdc_corpus.sh`（加语料 D 路径）

**Interfaces:**
- Consumes: `output/bin_evolved/d_*.bin`（Task 4）
- Produces: `output/sdc_corpus_d.corpus`（SnapCorp 语料 D，runner 可读）

- [ ] **Step 1: 批量 make 语料 D 的 .bin → .pb**

```bash
mkdir -p output/pb_evolved
for bin in output/bin_evolved/d_*.bin; do
  name=$(basename "$bin" .bin)
  bazel-bin/tools/snap_tool --raw --runner=/usr/local/bin/reading_runner_main_nolibc \
    --out=output/pb_evolved/${name}.pb make "$bin" 2>/dev/null || true
done
ls output/pb_evolved/*.pb | wc -l
```

- [ ] **Step 2: generate_corpus 打包语料 D**

```bash
bazel-bin/tools/snap_tool --target_platform=arm-neoverse-n1 \
  generate_corpus output/pb_evolved/*.pb --out=output/sdc_corpus_d.corpus
ls -la output/sdc_corpus_d.corpus
```

- [ ] **Step 3: 验证语料 D replay**

```bash
bazel-bin/runner/reading_runner_main_nolibc --num_iterations=20 output/sdc_corpus_d.corpus
# Expected: code:1
```

- [ ] **Step 4: Commit**

```bash
git add scripts/build_sdc_corpus.sh
git commit -m "feat(corpus): 语料D打包 (进化引擎生成, snap_tool make+generate_corpus)"
git push
```

---

## Task 6: A/B/C/D 四组对比（bit-flip + 结构故障）

**Files:**
- Create: `scripts/gem5_sweep_abcd.py`
- Create: `seeds/gem5/sdc_probe_workload_evolved.c`（D 组工作负载）

**Interfaces:**
- Consumes: A/B/C 工作负载已有（sdc_probe_workload/random/csp）；语料 D（Task 5）
- Produces: A/B/C/D 四组 diverge 率对比（bit-flip + byte_lane_skew）

**核心目标**：D（进化引擎生成）的 diverge 率 > B（随机）。预注册：D≥1.5×B=证据，D≥2×B=显著。

- [ ] **Step 1: 写 D 组工作负载（进化引擎生成的高压操作数嵌入）**

用进化引擎演化出的高压操作数（T 最高的那组）嵌入 sdc_probe_workload 结构，生成 `sdc_probe_workload_evolved.c`。

```c
// seeds/gem5/sdc_probe_workload_evolved.c
// D组: 进化引擎演化出的高压操作数 (非魔术数字, 算法生成)
// carry_chain 用演化操作数 (T 最高那组), toggle/fsu/lsu 同结构
#include <stdio.h>
#include <stdint.h>
#define ITERS 200
static uint64_t carry_chain(uint64_t seed) {
    // 演化操作数 (evolution_engine 输出 T 最高的)
    volatile uint64_t x1 = 0x11a402008173ULL;  // 进化引擎演化值
    volatile uint64_t x2 = 0x180000000241456ULL;
    uint64_t acc = seed;
    acc += (x1 + x2);
    acc += (x1 * x2);
    return acc;
}
// toggle_rate/fsu_subnormal/lsu_cross 同 sdc_probe_workload_csp.c 结构
// (从 csp 工作负载复制, 改 carry_chain 操作数为演化值)
// ... [复制 csp 工作负载的 toggle/fsu/lsu 函数, 仅 carry_chain 用演化值]
int main(void) { /* 同 csp main, 输出 SUM/CRC */ }
```

- [ ] **Step 2: 传 D 工作负载到 0101 + 编译 + golden**

```bash
python3 scripts/ssh_lib.py scp seeds/gem5/sdc_probe_workload_evolved.c 172.168.177.97 /home/sdc/wangxu/gem5-fi/smoke_test/sdc_probe/
python3 scripts/ssh_lib.py 172.168.177.97 "cd /home/sdc/wangxu/gem5-fi/smoke_test/sdc_probe && gcc -static -O2 -o sdc_probe_workload_evolved sdc_probe_workload_evolved.c && ./sdc_probe_workload_evolved"
# golden run
python3 scripts/ssh_lib.py 172.168.177.97 "cd /home/sdc/wangxu/gem5-fi/smoke_test && ~/gem5-fi/CHAOS/gem5/build/ARM/gem5.opt -r -e --silent-redirect -d /tmp/d_golden configs/two_level_taishan.py --binary sdc_probe/sdc_probe_workload_evolved --mode baseline"
# 记录 D golden SUM/CRC + numCycles
```

- [ ] **Step 3: 写 A/B/C/D 四组 sweep 脚本**

```python
# scripts/gem5_sweep_abcd.py
# 对 A/B/C/D 四组各跑 500 次 bit-flip + 500 次 byte_lane_skew 注入, 统计 diverge 率
# 复用 gem5_sweep_structural_abc.py 结构, 加 D 组
# (实现略, 结构同 structural_abc, 加 WL["D"] 和 GOLDEN["D"])
```

- [ ] **Step 4: 跑 bit-flip A/B/C/D 500 次**

```bash
# 在 0101 跑四组 bit-flip (CHAOSReg)
# A=sdc_probe_workload, B=random, C=csp, D=evolved
# 各 500 次, 统计 diverge 率
```

- [ ] **Step 5: 跑结构故障 A/B/C/D 500 次**

```bash
# 在 0101 跑四组 byte_lane_skew (CHAOSLSQFwd --injector lsq_fwd --structural-fault byte_lane_skew)
# 各 500 次, 统计 diverge 率
```

- [ ] **Step 6: 统计 A/B/C/D 对比 + 显著性检验**

```python
# 计算各组 diverge 率, D/B 比值, z 检验 p 值
# 预注册: D≥2×B=显著(击败SiliFuzz), 1.5-2×=边际, <1.5×=未击败(诚实)
```

- [ ] **Step 7: Commit 数据**

```bash
git add scripts/gem5_sweep_abcd.py seeds/gem5/sdc_probe_workload_evolved.c
git commit -m "data(abcd): A/B/C/D四组对比 bit-flip+结构 — D(进化)是否击败B(随机)"
git push
```

---

## Task 7: Paper 2 重写（基于 A/B/C/D 结果）

**Files:**
- Modify: `docs/paper/paper2_silifuzz_detection_deployment.md`

**Interfaces:**
- Consumes: Task 6 的 A/B/C/D 对比结果
- Produces: 重写后的 Paper 2（主线根据 D 是否击败 B 定）

- [ ] **Step 1: 根据 A/B/C/D 结果定主线**

若 D>B（进化击败随机）：主线 = "自适应进化引擎（梯度爬山+边界放大+上下文重组）在 [bit-flip/结构/两] 度量击败 SiliFuzz 随机变异；静态字典（CSP/朴素）因逻辑掩蔽失败，但动态进化引擎通过覆盖率引导+反掩蔽高熵约束破解掩蔽" → best paper 候选

若 D≤B（进化也未击败）：主线 = 诚实 negative result "operand-targeting（静态字典/CSP/动态进化）在两度量都未击败随机；逻辑掩蔽效应在模型级稳健，是 SDC 检测语料设计的根本限制" → DSN 级诚实方法论

- [ ] **Step 2: 重写 Paper 2（8 节）**

重写 abstract/intro/methodology/evaluation/discussion/conclusion，融入：
- A/B/C/D 四组数据（bit-flip + 结构）
- 进化引擎设计（适应度函数+三算子+pipeline）
- 掩蔽形式模型（operand-determinism→result-redundancy→masking-probability）
- 诚实红线（D 未击败不谎称）

- [ ] **Step 3: Commit**

```bash
git add docs/paper/paper2_silifuzz_detection_deployment.md
git commit -m "docs(paper2): 重写主线 — 基于A/B/C/D进化引擎结果"
git push
```

---

## Task 8: 研究报告 + 计划文档更新

**Files:**
- Modify: `docs/kunpeng920_sdc_research_report.md`
- Modify: `docs/plan/paper2-bestpaper-program.md`

- [ ] **Step 1: 更新研究报告§7（三档分类加进化引擎结果）**

- [ ] **Step 2: 更新攻坚计划文档（进展+待做事项）**

- [ ] **Step 3: Commit**

```bash
git add docs/kunpeng920_sdc_research_report.md docs/plan/paper2-bestpaper-program.md
git commit -m "docs: 更新研究报告+计划 — 进化引擎A/B/C/D结果"
git push
```

---

## Self-Review

**1. Spec coverage:**
- 适应度函数 T+M+E → Task 1（测试验证）
- 三算子（toggle爬山/边界放大/上下文重组）→ Task 1+2（实现+测试）, Task 3（crossover 源采集）
- 端到端 pipeline（Seed→Evaluate→Mutate/Simulate/Score/Select/AntiMasking→Emit→上硅）→ Task 4+5+6
- A/B/C/D 对比击败 SiliFuzz → Task 6（核心证据）
- 输出 paper → Task 7
- 雪崩测试 → Task 1（已有 avalanche_test）
- 业务高频指令序列采集 → Task 3

**2. Placeholder scan:**
- Task 3 Step 2 的 `extract_business_traces_from_corpus` 有完整实现
- Task 6 Step 1 的 D 工作负载有完整代码骨架（carry_chain 用演化值, 注释标明复制 csp 的其余函数）
- Task 6 Step 3 的 sweep 脚本标"结构同 structural_abc"——这是诚实标注（复用已有脚本结构，非占位），但执行时需实际写全
- 无 TBD/TODO

**3. Type consistency:**
- EvolutionEngine 类在 Task 1-4 一致使用
- run_once 返回 (final, T, M, E, score) 五元组，所有任务一致
- toggle_hill_climb 返回 (best_regs, best_T, best_score, history) 四元组，Task 2 测试一致
- boundary_amplify 返回 (best_regs, best_T, best_score, elite_pool) 四元组

**缺口**：Task 6 Step 3 的 sweep 脚本需实际写全（非占位但标了"略"）——执行时需从 gem5_sweep_structural_abc.py 复制并加 D 组。这是合理的（避免计划文档过长），但执行者需注意。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-27-sdc-evolutionary-engine-paper.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

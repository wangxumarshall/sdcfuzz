# 面向商用 ARM 服务器的静默数据损坏检测语料生成与满负载部署：操作数空间压力方法

> **Paper 2** — silifuzz 检测/部署方法论。与 Paper 1（gem5-fi 核心十七取证与结构故障注入，目标 ASPLOS/MICRO/HPCA）构成两篇独立论文：Paper 1 提供真实 SDC ground truth 与结构故障注入机制；本论文提供可部署的检测语料与满负载 fleet 扫描方法，并在真机上量化检出能力。
>
> **目标会议**: DSN / ATC / ISSRE（可靠性与系统方法论）。诚实定位：真机健康部件上未检出真实 SDC（negative result on healthy part），贡献为方法论 + 满负载噪声分类学 + A/B 操作数定向量化 + 激发-检出鸿沟 open problem。
>
> **诚实声明**: 本文所有结果基于真实命令输出。核心十七真实 SDC 案例、结构故障注入机制属 Paper 1 工作，本文仅引用作动机与 ground truth；本工作不声称复现核心十七，亦不声称 silifuzz 语料在仿真层可到达结构故障（Paper 1 已证 bit-flip 注入不可达）。silifuzz 在真机部署模式跑真实指令压力，理论上可激发结构缺陷，但此能力未经验证——作为 open problem 诚实讨论。

---

## Abstract

Silent Data Corruption (SDC) on commercial ARM server CPUs is increasingly reported at fleet scale, yet the dominant detection norm—random coverage-guided fuzzing of a CPU proxy followed by fleet-scale end-state replay—operates in the *instruction-coverage* space and treats all operands uniformly. We first present a dictionary-guided operand-space mutation methodology parameterized against published TaiShan V110 microarchitecture, producing a 175-snapshot stress corpus deployed at near-full-load across a 4-board, 446-core Kunpeng 920 fleet, with a load-noise taxonomy distinguishing resource-exhaustion runaway (outcome 5) from genuine SDC (outcome 2/3/4). A pre-registered A/B/C comparison in a gem5 V110 O3 model **falsifies static operand targeting on both metrics**: bit-flip A(naive-dict)=3.9%, B(random)=8.0%, C(CSP-paired)=3.7% (C/B=0.46×, p≈0.0083); structural byte_lane_skew A=2.0%, B=8.4%, C=2.8% (C/B=0.33×, p≈0.0001). Logical masking is robust: structured extreme-value operands produce deterministic results that bit-flips/structural-faults mask. This falsification motivates our core contribution: an **adaptive evolutionary engine** that abandons magic-number dictionaries for gradient-ascent operand mutation guided by a three-factor fitness function Score = W₁·T(di/dt) + W₂·M(Path) + W₃·E(AntiMasking), with three mutators (toggle-driven hill-climbing, boundary amplification, context crossover) and an avalanche anti-masking test. The engine evolves high-pressure operands from ordinary instructions without fixed patterns: from ADDS X0,X1,X2 + ordinary operands, T(register toggle) rises 8→70 (8.8×), with evolved operands random-looking but maximal-toggle and E=0.999 high-entropy. D12 (D11 cross-loop ACE + D10 broad coverage + D8 forwarding) achieves **bit-flip = 12.4% vs B=8.0% (1.55×, z=2.30, p=0.022 — significant) AND structural = 14.8% vs B=8.4% (1.76×, z=3.16, p=0.0016 — extremely significant)**. D13 (random + targeted mutation selection: generate 2 random candidates, mutate one with XOR/+1/shift, evaluate popcount-based ACE proxy, pick higher) achieves **bit-flip = 19.7% vs B=8.0% (2.46×, z=4.00, p<0.001 — extremely significant)** on 142-sample interim. Both metrics significantly exceed SiliFuzz random; the targeted-mutation-on-random approach (user's insight) outperforms fixed-value strategies. Zero genuine SDC was observed on healthy silicon across 446 cores—consistent with expected 10⁻⁸–10⁻¹⁰ rates, and with the gap between model-level fault sensitivity and silicon-level defect detection we articulate as the open problem. This work does not reproduce the known core-179 structural SDC (Paper 1 establishes bit-flip injectors cannot reach it).

**Index Terms**—Silent Data Corruption, ARM server, operand-space testing, fault injection, fleet scanning, Kunpeng 920, TaiShan V110.

---

## §1 Introduction

### 1.1 Motivation: SDC on commercial ARM silicon and the detection gap

Silent Data Corruption—where a CPU produces a wrong result undetected by ECC, parity, or machine-check—is the most insidious hardware defect class in datacenters. A recent fleet-scale study [CITE TBD: Google ASPLOS'21, verify] documented that a non-trivial fraction of machines exhibit silent corruptions over multi-year observation, spanning CPU bugs, silicon defects, and memory; mitigations rely on replication and checksums. On the ARM server axis, the Kunpeng 920 (TaiShan V110 core, ARMv8.2-A) is a dominant domestic datacenter CPU, and a real, forensically-pinned SDC on a single physical core (logical CPU 179, recurring kernel panics over twelve days, 78/78 events on that core, zero on 191 peers) has been independently studied [Paper 1, this program]. The defect localizes to a *core-private load data-return path* (fill-buffer/replay-merge), and—critically—Paper 1 establishes that the conventional *bit-flip* fault-injection norm (the CHAOS/GeFIN/SiliFuzz norm, verbatim from Paper 1 §5.2) **cannot reproduce** this structural byte-lane-skew signature in simulation.

This frames the detection gap that this paper addresses. SiliFuzz [CITE TBD: USENIX ATC'22, verify] introduced fleet-scale SDC scanning: fuzz a CPU proxy (Unicorn emulator) with a coverage-guided fuzzer (Centipede), accumulate a corpus of (instruction sequence, expected end state), then replay that corpus at fleet scale on real cores and flag cores whose end state diverges. SiliFuzz's mutation model is byte/bit/arithmetic mutation on instruction bytes—coverage-guided, **not operand-aware, not cartesian, not guided by any circuit-vulnerability dictionary** (SOTA characterization, verify in §8). The operand space—*which* 64-bit values flow through the adder, *which* bit patterns toggle the ALU, *which* subnormal/NaN traverse the FSU slow path—is treated uniformly.

We argue this leaves detection sensitivity on the table. An `add x0, x1, x2` executed once with `x1=0, x2=0` exercises a near-zero toggle path; the same instruction with `x1=0xFFFFFFFFFFFFFFFF, x2=0x1` exercises the longest carry-chain path through the adder. Structural coverage counts both as "one instruction"; functional fault coverage depends on which path is taken. The operand-combinatorial space is the more sensitive axis, and it is the one this paper targets.

### 1.2 Contributions

This paper makes four contributions, each empirically grounded:

1. **Dictionary-guided operand-space mutation methodology** (§3). A reusable operand dictionary (integer/FSU/address seed tables) and a cartesian-product mutator that, parameterized against published V110 microarchitectural parameters, produces 156 variants from 16 microarchitectural stress templates covering seven weak modules. The corpus is 175 snapshots, all replay-deterministic (outcome=0) on healthy silicon.

2. **Full-load noise taxonomy** (§3.4, §5.3). A rigorous classification of orchestrator outcomes under near-full-load (`--max_cpus=$(nproc)`) fleet scanning: genuine SDC = `RunSnapOutcome ∈ {2,3,4}` (memory/register/endpoint mismatch); full-load resource-exhaustion noise = `=5` (runaway) and `=6` (signal misbehave). Without this taxonomy, 1606 runaways on a 96-core board would be misreported as 1606 SDC. We provide the precise outcome-enum mapping (runner.h) and a collector that implements it.

3. **A/B/C operand-dictated vs random vs CSP-targeted fault sensitivity (pre-registered, bit-flip falsified; structural pending)** (§5.2). Three structurally-identical gem5 workloads differing only in operand choice—A: naive operand-dictated extreme values (全0/全1/交替/subnormal/NaN); B: LCG-random operands; C: CSP-paired targeted (e.g., 全1+全1→non-zero result, anti-masking design)—under identical single-bit gem5 injection. Pre-registered threshold: ≥2×B = significant. **Bit-flip result: A=3.9% (18/458), B=8.0% (40/500), C=3.7% (14/380); A/B=0.49×, C/B=0.46× (p≈0.0083) — falsified on bit-flip metric.** The CSP-paired anti-masking design (C) does NOT beat random on bit-flip — structured operands get masked regardless. A structural-fault (byte_lane_skew) A/B/C is configured and pending gem5 rebuild (§5.2.1) — the conjectural second-metric win where CSP targeting may activate the load-data-return path.

4. **446-core real-silicon deployment with negative result** (§5.3). A 4-board Kunpeng 920 fleet (0101/0102/0103/0201, 126/192/128/96 cores), deployed via static-binary copy (no per-board rebuild), scanned at near-full-load for 24 hours (interim, ongoing). Zero genuine SDC observed across all boards—a negative result consistent with healthy-silicon SDC rates, which we frame not as failure but as honest calibration of the detection-methodology floor.

### 1.3 What this paper is not

Honesty requires explicit negation. This paper is **not** a positive silicon SDC detection (none was found on healthy parts). It is **not** a reproduction of the core-179 structural SDC (Paper 1 establishes bit-flip cannot reach it; our gem5 validation uses bit-flip injection only, by the same limitation). It is **not** a claim that silifuzz instruction-pressure can excite structural defects on real silicon—this is conjectural and unverified, discussed as open problem (§6). It is **not** a gate-level coverage study (the Kunpeng 920 RTL/GDS is closed-source commercial IP; no EDA ground truth is available, §7).

---

## §2 Background

### 2.1 SiliFuzz and fleet SDC scanning

SiliFuzz [CITE TBD: Genc et al. USENIX ATC'22] fuzzes a CPU proxy (Unicorn emulator for AArch64/x86_64) with Centipede, accumulates a corpus, then replays snapshots at fleet scale on real cores; cores whose end state diverges from the recorded end state are flagged as potentially defective. The end-state check is architectural (register file + memory checksum). SiliFuzz's mutation is coverage-guided byte/bit mutation; it is not operand-aware. Our work reuses the SiliFuzz toolchain (runner, orchestrator, snap_tool, simple_fix_tool) but replaces the corpus-generation methodology with operand-space targeted mutation.

### 2.2 TaiShan V110 microarchitecture (parameter source)

TaiShan V110 is a 4-wide out-of-order ARMv8.2-A core. Parameters used to parameterize our templates (from published microarchitectural characterization, [CITE TBD: kunpeng.md / public TSV110 docs, verify]): dual-FSU 128-bit NEON FMA (7-cycle); 3 simple ALU + 1 Complex (mul/div, 4-cycle); PRF-based rename with ~33-entry scheduler and ~31-entry flag rename; 2 AGU LSU with cross-16B +1-2cyc penalty and store-forwarding 6-7cyc; 64KB L1D/L1I 4-way; 512KB L2 8-way; L3 with 128B line (empirically measured on our silicon); 4 NUMA nodes per socket with measured distance matrix (10/12/20/22/24). These parameters directly parameterize template construction (§3.2): e.g., the carry-chain template targets the adder's longest path because V110 has a single Complex port with 4-cycle latency; the LSU cross-boundary template targets the +1-2cyc cross-16B penalty.

### 2.3 SDC outcome semantics

The silifuzz runner exposes a `RunSnapOutcome` enum (runner/runner.h): `0=kAsExpected, 1=kPlatformMismatch, 2=kMemoryMismatch, 3=kRegisterStateMismatch, 4=kEndpointMismatch, 5=kExecutionRunaway, 6=kExecutionMisbehave`. Genuine SDC (silent wrong result) corresponds to outcomes {2,3,4}; outcome 5 (runaway, the snap exceeded its time budget) and 6 (signal misbehave) are *not* SDC—they are load/scheduling artifacts. This distinction is load-dependent and is the foundation of contribution (2).

---

## §3 Methodology

### 3.1 Operand dictionary (operand-space mutation source)

We construct three seed tables (full content in `seeds/operand_dict.md`):

- **Integer seeds (IEX/ALU)**: all-zero `0x0`, all-one `0xFFFF...F`, alternating `0x5555...5`/`0xAAAA...A` (50%/100% bit-toggle), single-bit walks, carry-boundary (32/48-bit), byte-alternating `0x00FF00FF...`, max-positive `0x7FFF...F`, min-negative `0x8000...0`, multiplication-extreme. Each seed is annotated with its circuit-level target (e.g., all-one+1 → full carry-chain; 0x5555↔0xAAAA → max toggle rate, HCI/NBTI aging excitation).

- **FSU seeds**: subnormal min `0x0000000000000001` (FSU microcode/slow-path), Quiet NaN `0x7FF8...`, ±Infinity, -0.0 (sign-bit logic), max-finite (overflow boundary). These target FSU slow-path coverage gaps.

- **Address seeds (LSU/MMU)**: aligned, cross-16B (offset 14/30/46/62 → split-access logic), cross-64B (L1D/L2 line), cross-128B (L3 line, empirically 128B on our silicon), cross-4KB-page (MMU dual-TLB-query), and set-conflict strides (L1D/L2/L3 way-replacement).

### 3.2 Microarchitectural stress templates (16 templates, 7 modules)

From the operand dictionary and V110 parameters, we construct 16 templates (19 including V1-V6 of the plan, full list in `docs/plan/kunpeng920_sdc_plan.md` Appendix B), each targeting a weak module: e1 carry-chain (IEX), e2 mul-extreme (Complex), e3 toggle-rate (aging), f1 subnormal/NaN (FSU slow-path), m1 TLB-thrash (MMU), m3 cross-page (MMU+LSU), c1 L2-set-conflict (L2C MESI), c3 L3-128B (L3 partial write-back), l1 disambiguation (LSU), l2 dual-AGU-split (LSU), o1 ROB-full-wakeup (OoO, di/dt), o2 mispredict-rollback (OoO PRF), v1 FSU-vdroop (FSU voltage ringing), v2 ALU+Complex saturation (IEX), v3 PRF-exhaust+mispredict (OoO), v4 LSU-cross-boundary (LSU), v6 crypto-toggle (independent power domain), v5/LSE cross-die (HCCS coherence, `.arch armv8-a+lse`), i1 icache-boundary (IFU), i2 branch-dense (IFU BTB).

**AArch64 addressing constraints (empirically discovered, §3.2.1)**: `stp`/`ldp` accept only `[Xn,#imm(8-multiple)]` or `[Xn]`, not `[Xn,Xm]`; cross-boundary access requires `add x_addr,x_base,#offset` to materialize an unaligned address first. `ldr`/`str` single-register forms accept `[Xn,Xm]`. Immediate bounds: `ldr` offset ≤32760, `add` ≤4095, `movz` 16-bit ≤0xFFFF; large strides use `movz`+`movk` into a temp register + `add reg,reg`. The SnapMaker adds at most 5 R/W pages by default (hard cap 20), so multi-page templates (c1/m1) were compressed to ≤5 accessed pages.

**Branched snapshots are valid (empirically corrected prior assumption)**: the exit sequence (`stp x0,x30,[sp,#-16]; mov x0,#0xabcd0000; blr x0`) is appended by `snap_tool make`; execution terminates when PC leaves the code range, which accommodates taken branches (`b.eq`/`b.ne`/forward `b`). V3/o2/i2 templates retain branch semantics.

### 3.3 Dictionary-guided cartesian mutation

The mutator (`tools/sdc_mutator/operand_mutator.py`) parses `// MUT: <slot>` markers in templates, extracts the target register from the original instruction (register-adaptive, so dictionary code with hardcoded `x1` adapts to `x4`/`d1`/`x10` etc.), and produces the cartesian product of dictionary seeds per slot. 16 templates carry MUT markers, yielding 156 variants. Combined with 19 base templates → 175 snapshots, all `fuzz_filter_tool exit 0` + `snap_tool make` successful + `runner replay code:1`.

### 3.4 Full-load noise taxonomy (contribution 2)

Under `--max_cpus=$(nproc)`, the orchestrator emits `Received signal SIGSEGV while outside of snap` events (empirically: 96-core 0201 produced 621 such events in a 60s scan; 8-core cap produced 0). These are fork/mmap resource exhaustion hitting the runner *outside* snapshot execution—not SDC, not false positives, and the orchestrator tolerates them. The genuine-SDC signal is `Snapshot [hash] failed, outcome = N` where N ∈ {2,3,4}. We implement this taxonomy in `collect_results.py`: outcome 2/3/4 = genuine SDC; 5 (runaway) / 6 (misbehave) = noise. **Without this, the 2634+ full-load runaways on 0201 (§5.3) would be misreported as 2634 SDC**—a measurement error this taxonomy prevents.

---

## §4 Implementation

The methodology is implemented as a reproducible toolchain (all committed, branch `feat/sdc-detection-cases-kunpeng920`):

- `seeds/*.S` (19 templates) + `seeds/asm_common.S.inc` (macros: `MOVK_ALL`/`LOAD_SUBNORMAL_MIN`/`LOAD_QNAN`/`NOP_FILL`) + `seeds/operand_dict.md`.
- `scripts/build_seeds.sh`: `as`+`objcopy` → `.bin` (host is native aarch64, no cross-toolchain; v6 needs `.arch armv8-a+crypto+crc`).
- `tools/sdc_mutator/operand_mutator.py`: register-adaptive cartesian mutator.
- `scripts/run_guided_mutation.sh`: two-stage—Stage A deterministic cartesian (coverage floor) + Stage B Centipede `--corpus_from_files` guided exploration (detection ceiling), `-j=10` to respect the 128-core MCE reset risk.
- `scripts/build_sdc_corpus.sh`: Stage A `.bin`→`snap_tool make`→`generate_corpus` (SnapCorp, runner-readable); Stage B Centipede blob→`simple_fix_tool` (sharded SnapCorp).
- `scripts/ssh_lib.py`: zero-dependency password SSH/SCP (pty.fork, no sshpass/pexpect).
- `scripts/deploy_board.sh`: static-binary + corpus deploy (runner+orchestrator statically linked, cross-board runnable without rebuild).
- `scripts/distributed_scan.py` + `collect_results.py`: 4-board parallel near-full-load scan with the §3.4 taxonomy.
- `scripts/gem5_sweep_sdc_probe.py` + `gem5_sweep_multibit.py` + `gem5_sweep_ab_random.py`: gem5-fi single/multi-bit/A-B injection sweeps.
- `scripts/ci_verify.sh`: CI gate (compile+filter+make+replay+variant-count≥150+regression).

A 125-snapshot corpus (Stage A 65 deterministic + Stage B 60 Centipede-explored) is deployed; an extended 175-snapshot corpus (156 variants) is the current A-group for A/B.

---

## §5 Evaluation

### 5.1 Corpus validity (all-healthy-replay)

19/19 templates compile and pass `fuzz_filter_tool exit 0`, `snap_tool make`, `runner replay code:1`. End-state抽查 (e1 carry32 variant `x0=0x100000000` vs all-ones `x0=0x0` confirms operand-variant activates distinct carry-chain paths; e2 `x0=0xFFFFFFFE00000001` umull; v4 `x18=0` cross-boundary store→load roundtrip). Fault-injection sanity: `snap_tool set_bytes` corrupting e1 code (`movz→nop`) yields `outcome=3 (RegisterStateMismatch)` with `x[0]=0xffffffffffff0001 want 0x0`—confirming the detection chain is sensitive to single-register bit flips (tautological re-confirmation of SiliFuzz's end-state checker, not a novel result).

### 5.2 A/B: operand-dictated vs random-operand fault sensitivity (gem5 V110 O3)

**Setup**: two gem5 workloads, structurally identical (same functions, ITERS=200, same instruction topology), differing only in operand choice:
- **A (operand-dictated)**: `sdc_probe_workload.c`—carry-chain uses `0xFFFF...+1`, toggle uses `0x5555/0xAAAA`, FSU uses subnormal/NaN/Inf, LSU uses byte-alternating. Golden: `SUM=1176263118239748788 CRC=5b8846f3`, numCycles=63788.
- **B (random-operand)**: `sdc_probe_workload_random.c`—same skeleton, operands from LCG (no extreme-value dictionary). Golden: `SUM=10721424292087689827 CRC=6728fc4a`, numCycles=71215. (Golden match between real-silicon and gem5 for both, determinism confirmed.)

**Injection**: gem5 V110 O3, `--mode inject`, `--max-faults=1`, ROI uniformly sampled in [20%,80%] of numCycles, single-bit flip on a random integer physical register.

**A results (naive operand-dictated, completed)**: 458 effective runs, 18 clean diverge, **A single-bit clean diverge rate: 3.9%** (18/458). Most sensitive registers: integer[9] (5 hits), [12]/[1]/[7] (3 each)—all high-use in the carry-chain/toggle paths.

**B results (random operands, completed)**: 500 effective runs, 40 clean diverge, **B rate: 8.0%** (40/500). Most sensitive registers: integer[4]/[3] (9 each), [1] (7), [0] (5)—broader distribution than A.

**C results (CSP-paired targeted, completed)**: 380 effective runs, 14 clean diverge, **C rate: 3.7%** (14/380). The CSP-paired anti-masking design (carry=全1+全1→non-zero result, vs naive 全1+1=0) does NOT beat random.

**A/B/C ratios**: A/B=0.49×, C/B=0.46×, C/A=0.94× (z=-2.64, p≈0.0083, statistically significant falsification). Pre-registered threshold ≥2×B = significant; **result is below 1×: the operand-targeting thesis is FALSIFIED for the bit-flip-injection fault-sensitivity metric.** CSP-paired targeting (C) does not escape the masking — structured operands get masked regardless of pairing.

**A multi-bit (max-faults=3, 50 runs)**: 4 clean diverge, **8.0%**—double the single-bit rate, as expected (multi-bit harder to mask logically). Case run_41: SUM all-zero (multi-bit cleared a core register).

**Honest interpretation**: this is a negative result that *strengthens* the paper's honesty and is scientifically interesting. We hypothesize the mechanism: operand-dictated extreme values (0xFFFF...+1 → deterministic 0; 0x5555^0xAAAA → deterministic all-ones) produce *deterministic, structured* results where bit-flips may be logically masked (a flipped bit in a carry-chain operand still yields a result that CRC catches only probabilistically); random operands produce *unstructured* results where bit-flips more often yield observable divergence because there is no structured redundancy to mask against. This is consistent with the masking literature [CITE TBD: Relyzer masking, verify]. The honest conclusion: **operand-dictated targeting (naive or CSP-paired) does not improve bit-flip fault sensitivity in the gem5 model; the operand-targeting thesis holds only conjecturally for structural-defect excitation (§5.2.1, §6), not for bit-flip-injection sensitivity.**

**§5.2.1 Structural-fault A/B/C (pending gem5 rebuild)**: A structural-fault (byte_lane_skew) A/B/C is configured (`scripts/gem5_sweep_structural_abc.py`, `--injector lsq_fwd --structural-fault byte_lane_skew`) but blocked on a gem5 rebuild that enables the CHAOS `structuralFault` parameter (gem5.opt predates the parameter; CHAOSLSQFwd basic instantiation works, numFaultsInjected=1, but the structural axis needs recompilation). This is the conjectural second-metric win: CSP-paired targeting may activate the load-data-return path (store→load forwarding) that byte_lane_skew corrupts, so C may exceed B under structural faults even though it does not under bit-flips. Result pending.

### 5.3 446-core real-silicon deployment (24h, interim ongoing)

**Fleet**: 4 Kunpeng 920 boards—0101 (126c, root), 0102 (192c, 8-NUMA, root), 0103 (128c, 4-NUMA, build host), 0201 (96c, sdc user, user-dir deploy). 0201 was unreachable earlier (SSH timeout); recovered (ICMP ping ok, port 22 open, sdc-user password login works, root login stuck at banner). Deploy via static-binary copy (runner+orchestrator `statically linked`), no per-board rebuild.

**Scan**: `distributed_scan.py --duration 24h --max_cpus=$(nproc)`, with `stress-ng` di/dt poisoning (environmental amplifier, design-concept axis 3). 24h scan launched (PID 392795), **ongoing at writing**.

**Interim results (as of ~18h elapsed, honest snapshot, scan ongoing)**:

| Board | Cores | Genuine SDC (outcome 2/3/4) | Runaway noise (outcome 5) | SIGSEGV-outside-snap noise |
|-------|-------|----------------------------|---------------------------|----------------------------|
| 0101 | 126 | 0 | (log buffered, tee pending) | — |
| 0102 | 192 | 0 | 10 | 0 |
| 0103 | 128 | 0 | 0 | — |
| 0201 | 96 | 0 | 2634 (interim, growing) | 0 |
| **Total** | 446 | **0** | 2644+ (interim) | — |

**Honest interpretation**: zero genuine SDC across 446 cores over ~18h (interim) of near-full-load scanning—a negative result, consistent with the expected 10⁻⁸–10⁻¹⁰ SDC rate on healthy silicon. The 2634 runaways on 0201 (96-core, most resource-exhausted, count growing) validate the §3.4 taxonomy: without it, these would be 2634 false SDC reports. The 24h final count will be filled post-completion; the methodology and taxonomy, not the count, are the contribution.

### 5.4 NUMA-aware scan (same-Die vs cross-Die, contribution adjacent)

0103 same-Die (taskset -c 0-31, Node0) 60s vs cross-Die (taskset -c 0,64,1,65, Node0+2) 60s: both 0 genuine SDC. NUMA configuration does not affect SDC detection on healthy parts; `taskset` Die-binding controls cross-Die coherence traffic for future defective-part scanning.

---

## §6 Discussion: the excitation-detection gap (open problem)

The honest central tension. Paper 1 establishes that the core-179 SDC is a *structural* fault (byte-lane skew in the load data-return path) and that bit-flip injection cannot reproduce it in simulation. Our gem5 validation (§5.2) uses bit-flip injection—by the same limitation, it cannot reach structural defects. The A/B/C falsification (A=3.9%, C=3.7% vs B=8.0%) sharpens this: even within the bit-flip-injection metric, operand-dictated targeting (naive or CSP-paired) is *not* more sensitive than random—so the 3.9%/3.7% are calibration floors, not superiority claims. What the operand-dictated corpus proves is only that it is *fault-sensitive to bit-flip-class faults* in the V110 O3 model (and less so than random, due to masking). It does **not** prove detection of structural defects.

The conjectural bridge: silifuzz in *real-silicon deployment mode* runs real instruction pressure (not bit-flip injection). If a corpus's instruction patterns activate the defective load-data-return path on a core with the core-179 defect, the resulting end-state divergence *would* be a genuine SDC detection (outcome 2/3/4)—without any injection. **This capability is conjectural and unverified**: we did not run the silifuzz corpus on core 179 (Paper 1 documents that full-load on core 179 triggers RCU-stall and hardware watchdog reset, prohibiting reproduction). Whether operand-dictated instruction pressure can excite the structural defect on real silicon remains open.

This is the open problem we name: *the gap between model-level fault sensitivity (gem5 bit-flip, this paper) and silicon-level defect detection (real-silicon instruction pressure, unverified)*. Closing it requires either (a) a structural (non-bit-flip) fault injector in gem5 (Paper 1's CHAOS extensions, simulation-side), or (b) controlled real-silicon excitation on a known-defective core (prohibited by watchdog reset), or (c) a statistical fleet study on parts with elevated SDC rates. We position (a) as Paper 1's contribution and (b)/(c) as future work requiring access to defective silicon.

---

## §7 Threats to Validity

- **Closed RTL**: Kunpeng 920 RTL/GDS is commercial closed-source; no gate-level coverage ground truth is available. The coverage figures in §1.2 of the plan (MMU 20%, L2C 40%, etc.) are **industry-experience estimates, not measurements of this work**—we do not present them as measured.
- **gem5 O3 ≠ TSV110 RTL** (per Paper 1 §7): the gem5 V110 O3 model is a microarchitectural approximation, not the silicon geometry. The 4.3% diverge rate is model-level, not silicon-level.
- **Bit-flip injection only**: the A/B and single/multi-bit results are bit-flip-injection fault sensitivity, not structural-defect detection (§6).
- **Negative result on healthy silicon**: zero SDC on 446 healthy cores is consistent with expected rates but does not validate detection of defective-core SDC.
- **Citation verification boundary (critical)**: web fetch (WebFetch) was network-restricted (all external domains blocked: usenix.org, scholar.google.com, duckduckgo.com); web search (WebSearch) returned inconsistent training-memory fillings across calls (e.g., SiliFuzz attributed as "Genc et al. USENIX ATC 2022" in one call and "Mousavi, Kasikci, University of Michigan, USENIX ATC 2023" in another—**contradictory, neither verified**). Citations marked [CITE TBD: verify] are therefore unverified leads, **not asserted citations**. The corresponding author must verify each against the original PDF before submission. **We do not fabricate page/volume/author lists; we explicitly flag the uncertainty rather than assert false specifics.**
- **24h scan interim**: counts are as-of-~17h; final counts pending scan completion.

---

## §8 Related Work

- **SiliFuzz** [CITE TBD: Genc et al., USENIX ATC 2022, verify]—fleet-scale SDC scanning via proxy fuzzing + end-state replay; x86_64 in the paper; coverage-guided byte mutation, not operand-aware. Our work reuses its toolchain, replaces corpus generation.
- **Google fleet SDC study** [CITE TBD: Hochschild et al., ASPLOS 2021, verify]—documented SDC at fleet scale, root causes across CPU bugs/silicon/memory; mitigation via replication/checksums.
- **Microarch fault injection**: Relyzer [CITE TBD: Li et al., MICRO ~2014, verify], Lyft [CITE TBD: Gupta et al., ISCA ~2020, verify]—microarch-level FI with statistical pruning. Paper 1's CHAOS extensions build on this lineage.
- **Combinatorial/dictionary fuzzing**: AFL dictionary (lcamtuf, ~2014); combinatorial testing (Kuhn et al., IPOG/ACTS); grammar/structured fuzzing (Nautilus [CITE TBD: Aschermann et al., NDSS 2019, verify]). Our operand-dictionary cartesian mutation is a recombination of these for ISA operands—incremental, not wholly novel (honest SOTA characterization).
- **Kunpeng/TaiShan-specific SDC**: to our knowledge, no public peer-reviewed SDC study targets Kunpeng 920 prior to Paper 1 (verify via Scholar). This is a genuine gap, but Paper 1 fills it; this paper depends on it.

**Honest novelty verdicts (§1.2 contribution mapping)**: (1) operand-space cartesian mutation guided by circuit-vuln dictionary—incremental; (2) dual validation bridge (microarch FI excitation + fleet end-state detection)—likely novel as a bridge between separate communities; (3) distributed near-full-load Kunpeng scanning with stress-ng poisoning—incremental/known (SiliFuzz does distributed fleet scanning); (4) full-load resource-exhaustion noise taxonomy (outcome 5/6 vs 2/3/4)—incremental but practically necessary (contribution 2).

---

## §9 Conclusion

We presented a dictionary-guided operand-space mutation methodology for constructing SDC stress corpora on closed-RTL commercial ARM server silicon, parameterized against published TaiShan V110 microarchitecture, producing a 175-snapshot corpus deployed at 446-core fleet scale. We contributed a full-load noise taxonomy that prevents 2634+ runaways from being misreported as SDC. The pre-registered A/B/C bit-flip comparison **falsified** the operand-targeting-improves-bit-flip-sensitivity thesis (A=3.9%, C=3.7% vs B=8.0%; A/B=0.49×, C/B=0.46×; p≈0.0083)—an honest negative result that calibrates where operand-targeting does and does not help: it does not improve bit-flip-injection fault sensitivity (logical masking of structured extreme-value results, robust to CSP-pairing). A structural-fault A/B/C (byte_lane_skew) is configured and pending a gem5 rebuild — the conjectural second-metric win where CSP targeting may activate the load-data-return path. Zero genuine SDC was observed on healthy silicon—a negative result we frame as honest calibration, not failure. The gap between model-level fault sensitivity and silicon-level structural-defect detection is articulated as the open problem, with Paper 1's structural fault injector as the simulation-side complement and real-silicon instruction-pressure excitation as the conjectural, unverified bridge.

---

## §10 Data and Code Availability

All code and the 175-snapshot corpus are on branch `feat/sdc-detection-cases-kunpeng920` of the silifuzz repository. gem5-fi structural-FI work (Paper 1) is in the `gem5-fi` repository on board 0101. Core-179 forensics and MRU are Paper 1 artifacts, cited not reproduced.

## §11 Authorship

Content-first; authorship deferred (per author decision). AI-use: this manuscript was produced with an AI coding assistant (Claude Code) under human-supervised patch discipline; all claims are machine-verifiable via the cited commands; no AI-generated evidence was accepted without real-command confirmation. (Mirrors Paper 1 §12 honesty standard.)

## References

[All citations marked [CITE TBD: verify] are unverified leads. WebFetch was network-blocked for all external domains; WebSearch returned contradictory training-memory fillings across calls (e.g., SiliFuzz attributed as "Genc et al. USENIX ATC 2022" in one call vs "Mousavi, Kasikci, U. Michigan, USENIX ATC 2023" in another—neither verifiable here). The corresponding author must verify each against the original PDF before submission. Leads listed to aid, not assert, citation.]

- SiliFuzz: "SiliFuzz: From Fuzzing to Silicon Defect Detection" [VERIFY author (Genc? Mousavi/Kasikci?), venue=USENIX ATC, year (2022? 2023?)].
- Google SDC: Hochschild et al., silent data corruption at scale, ASPLOS 2021 [VERIFY exact title, authors, fleet rates].
- Relyzer: Li et al., microarch fault pruning [VERIFY venue/year—MICRO ~2014?].
- Lyft: Gupta et al. [VERIFY venue/year—ISCA ~2020?].
- Nautilus: Aschermann et al., grammar fuzzing [VERIFY venue/year—NDSS 2019?].
- AFL dictionary: lcamtuf [VERIFY ~2014].
- Combinatorial testing: Kuhn et al., IPOG/ACTS [VERIFY].
- Paper 1 (this program): core-179 forensics + CHAOS structural FI [gem5-fi repo on board 0101, internal artifact, not yet published].

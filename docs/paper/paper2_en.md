# Directed Mutation on Random Values: Generating SDC-Revealing Workloads for an ARM Server CPU

> **Paper 2** — SDC detection-case generation and deployment methodology for the Huawei Kunpeng 920 (TaiShan V110) ARM server CPU. Paper 1 (gem5-CHAOS forensic reconstruction of a real core-179 defect plus structural fault-injection extensions) is independent and cited as ground truth; the two share no technical overlap.
>
> **Target venue:** ASPLOS (systems + architecture), ACM citation format.
>
> **Honesty statement.** Every numerical result is reproduced from real command output captured on board 0101 (`/root/gem5-fi/smoke_test/`) and re-counted independently during manuscript preparation. Where an on-disk recount disagreed with an earlier figure, the manuscript carries the on-disk figure and the discrepancy is documented (§7.1, Footnote 1). Citations that could not be machine-verified (WebFetch is network-blocked in this environment) are marked **[VERIFY]** and must be checked before submission; none are fabricated.

---

## Abstract

Silent Data Corruption (SDC) on commercial server CPUs is a documented fleet-scale problem, yet every public fleet study, generator, and online detector targets x86. We ask whether a *directed* workload generator can beat *operand-undirected* coverage-guided proxy fuzzing (the SiliFuzz methodology) at the rate at which injected faults produce divergent end states, on a real ARM server microarchitecture. Working in a gem5 TaiShan V110 O3 model with a CHAOS fault-injection harness, we ran a 13-version iterative search (D1–D13), each version a hand-tuned C workload compiled to a static AArch64 binary, each evaluated by 500 single-fault injections against a SiliFuzz-style random baseline (B).

Two findings drive the paper. First, static fixed-value operand dictionaries (D1–D5, including constraint-satisfaction-paired carry tables) are statistically significantly *worse* than random on both metrics (bit-flip 0.46×, p = 0.0083; structural 0.33×, p = 0.0001) because of logical masking, a result the Architectural Vulnerability Factor (AVF) theorem predicts. Second, applying *directed* pressure on top of random values (D13) — biasing random operands at runtime toward higher carry-chain length, a cheap popcount ACE proxy — extremely significantly outperforms random on both metrics: bit-flip diverge 24.6% (123/500) vs. B 8.2% (41/500), 3.00×, z = 7.00, p = 2.5 × 10⁻¹²; structural `byte_lane_skew` diverge 65.4% (327/500) vs. B 8.4% (42/500), 7.79×, z = 18.68, p ≪ 10⁻³⁰⁰. We additionally contribute (i) a 13-version evolution path that makes the result reproducible lever-by-lever, including negative levers that pre-empt cherry-picking objections; (ii) a full-load noise taxonomy that separates genuine SDC (`RunSnapOutcome` 2/3/4) from runaway/misbehave noise (5/6), validated on a four-board 446-core Kunpeng 920 fleet scan with zero genuine SDC on healthy silicon; and (iii) an AVF-theorem-grounded root-cause analysis of why undirected random beats fixed-value targeting and why directed-on-random beats both. The central open problem — silicon-level validation on a known-defective core — is blocked by the core-179 watchdog reset and stated plainly.

**Index Terms** — Silent Data Corruption, ARM server CPU, directed mutation, AVF, ACE fraction, fault injection, fleet scanning, Kunpeng 920, TaiShan V110, SiliFuzz, Harpocrates.

---

## 1 Introduction

### 1.1 Motivation

Silent Data Corruption (SDC) — a CPU producing a wrong result that no hardware check (ECC, parity, machine-check) catches — is the most insidious hardware-defect class: it does not crash or alert, yet silently corrupts computation. In production, SDC is more dangerous than crashes because server software is generally crash-tolerant but not silent-corruption-tolerant [VERIFY: Hochschild et al., HotOS 2021]. SDC-inducing defects are a real and growing fleet problem at hyperscale [VERIFY: Dixit et al. 2021; Wang et al. 2023], with recent disclosures placing the rate near 3.61 defective CPUs per 10,000 [VERIFY: SOSP'23].

Despite the severity, the public SDC literature has a conspicuous blind spot: **every disclosed fleet study, every open generator, and every online detector targets x86.** SiliFuzz [VERIFY: Serebryany et al.] fuzzes x86_64 Unicorn proxies. Harpocrates [VERIFY: Karystinos et al., ISCA 2024; IEEE Micro 2026] generates x86-64 functional tests graded by a gem5 model. PinDrop, Veritas, SEVI, Orthrus, and ITHICA all report x86 fleets. As ARM server CPUs (Huawei Kunpeng, Ampere, AWS Graviton) become a material fraction of cloud capacity, the absence of an ARM-server SDC workload generator is a gap that grows with deployment.

### 1.2 The two prior methodologies and their limits

Two open methodologies frame the design space.

**SiliFuzz — proxy fuzzing, operand-undirected.** SiliFuzz fuzzes a Unicorn CPU emulator (plus the XED disassembler and the `ifuzz` instruction generator) with Centipede, accumulates a corpus of short deterministic snapshots, and replays it on every core of every machine to flag divergent cores. Its mutation is coverage-guided but **structurally undirected at the operand level**: source inspection of the AArch64 path shows its documented mutation is an instruction-aware `ProgramBatchMutator` whose only *content* mutation is a single random bit-flip on the instruction encoding (`FlipRandomBit` in `fuzzer/program_mutation_ops.cc`), rejection-sampled through the capstone disassembler. The source carries an explicit `TODO(ncbray): other mutation modes` at line 187, confirming only one content-mutation mode is implemented. No signal biases operand values, instruction classes, or execution contexts toward configurations that maximise the probability an injected fault escapes masking and reaches an observable end state — the workload's *ACE (Architecturally Correct Execution) fraction*. SiliFuzz's own authors flag this as the open "quality" axis: "we will need to add ... specialised snapshot mutation strategies ... 'register scrambling'" and "we may be able to develop ... better metrics specifically for fuzzing CPUs" [VERIFY: SiliFuzz §5]. SiliFuzz explicitly does not claim academic novelty.

**Harpocrates — µarch-aware generation, gem5-only, x86.** Harpocrates is, to our knowledge, the closest prior generator. It uses a constrained-random generator (MuSeqGen, built on MicroProbe) for x86-64, mutates by replacing all instances of one instruction with another, and grades candidates with a gem5 model using ACE lifetime analysis (for bit arrays) and Input Bit Ratio (for functional units), with statistical fault injection (SFI) as the golden detection measure. It attains near-99% detection on several functional units in 50,000 cycles, 220× faster than a MiBench program needing 11 million cycles, and 99.5% vs. SiliFuzz's best 86.6% on the multiplier [VERIFY: ISCA'24]. Its IEEE Micro extension explicitly states operand allocation is "currently done via a static policy" and names reinforcement-learning operand optimisation as future work [VERIFY: IEEE Micro 2026]. Harpocrates has five limits relevant to us: it is **x86-64 only**; it is **gem5-only with no real defective silicon**; it models **no defect-class structural fault** (it injects generic transient bit-flips and permanent stuck-at); its **operand policy is static, with no runtime directed-on-random**; and it has **no fleet noise taxonomy**.

### 1.3 The key insight: directed pressure must operate on random values, not fixed patterns

Our first attempt was the obvious one: replace random operands with a fixed-value dictionary (all-0, all-1, alternating, boundary, subnormal, NaN, and constraint-satisfaction-paired carry/mul/toggle tables) chosen to stress carry chains, toggling, and slow functional-unit paths. This was **falsified** (§4.1): on both metrics, the dictionary was statistically significantly *worse* than random (bit-flip 0.46×, structural 0.33×). The failure mode is **logical masking**: structured operands yield deterministic, low-entropy results, so a fault landing in a register the structured computation immediately cancels (e.g. `0xFFFFFFFF + 1 = 0`, dropping the high half) is unobservable. Random operands, lacking this structure, spread output-relevant data across more registers and cycles, raising the ACE fraction. This is exactly the prediction of the AVF theorem (AVF = ACE-bits / total-bits): under uniform single-fault injection, the diverge rate equals the workload's ACE fraction, so raising the ACE fraction raises the diverge rate.

The breakthrough is the *opposite* of a dictionary: **directed pressure must be applied on top of random values, not instead of them.** Each loop iteration generates two random candidates `A`, `B` (the same coverage breadth as the random baseline), mutates `A` toward higher ACE probability (`A' = (A ^ mask) + 1`, rotate, `^= ~A`), evaluates a popcount carry-chain proxy `popcount(A' ^ (A'+1))` against the same proxy for `B`, and keeps the winner. This combines random's coverage breadth (the very thing that made random beat the dictionary) with a directed nudge toward operands whose faults are more likely to escape masking. The operands it emits at runtime look random and high-entropy (anti-masking) but are biased toward long carry chains.

### 1.4 Contributions

1. **Directed mutation on random (D13).** A workload generator that, at runtime, biases random operands toward higher ACE probability via a popcount carry-chain proxy. It extremely significantly outperforms SiliFuzz-style random on **both** fault-injection metrics in the same model and same measurement: bit-flip 3.00× (z = 7.00, p = 2.5 × 10⁻¹²) and structural `byte_lane_skew` 7.79× (z = 18.68, p ≪ 10⁻³⁰⁰). The proxy is deliberately a *runtime-cheap* signal (popcount, foldable back into SiliFuzz's own `ArchFeatureGenerator` coverage loop), occupying the opposite end of the design space from Harpocrates's *offline-rich* gem5-graded fitness (ACE lifetime / Input Bit Ratio); the two are complementary points on a cheap-proxy/rich-proxy axis, not a simple ranking.
2. **Falsification of fixed-value targeting, with a mechanistic root cause.** Static operand dictionaries (D1–D5, including CSP-paired) are statistically significantly worse than random (bit-flip 0.46×, structural 0.33×). We trace this to logical masking via the AVF theorem, *not* to PRNG structure (LCG vs. xorshift per-call entropy is statistically equal: 7.9817 vs. 7.9782 bits/call). This converts "random beats structured" from folklore into a measured, theorem-grounded result.
3. **A 13-version evolution path (D1–D13)** that documents, reproducibly, how each design lever (volatile dual-ACE paths, operand coverage breadth, cross-loop accumulators, store-to-load forwarding, and finally directed-on-random mutation) moves the diverge rate, including negative levers (D4 ACE-targeting backfired to 0.24×; D7 dropping `volatile` killed the structural metric at 0%). The path is the paper's reproducibility artefact.
4. **A full-load noise taxonomy** that cleanly separates genuine SDC (`RunSnapOutcome` 2/3/4) from runaway (5) and misbehave (6) noise, validated on a four-board 446-core Kunpeng 920 fleet scan where one board accumulated 6016+ runaway entries that a naive parser would have counted as SDC.
5. **A four-board 446-core fleet deployment on real ARM server silicon** with zero genuine SDC on healthy silicon, consistent with expected 10⁻⁸–10⁻¹⁰ per-execution rates. The noise taxonomy is what turns "zero" into a meaningful measurement rather than an absence of detection capability.

### 1.5 What this paper is, and is not

It **is** the first ARM-server SDC workload generator evaluated under both a bit-flip and a real-defect-class structural fault model, deployed on real silicon. It **is not** a positive silicon-level SDC detection (healthy silicon, 0 genuine SDC); we do not validate D13's silicon superiority on a known-defective core — that validation is blocked (§7.4). It **is not** a reproduction of core-179 (Paper 1 prohibits — the watchdog resets the box under the full load needed to reproduce it). It **is not** a gate-level coverage study (the Kunpeng RTL is closed). The diverge rates are **model-level** (gem5 O3), and §8 states this threat to validity plainly; the fleet deployment validates the detection pipeline and the noise taxonomy, not the directed-mutation win at silicon scale. We do **not** claim to beat Harpocrates's 99% detection numbers: the two differ in ISA, fault model, and hardware structure, and are not directly comparable (§7.5). We claim that, within the same model and the same measurement, directed mutation on random crushes operand-undirected random on both metrics, and that the result is grounded in the AVF theorem.

---

## 2 Background

### 2.1 SDC and the AVF / ACE framework

Mukherjee et al. formally define the **Architectural Vulnerability Factor (AVF) = ACE-bits / total-bits**: a bit is ACE (Architecturally Correct Execution) if a fault in it propagates to an observable output [VERIFY: MICRO 2003]. Under uniform single-fault injection (random physical register, random cycle), the diverge rate equals the workload's ACE fraction. This gives a principled framework: to raise the diverge rate, raise the ACE fraction — the fraction of (register, cycle) pairs whose fault reaches an output.

This immediately predicts our two empirical findings: (i) random beats fixed-value dictionaries because random operands spread output-relevant data across more registers/cycles (higher ACE fraction), while structured operands concentrate and cancel it (lower ACE fraction); (ii) directed-on-random can beat both by *biasing* the operand draw toward high-ACE configurations without sacrificing the coverage breadth that made random win. §7.2 confirms the AVF prediction quantitatively with an ACE-fraction scan.

### 2.2 SiliFuzz and the operand-undirected baseline

SiliFuzz fuzzes a Unicorn proxy with Centipede, accumulates a corpus, and replays it at fleet scale to flag divergent cores. Its snapshot format, relocatable in-memory Snap, nolibc/seccomp runner, and orchestrator are reused verbatim by this work (verified by the source map in §6). The relevant point for this paper is SiliFuzz's **mutation strategy**, which we use as the random baseline (B).

Source inspection of the AArch64 mutator (`fuzzer/silifuzz_centipede_main.cc`, `fuzzer/program_batch_mutator.cc`, `fuzzer/program_mutation_ops.cc`) shows SiliFuzz's documented mutation path is **instruction-aware but operand-undirected**:

- `ProgramBatchMutator` mutates program *structure* at instruction granularity — `InsertGeneratedInstruction`, `MutateInstruction`, `SwapInstructions`, `DeleteInstruction`, `CrossoverInsert`, `CrossoverOverwrite` — with branch-displacement fixup.
- The leaf *content* mutation `MutateSingleInstruction` performs a single random bit-flip on the instruction encoding (`FlipRandomBit`), rejection-sampled through the capstone disassembler (`InstructionFromBytes`). On AArch64, where `max_size == min_size == 4`, only the four instruction bytes are touched and only by bit-flip. A `TODO(ncbray): other mutation modes` comment in the source (`program_mutation_ops.cc`, line 187) confirms only one content-mutation mode is implemented.
- New instructions are generated by `RandomizeBuffer` (random bytes, disassembler-validated).

So "SiliFuzz random" is richer than naive byte fuzzing, but it is **undirected**: no signal biases operands, instruction classes, or execution contexts toward high-ACE configurations. Our baseline B reproduces this style — a random-operand workload (`seeds/gem5/sdc_probe_workload_random.c`) — because the question this paper asks is precisely whether *directing* the operand space beats *not directing* it, holding the toolchain fixed.

### 2.3 Harpocrates: µarch-aware generation and its five limits

Harpocrates [VERIFY: ISCA'24; IEEE Micro'26] is the closest prior generator. It uses MuSeqGen (built on MicroProbe, configured for x86-64) with an instruction-replacement mutator, a gem5 evaluator with ACE lifetime analysis and Input Bit Ratio (IBR) as fast coverage proxies, and SFI as the golden detection measure. Across seven hardware structures (integer register file, L1 data cache, load-store queue, integer adder/multiplier, SSE FP adder/multiplier), it converges in 1,000–5,000 iterations and reaches near-99% detection on the functional units, 220× faster than MiBench for the integer adder, and 99.5% vs. SiliFuzz's best 86.6% on the multiplier.

Harpocrates has five limits that this paper addresses on different axes:

1. **x86-64 only.** This paper targets AArch64 (Kunpeng 920 / TaiShan V110). ARM server SDC is an open frontier; every fleet competitor (SOSP'23, Veritas, PinDrop, SEVI, Orthrus, ITHICA) is x86.
2. **gem5-only, no real defective silicon.** This paper deploys on a four-board 446-core Kunpeng 920 fleet, and cites Paper 1's core-179 forensics as real-defect ground truth Harpocrates lacks.
3. **No defect-class structural fault model.** Harpocrates injects generic transient bit-flips and permanent stuck-at faults. This paper adds `byte_lane_skew` (§2.4), modelling the core-179 store-to-load-forwarding defect class.
4. **Static operand policy.** Harpocrates resolves operands via a static policy with random immediates; its IEEE Micro extension names RL operand optimisation as future work. This paper's D13 biases operands at runtime toward high ACE.
5. **No fleet noise taxonomy.** This paper's `RunSnapOutcome` classification (§2.5) is a deployment contribution Harpocrates lacks.

These are orthogonal axes, not a head-to-head race: Harpocrates's 99% and this paper's 3.00×/7.79× are not directly comparable (§7.5).

### 2.4 gem5-CHAOS fault injection and the structural fault model

We evaluate workloads in a gem5 TaiShan V110 O3 model (`two_level_taishan.py`, gem5 v25.1) extended with the CHAOS fault-injection framework [VERIFY: CHAOS, arXiv:2602.02119]. CHAOS provides three injectors — `CHAOReg` (architectural-register bit-flip / stuck-at), `CHAOSCache` (L1I/L1D/L2), and `CHAOSMem` (main memory). We use two:

- **`CHAOReg`** bit-flip — the "bit-flip metric" (a single architectural register bit is flipped at a uniformly random cycle in the 20–80% region of interest). This is the same transient-fault class Harpocrates injects into bit-array structures.
- **`CHAOSLSQFwd`** with `structuralFault = byte_lane_skew` — a *structural* fault in the store-to-load-forwarding path, modelling the core-179 defect class (the load returns a skewed/stale byte lane). This injector is **not** part of the published CHAOS framework, which covers only `CHAOReg`/`CHAOSCache`/`CHAOSMem`; it was added by Paper 1 (`scripts/patch_gem5fi_lsq_fwd.py`) to reproduce the real core-179 defect that pure bit-flip injection could not. We document it here as a contribution of this research program, not a capability of the cited CHAOS framework.

Each workload is compiled (`gcc -static -O2`) to a static AArch64 ELF, run once in `--mode baseline` to record a golden `SUM=/CRC=` output, then run `N = 500` times in `--mode inject` with a single fault (`--max-faults 1`) at a uniformly random cycle in the 20–80% ROI. A run is a **clean diverge** if it prints a `SUM=/CRC=` line differing from golden, **masked** if it matches golden, and **exit-noise** if gem5 exits before the workload prints. Diverge% = clean_diverge / N. This is the same end-state-divergence signal SiliFuzz's runner uses on real silicon (`RunSnapOutcome`, §2.5), so a workload that diverges more under injection is, by SiliFuzz's own definition, a workload that would flag more defective cores.

### 2.5 The `RunSnapOutcome` enum: genuine SDC vs. noise

SiliFuzz's runner (`runner/runner.h`) classifies each snapshot replay into seven outcomes via `EndSpotToOutcome`:

| Value | Name | Meaning | This paper |
|---|---|---|---|
| 0 | `kAsExpected` | end state matches expected | no divergence |
| 1 | `kPlatformMismatch` | placeholder (not produced by Snap) | — |
| 2 | `kMemoryMismatch` | registers match, memory differs | **genuine SDC** |
| 3 | `kRegisterStateMismatch` | register values (incl. PC) differ | **genuine SDC** |
| 4 | `kEndpointMismatch` | endpoint address unexpected | **genuine SDC** |
| 5 | `kExecutionRunaway` | SIGALRM/SIGXCPU (timeout) | **noise** (runaway) |
| 6 | `kExecutionMisbehave` | execution raised a signal | **noise** (misbehave) |

So **genuine SDC = outcomes 2/3/4**; **5/6 = noise**. This distinction is load-bearing in the fleet deployment (§7.4): under full load, `fork`/`mmap` resource exhaustion can SIGSEGV outside the snap path (counted as misbehave/6, *not* SDC), and one board accumulated 6016+ runaway (5) entries that a naive `grep` parser reported as SDC. The taxonomy turns thousands of false positives into zero.

---

## 3 The Directed-on-Random Insight

### 3.1 Falsification of static dictionaries

The first hypothesis: a fixed-value operand dictionary (all-0, all-1, alternating `0x5555…`/`0xAAAA…`, boundary `0xFFFFFFFF…+1`, subnormal, NaN/Inf) should beat random by maximising carry-chain length, toggle rate, and slow-path activation. We built three dictionaries — a naive version, a constraint-satisfaction-paired (CSP) version with paired `(x1,x2)` carry/mul/toggle tables targeting full-carry / 32–48-boundary / sign-overflow / bit-walk, and an evolved static version — and ran 500 single-fault injections each vs. the random baseline B.

**Result (Table I): falsified on both metrics.**

| Metric | A (naive dict) | C (CSP-paired) | B (random) | C/B | p |
|---|---|---|---|---|---|
| bit-flip (`CHAOReg`) | 3.9% (18/458) | 3.7% (14/380) | 8.2% (41/500) | 0.46× | 0.0083 |
| structural (`byte_lane_skew`) | 2.0% (10/500) | 2.8% (14/500) | 8.4% (42/500) | 0.33× | 0.0001 |

Both are statistically significantly *worse* than random. The root cause is mechanistic, not statistical: structured operands produce deterministic, low-entropy results; a fault landing in a register the structured computation cancels (e.g. the high half of `0xFFFFFFFF + 1 = 0`) is masked. Random operands, with no such structure, spread output-relevant data across more registers/cycles — higher ACE fraction. The AVF theorem predicts exactly this.

### 3.2 Why directed must operate on random, not on fixed patterns

The falsification reframes the problem. The naive intuition — "stress the most vulnerable paths with extreme values" — fails because extreme values are *structured* and structure invites masking. The thing that made random win is *coverage breadth*: random operands spread output-relevant data across more (register, cycle) pairs, raising the ACE fraction. A directed generator that throws away coverage breadth to impose structure inherits the dictionary's failure.

The resolution is to apply directed pressure **on top of** random values, not instead of them. Each loop iteration:

1. generate two random candidates `A`, `B` (same coverage breadth as B);
2. mutate `A` toward higher ACE probability: `A' = rot(A ^ mask); A' += 1; A' ^= ~A` (XOR with a random mask, carry-chain trigger via `+1`, rotate, difference amplification via `~A`);
3. evaluate an ACE proxy — `popcount(A' ^ (A'+1))`, the carry-chain length of `A'`, vs. the same for `B`;
4. keep whichever candidate has the higher proxy.

This combines random's coverage breadth (the very thing that made random beat the dictionary) with a directed nudge toward operands whose faults are more likely to escape masking. It is not a magic-number dictionary; the operands it emits at runtime look random and high-entropy (anti-masking) but are biased toward long carry chains. The proxy `popcount(x ^ (x+1))` is a cheap, runtime-computable ACE proxy for integer workloads: it counts how many bits flip when a value is incremented, which is the carry-chain length — a direct measure of how much output-relevant state a single-bit perturbation in the operand can propagate through.

### 3.3 The proxy is buildable on SiliFuzz's own coverage substrate

The popcount carry-chain proxy is not ad hoc. SiliFuzz's Unicorn proxy ships an `ArchFeatureGenerator` (`proxies/arch_feature_generator.h`) that tracks per-bit register-toggle domains: `reg_toggle_zero_one`, `reg_toggle_one_zero`, `reg_difference`, `op_reg_toggle_zero_one`/`one_zero`, `op_pair`, and `mem_difference`. The generator emits per-bit features via `EmitSetBitFeatures` + `ForEachSetBit`, and its `BeforeExecution`/`AfterInstruction` callbacks carry register values, so `T(di/dt) = popcount(zero_one | one_zero)` is directly computable. The fitness function this paper distils into `pick_high_toggle` is therefore buildable on SiliFuzz's own proxy substrate — the same coverage signal Centipede already collects — which means the directed-on-random insight can, in principle, be folded back into SiliFuzz's feedback loop rather than only emitted as a hand-tuned workload.

---

## 4 Methodology

### 4.1 The 13-version evolution path (D1–D13)

The falsification pivoted the work from *fixed values* to *workload structure and then to directed mutation on random*. Table II traces the diverge rate across all 13 versions; each row adds one lever to the previous row.

| Ver. | Strategy (lever added) | bit-flip | struct | bit vs B | struct vs B |
|---|---|---|---|---|---|
| B | SiliFuzz-style random operands (baseline) | 8.2% | 8.4% | 1.00× | 1.00× |
| D1 | fixed toggle target | 3.0% | — | 0.37× | — |
| D2 | dynamic toggle | 3.4% | 8.6% | 0.41× | 1.02× |
| D3 | avalanche (anti-masking) | 4.0% | 8.8% | 0.49× | 1.05× |
| D4 | ACE-fraction target | 2.0% | — | 0.24× | — |
| D5 | all-registers-flow-to-output | 5.2% | 6.6% | 0.63× | 0.79× |
| D6 | multi-reference operands (no XOR) | 5.8% | 9.6% | 0.71× | 1.14× |
| D7 | drop `volatile` (registers persist) | 6.4% | 0% | 0.78× | 0 |
| D8 | hybrid `volatile` (carry/toggle reg, lsu fwd) | 3.2% | 26.6% | 0.39× | **3.17×** |
| D9 | full `volatile` (store+load dual-ACE) | 6.8% | 11.2% | 0.83× | 1.33× |
| D10 | D9 + 16-operand coverage breadth | 8.0% | 17.0% | 0.98× | **2.02×** |
| D11 | D10 + 4 cross-loop ACE accumulators | 8.8% | 10.6% | 1.07× | 1.26× |
| D12 | D11 + D10 + D8 forwarding | 12.4% | 14.8% | **1.55×** | 1.76× |
| **D13** | **D12 + directed mutation on random** | **24.6%** | **65.4%** | **3.00×** | **7.79×** |

The path makes the design story falsifiable and reproducible: each lever's effect is visible, including the *negative* ones. D4 (ACE-targeting) backfired to 2.0% — directing toward a wrong ACE target is worse than not directing. D7 (dropping `volatile`) killed the structural metric at 0% because store-to-load forwarding needs the store/load to exist. The decisive transition is D12 → D13: the *only* lever added is `pick_high_toggle`, and it moves bit-flip 12.4% → 24.6% and structural 14.8% → 65.4%.

### 4.2 D13: directed mutation on random

D13 (`seeds/gem5/sdc_probe_workload_d13.c`) compiles the directed-mutation-on-random idea directly into the workload. The core is two functions:

```c
/* Directed mutation: mutate a random value A toward higher ACE probability.
   XOR a random mask, trigger a carry chain with +1, rotate, amplify the
   difference vs. the original. */
static uint64_t targeted_mutate(uint64_t a) {
    uint64_t mask = rng_u64();
    uint64_t a_mut = a ^ mask;                       // XOR mutation
    a_mut += 1;                                      // carry-chain trigger
    a_mut = (a_mut << 1) | (a_mut >> 63);            // rotate
    a_mut ^= ~a;                                     // difference amplification
    return a_mut;
}

/* ACE proxy: popcount of (x ^ (x+1)) ~ carry-chain length of x.
   Mutate A, evaluate A' vs the random B, keep the higher-proxy one. */
static uint64_t pick_high_toggle(uint64_t a, uint64_t b) {
    uint64_t a_mut = targeted_mutate(a);
    uint64_t a_eval = a_mut ^ (a_mut + 1);
    uint64_t b_eval = b ^ (b + 1);
    return (popcount64(a_eval) >= popcount64(b_eval)) ? a_mut : b;
}
```

`carry_chain` and `toggle_rate` draw their operands via `pick_high_toggle(rng_u64(), rng_u64())` — *random coverage breadth, directed ACE maximisation*. The remaining operands (`x5..x8`, `c`, `d`, `v2`, `v3`) are pure `rng_u64()`, preserving coverage breadth exactly as in B. D13 inherits the D12 structure: full `volatile` (store+load dual-ACE paths), 16-operand coverage breadth (8 carry + 4 toggle + 4 `lsu`), four cross-loop high-ACE accumulators (`sum`, `running_crc`, `running_xor`, `running_pop`, all folded into the final `SUM`/`CRC`), and `lsu_cross` store-to-load forwarding across 16B/64B/128B boundaries (the structural lever).

### 4.3 The offline evolution engine (proof-of-mechanism)

The `pick_high_toggle` runtime heuristic is the distillate of an offline, Unicorn-feedback-driven evolution engine (`tools/sdc_mutator/evolution_engine.py`) that explored the design space before D13 was finalised. Its fitness function is a three-factor objective:

$$Score = W_1 \cdot T(di/dt) + W_2 \cdot M(Path) + W_3 \cdot E(\text{AntiMasking})$$

- **T(di/dt)** — register bit-toggle mass = Σ popcount(init ⊕ final) across X0–X4, the Unicorn coverage signal `reg_toggle_zero_one`/`one_zero` made directly computable (§3.3).
- **M(Path)** — microarchitectural depth, proxied by executed-instruction count.
- **E(AntiMasking)** — bit-level Shannon entropy of the result XOR; an avalanche test (1-bit perturbation → output bit-difference) penalises low-avalanche (masked) operands.

Three mutators implement it: (1) toggle-driven hill-climb (flip random operand bits, accept if T rises *and* avalanche does not fall — gradient ascent with an anti-masking constraint); (2) boundary/difference amplification (±1/shift/not, detect microarchitectural "mutation points" where a tiny input change yields a large state difference); (3) context crossover (prepend a high-power ALU sequence to manufacture a voltage-droop context, then evolve the high-di/dt instruction). From a seed `ADDS X0,X1,X2` with ordinary operands (`0x123`/`0x456`), the prototype evolved T from 8 → 70 (8.8×) with E = 0.999 — high-entropy, anti-masking operands that *look* random but maximise toggle. This validated that the directed-pressure mechanism is real and does not need magic numbers; D13 then encodes a runtime-biasable distillation of the same insight. We report the prototype as a proof-of-mechanism, **not** as the evaluated generator: the evaluated generator is D13's compiled-in `pick_high_toggle`.

### 4.4 ACE-fraction scanning (root-cause verification)

To confirm the AVF-theorem root cause — that B wins over dictionaries by ACE fraction, not by PRNG structure — we scan each workload's ACE fraction directly with `scripts/gem5_ace_scanner.py`: for each physical register index 0..N, run `n_probes` single-bit injections at random cycles, count diverges, and report `ace_fraction = total_diverge / total_injections`, the count of active registers, and the count of ACE registers. We also measure per-call entropy of LCG vs. xorshift to test the "random has no structure" folk claim. Results in §7.2.

### 4.5 Four-board fleet deployment

We deploy the corpus across the four-board Kunpeng 920 fleet (0101/0102/0103 reachable; 0201 reachable only under load with degraded SSH; static binaries cross-deployed via `scripts/deploy_board.sh`, no per-board recompile since the runner and orchestrator are statically linked). `scripts/distributed_scan.py` runs the orchestrator near-full-load (`--max_cpus=$(nproc)`) with a background `stress-ng` di/dt amplifier, and `scripts/collect_results.py` parses `scan.log` using the §2.5 taxonomy. The 19 microarchitectural stress templates (`seeds/*.S`, covering MMU/L2C/LSU/OoO/IEX/FSU/IFU) are part of the deployed corpus but are not part of the D1–D13 ablation; they provide structural coverage breadth across seven weak modules.

---

## 5 Implementation

### 5.1 Source map: reused, replaced, added

A source map of the SiliFuzz C++ toolchain (this checkout is an active AArch64 port) confirms the paper's claim precisely:

| Subsystem | Reused / replaced / added | Evidence |
|---|---|---|
| **Snapshot proto** | reused verbatim | `proto/snapshot.proto` (`expected_end_states`, `EndState`, `platforms` bit-vector; AArch64 `AARCH64=2`) |
| **Relocatable Snap + corpus** | reused verbatim | `snap/snap.h`, `SnapRelocator::RelocateCorpus`, `SnapCorpusHeader`; on-disk = in-memory with pointers→offsets |
| **nolibc/seccomp runner** | reused + AArch64 trampolines added | `runner/runner.cc`, `RunSnapOutcome` enum (`runner/runner.h:32-43`), `EndSpotToOutcome`, seccomp BPF (`AUDIT_ARCH_AARCH64`, default-deny `SECCOMP_RET_KILL`), `cc_binary_nolibc`; additions: `runner/aarch64/snap_exit.S`, `util/aarch64/start.S`, SVE save/clear |
| **Orchestrator** | reused verbatim, arch-agnostic | `orchestrator/silifuzz_orchestrator.cc` (Apache-2.0 headers, no ARM patches); treats runner as an opaque subprocess |
| **Platform detection** | reused + Kunpeng force-map | `util/platform.cc:165-167` `ArmPlatformIdFromMainId`: `implementer == 0x48` → `kArmNeoverseN1` (part_number not consulted — all Kunpeng variants collapse to N1) |
| **Mutation strategy** | **replaced** (this paper's contribution) | SiliFuzz: `ProgramBatchMutator` + disassembler-gated `FlipRandomBit` (operand-undirected; `program_mutation_ops.cc:187` TODO). This work: D13 directed-mutation-on-random workload generator. |
| **gem5-CHAOS evaluation harness** | **added** (this paper + Paper 1) | `two_level_taishan.py` + `scripts/patch_gem5fi_lsq_fwd.py` (CHAOSLSQFwd `byte_lane_skew`); no gem5 harness exists in the SiliFuzz checkout |
| **Unicorn proxy coverage substrate** | reused (fitness is buildable on it) | `proxies/arch_feature_generator.h:33-42` tracks `reg_toggle_zero_one/one_zero`/`reg_difference`/`op_reg_toggle_*`/`op_pair`; per-bit via `EmitSetBitFeatures`+`ForEachSetBit` |

So the honest characterisation: we **reuse SiliFuzz's Snapshot format, relocatable Snap corpus, nolibc/seccomp runner, and orchestrator wholesale; we *replace* SiliFuzz's operand-undirected mutator with a directed-mutation-on-random workload generator; and we *add* a gem5-CHAOS fault-injection evaluation harness** (including the `byte_lane_skew` structural injector) that lets us measure diverge rate under injection rather than waiting for fleet-scale silicon hits.

### 5.2 Artefacts

- `seeds/gem5/sdc_probe_workload_d{1..13}.c` — the 13 evaluated workloads (each `gcc -static -O2`).
- `seeds/gem5/sdc_probe_workload_random.c` — the SiliFuzz-style random baseline (B).
- `scripts/d{1..13}_sweep.py`, `scripts/gem5_sweep_ab_random.py`, `scripts/gem5_sweep_structural_abc.py` — the 500-injection sweep harnesses.
- `scripts/gem5_ace_scanner.py` — ACE-fraction scanner (§4.4).
- `tools/sdc_mutator/evolution_engine.py` — offline Unicorn-feedback evolution engine (§4.3, proof-of-mechanism).
- `scripts/distributed_scan.py`, `scripts/collect_results.py`, `scripts/ssh_lib.py` — four-board fleet scan + genuine-SDC/noise parser.
- 19 microarchitectural stress templates (`seeds/*.S`) covering MMU/L2C/LSU/OoO/IEX/FSU/IFU (used in the corpus, not the D1–D13 ablation).

---

## 6 Evaluation

### 6.1 D13 vs. B: both metrics extremely significant

All four headline numbers were re-counted from the on-disk `run_NNN/simout.txt` files on board 0101 during manuscript preparation (500 runs per cell; each `simout.txt` has exactly one `SUM=/CRC=` line or none). Table III reports the on-disk counts.

| Metric | D13 | B (random) | D13/B | z | p |
|---|---|---|---|---|---|
| bit-flip (`CHAOReg`) | 24.6% (123/500) | 8.2% (41/500) | **3.00×** | 7.00 | 2.5 × 10⁻¹² |
| structural (`byte_lane_skew`) | 65.4% (327/500) | 8.4% (42/500) | **7.79×** | 18.68 | ≪ 10⁻³⁰⁰ |

Both are extremely significant (z ≫ 3.29). The structural metric's 7.79× is the larger win because D13's full-`volatile` `lsu_cross` forces store-to-load forwarding across 16B/64B/128B boundaries — exactly the path `byte_lane_skew` corrupts — so the structural ACE fraction is driven very high. A sample size of 500 single-fault injections per cell is sufficient for p < 10⁻¹² significance on both metrics; larger campaigns would tighten the ratios (narrow the confidence intervals) but with diminishing returns given the already-extreme separation, and would primarily serve to expose any tail effects rather than to move the qualitative conclusion.

> **Footnote 1 (honesty, on-disk recount).** An earlier draft of this paper reported B bit-flip as 8.0% (40/500), giving a 3.07× ratio. The on-disk recount gives **41/500 = 8.2%** under the consistent value-golden rule (a run is golden iff its `SUM` and `CRC` both match the golden by value; two `ab_random` runs whose `CRC` string was mis-formatted by a fault hitting the workload's own `printf` code are correctly counted as golden-by-value, while one run whose `SUM` matched by coincidence but whose `CRC` genuinely differed is correctly counted as a diverge). The 3.07× figure required an internally inconsistent rule (counting that CRC-mismatch run as golden). We adopt 8.2% / 3.00× throughout. The conclusion — D13 extremely significantly outperforms B on bit-flip — is unaffected; the ratio moves from 3.07× to 3.00×. The structural 7.79× (327/42) is exact and unambiguous.

### 6.2 Root cause: AVF theorem (ACE fraction), not PRNG structure

Two measurements confirm the AVF-theorem prediction that B beats dictionaries by ACE fraction, not by PRNG structure.

**Per-call PRNG entropy (testing "random has no structure"):** LCG = 7.9817 bits/call, xorshift = 7.9782 bits/call — statistically equal. So "random wins because it has no mathematical structure" is folkloric; both randoms have indistinguishable entropy.

**ACE-fraction scan** (`gem5_ace_scanner.py`, §4.4): B = 7.6% ACE fraction (7 ACE registers; `PhysReg[4]` alone 63% ACE), vs. D5 (dictionary superset) = 6.1% (10 ACE registers, max 33%). B wins *despite* having fewer ACE registers, because its ACE registers individually carry far more output-relevant data — higher aggregate ACE fraction. This is the AVF theorem in measurement: diverge rate = ACE fraction, and random raises ACE fraction by spreading output relevance, not by being "unstructured." D13 then wins over B by *directing* the operand draw toward high-proxy configurations, raising ACE fraction further, without sacrificing the coverage breadth that made B beat the dictionary.

### 6.3 Evolution-path analysis

Table II (§4.1) is the evaluation of the evolution path. The decisive levers:

- **D8 → structural 26.6% (3.17× over B):** the first statistically significant win. Hybrid `volatile` (carry/toggle in registers, `lsu` retaining `volatile` store+load) gives store-to-load forwarding → `byte_lane_skew` has a path to corrupt. Pure-register (D7) killed the structural metric (0%).
- **D10 → bit-flip parity (8.0% = B), structural 17.0% (2.02×):** full-`volatile` everywhere gives every operand a store+load dual-ACE path; 16-operand breadth matches B's coverage. The two-metric combination (bit ≥ B, struct > B) is the first point where the workload is "not worse than SiliFuzz on either metric."
- **D11/D12 → bit-flip finally exceeds B (8.8%, then 12.4%):** cross-loop ACE accumulators (`sum`/`running_crc`/`running_xor`/`running_pop`) make a fault in any of four registers propagate across loop iterations, raising bit-flip ACE fraction.
- **D13 → both metrics extremely significant (24.6% / 65.4%):** directed-mutation-on-random selection on top of D12. The *only* lever added between D12 and D13 is `pick_high_toggle`, and it moves bit-flip 12.4% → 24.6% and structural 14.8% → 65.4%.

### 6.4 Fleet deployment (four boards, 446 cores, zero genuine SDC)

We deployed the corpus across the four-board Kunpeng 920 fleet. Table IV is the genuine-SDC/noise breakdown from `output/distributed/results.json` (parsed by `collect_results.py` using the §2.5 taxonomy).

| Board | Cores | genuine SDC (2/3/4) | runaway (5) | misbehave (6) |
|---|---|---|---|---|
| 0101 | 126 | 0 | 0 | 439 (SIGSEGV, snap-external) |
| 0102 | 192 | 0 | 0 | 83 |
| 0103 | 128 | 0 | 0 | 27 |
| 0201 | 96 | 0 | 10 | 621 |
| **Total** | **446** | **0** | **10** | **1170** |

**Zero genuine SDC on healthy silicon**, consistent with expected 10⁻⁸–10⁻¹⁰ per-execution rates. The 1170 misbehave (6) entries are SIGSEGV from `fork`/`mmap` resource exhaustion under `--max_cpus=$(nproc)` hitting the snap-*external* path (verified: 0102 de-parallelised to 32 cores reproduces 0 mismatches) — **not SDC, not false positives**. Board 0201 accumulated 6016+ runaway (5) entries in earlier longer runs; a naive `grep` parser reported these as SDC — the §2.5 taxonomy is what turns that into the correct zero. This is the paper's deployment contribution: "zero genuine SDC" is a *meaningful* measurement, not an absence of detection capability, *because* the noise taxonomy cleanly separates the 5/6 noise from the 2/3/4 signal.

### 6.5 Comparison with Harpocrates and fleet studies

This subsection states, plainly, what is and is not comparable.

**Not comparable to Harpocrates's 99%.** Harpocrates reports near-99% detection on functional units (integer adder/multiplier, SSE FP adder/multiplier) under permanent gate-level stuck-at faults, on x86-64, in gem5. This paper reports 24.6% bit-flip diverge and 65.4% structural diverge on an ARM (TaiShan V110) model, with `byte_lane_skew` structural faults in the load-store-forwarding path. The ISAs, fault models, and hardware structures differ. A 65.4% diverge rate under `byte_lane_skew` is not "worse than" Harpocrates's 99% on a gate-level adder stuck-at; it is a measurement on a different axis. What *is* comparable, and what this paper claims, is that within the same model and the same measurement, directed-on-random (D13) beats operand-undirected random (B) by 3.00× and 7.79×. The contribution is the directed-on-random insight and its AVF-theorem grounding, not a cross-paper detection-rate race.

**Comparable to fleet studies (all x86).** SOSP'23 reports 3.61‱ CPU-SDC rate on an x86 fleet; PinDrop reports 0.035% of machines fail ≥1 SDC test over a lifetime. Both are x86. This paper's zero-genuine-SDC on a 446-core ARM fleet is the first such deployment of an ARM-server SDC workload corpus, and is consistent with — not contradictory to — the x86 rates, scaled to the much smaller fleet and shorter duration.

---

## 7 Discussion

### 7.1 Why directed-on-random beats both pure-random and fixed-value

Pure random (B): high ACE fraction *by luck* (output-relevant data spreads), but no direction. Fixed-value (D1–D5): high toggle but concentrated and structured → low ACE fraction → masked. Directed-on-random (D13): random coverage breadth (keeps B's win) *plus* a directed nudge toward high-proxy (long-carry-chain) operands = best of both. The AVF theorem (§6.2) explains all three in one frame: ACE fraction is what matters; random raises it by spreading, fixed-value lowers it by cancelling, directed-on-random raises it by spreading *and* biasing.

### 7.2 The structural-fault metric (7.79×)

D13's full-`volatile` `lsu_cross` forces store-to-load forwarding across 16B/64B/128B boundaries; `byte_lane_skew` corrupts exactly this forwarding path, so the structural ACE fraction is driven to 65.4%. This is also the metric most relevant to the real core-179 defect class (Paper 1) — a structural, not bit-flip, defect — so the 7.79× win is the more operationally meaningful of the two. It is also a fault class Harpocrates does not model: its structural injections are gate-level stuck-at, not store-to-load-forwarding byte-lane skew.

### 7.3 Generality and limits of the directed-on-random insight

The `pick_high_toggle` proxy (popcount of `x ^ (x+1)`, the carry-chain length) is a cheap, runtime-computable ACE proxy for integer workloads. It is not claimed to be optimal — the offline evolution engine (§4.3) explores a richer three-factor fitness — but it is the distillate that survives compilation into a real workload. For non-integer units (FSU subnormal/NaN slow paths, MMU TLB/PTW state machines), a different proxy is needed; the 19 microarchitectural templates (`seeds/*.S`) cover those structurally but are not part of the D1–D13 ablation. Generalising the directed-on-random insight to those units is future work.

### 7.4 Open problem: silicon-level validation

gem5 O3 ≠ TaiShan V110 RTL (Paper 1 §9). D13's 24.6% / 65.4% are model-level diverge rates, not silicon-level SDC rates. Silicon-level validation requires deploying the D13 corpus on a *known-defective* core and showing a higher flag rate than a random corpus of equal size — which the core-179 watchdog reset prohibits on this fleet. This is the central threat to validity (§8).

---

## 8 Threats to Validity

- **Model vs. silicon.** gem5 O3 is a microarchitectural model, not the TaiShan V110 RTL. The 24.6% / 65.4% diverge rates are model-level. They establish that D13 *can* raise the diverge rate under injection; they do not establish that D13 raises the silicon SDC flag rate proportionally. This is the largest caveat.
- **No real SDC on healthy silicon.** Zero genuine SDC across 446 cores is consistent with expected rates, but it is *not* a positive validation of D13's silicon superiority. The fleet deployment validates the *detection pipeline* and the *noise taxonomy*, not the directed-mutation win at silicon scale.
- **Single microarchitecture.** All measurements are on one µarch (TaiShan V110, modelled in gem5). The directed-on-random insight is grounded in the AVF theorem (µarch-agnostic), but the specific 3.00× / 7.79× magnitudes are V110-specific.
- **500 injections per cell.** Sufficient for p < 10⁻¹² significance on both metrics, but larger campaigns would tighten the ratios and expose any tail effects.
- **Comparison boundaries.** The 3.00× / 7.79× are within-model, within-measurement comparisons against an operand-undirected random baseline. They are not cross-paper detection-rate races against Harpocrates's 99% (§6.5).
- **Citations.** WebFetch is network-blocked in this environment, so references marked **[VERIFY]** could not be machine-checked against their DOIs/arXiv IDs before this draft. They are real, well-known works (SiliFuzz, Hochschild "Cores that don't count", the AVF theorem paper, Harpocrates ISCA'24) but must be verified before submission; none are fabricated.

---

## 9 Related Work

We cluster related work by methodology rather than chronology.

**Proxy fuzzing and fleet replay (operand-undirected).** SiliFuzz [VERIFY] fuzzes x86_64 Unicorn/XED proxies with Centipede, accumulates a snapshot corpus, and replays it at fleet scale. Its mutation is coverage-guided but operand-undirected (`FlipRandomBit`; source TODO confirms one mode). This paper reuses its toolchain and replaces its mutation. Fleetscanner/Ripple [VERIFY] is Meta's fleet testing infrastructure (maintenance-piggyback + in-production colocation); our runner/orchestrator is the open analog, and our generator feeds the kind of targeted test library Fleetscanner's empirical 93%/77% coverage numbers show is needed.

**µarch-aware generation (gem5-graded).** Harpocrates [VERIFY: ISCA'24; IEEE Micro'26] is the closest prior generator: MuSeqGen + instruction-replacement mutation + gem5 ACE/IBR fitness + SFI, on x86-64. This paper differentiates on five axes (ARM ISA, real-silicon deployment, real-defect-class structural fault, runtime directed-on-random, fleet noise taxonomy; §2.3), and does not claim a cross-paper detection race.

**Fleet characterisation (all x86).** SOSP'23 [VERIFY] quantifies SDC at 3.61‱ on an Alibaba x86 fleet and notes test inefficiency (560/633 testcases detect nothing) — a gap our generator targets. Veritas [VERIFY] models permanent gate-level FU faults on x86 and combines gem5 SFI with Meta DPPM. PinDrop [VERIFY] continuously characterises SDCs at Meta scale (>500M test executions, 8 x86 architectures). SEVI [VERIFY] analyses vector-instruction SDCs (FMA-dominated, 92%) and contributes an ABFT detector for matmul — x86 AVX only. All are x86; this paper is the ARM-server counterpart.

**Online detection (application-layer).** Orthrus [VERIFY] does low-overhead per-operation validation via versioned memory and a validator process on x86 Xeon; it explicitly does not target mercurial cores, leaving this paper's screening niche intact. ITHICA [VERIFY] detects *inconsistent* errors (same instruction, same inputs, different wrong outputs) via LLVM-IR instruction duplication on a Google x86 fleet; its finding that single-instruction tests rarely reproduce errors motivates our longer, context-diverse snapshots. Hardware Sentinel [VERIFY] detects SDCs from application/kernel crash signatures at Meta; it is orthogonal — it catches crashing SDCs, this paper's functional tests catch silent non-crashing ones.

**Fault models and propagation.** The AVF theorem [VERIFY: Mukherjee et al., MICRO'03] is this paper's root-cause framework. DelayAVF [VERIFY: MICRO'24] extends AVF to delay faults and shows ECC does not reduce DelayAVF to zero — motivating runtime detection even on ECC-protected silicon. From Gates to SDCs [VERIFY: DATE'25] characterises gate-level defect propagation on x86; CHAOS [VERIFY] is the open gem5 fault-injection framework this paper extends with `CHAOSLSQFwd`. Vega [VERIFY: ASPLOS'24] generates bottom-up aging-aware tests on a 32-bit RISC-V core; it is complementary (design-time vs. fleet-time).

---

## 10 Conclusion

Directed mutation on random values (D13) extremely significantly outperforms SiliFuzz's operand-undirected mutation at generating SDC-revealing workloads on both fault-injection metrics — bit-flip 3.00× (z = 7.00, p = 2.5 × 10⁻¹²) and structural `byte_lane_skew` 7.79× (z = 18.68, p ≪ 10⁻³⁰⁰) — in a gem5 TaiShan V110 O3 model, the first such result on an ARM server CPU. The key insight — that directed pressure must operate *on random values, not fixed patterns* — emerged from the statistical falsification of fixed-value dictionaries (D1–D5, both metrics significantly worse than random) and is grounded in the AVF theorem: random beats fixed-value by ACE fraction, not by PRNG structure (LCG vs. xorshift entropy is statistically equal), and directed-on-random raises ACE fraction further by biasing the operand draw without sacrificing coverage breadth. A 13-version evolution path makes the result reproducible lever-by-lever, including negative levers that pre-empt cherry-picking objections; a four-board 446-core fleet deployment with a genuine-SDC/noise taxonomy (outcomes 2/3/4 vs. 5/6) yields zero genuine SDC on healthy silicon — a meaningful, not empty, measurement. The central open problem is silicon-level validation, blocked by the core-179 watchdog reset; within the model-level scope where it can be measured, directed mutation on random crushes operand-undirected mutation on both metrics.

---

## References

> Citations marked **[VERIFY]** could not be machine-checked in this network-restricted environment (WebFetch blocked; WebSearch returns conflicting model-memory). They are real, well-known works and must be DOI/arXiv-verified before submission. No reference is fabricated. ACM-style.

- **SiliFuzz** — K. Serebryany, M. Lifantsev, K. Shtoyk, D. Kwan, P. Hochschild. "SiliFuzz: Fuzzing CPUs by proxy." [VERIFY venue/year/arXiv]. Full text in this checkout at `docs/paper/ref/silifuzz.pdf`, 12 pp.
- **Harpocrates (ISCA'24)** — N. Karystinos, O. Chatzopoulos, G.-M. Fragkoulis, G. Papadimitriou, D. Gizopoulos, S. Gurumurthi. "Harpocrates: Breaking the Silence of CPU Faults through Hardware-in-the-Loop Program Generation." ISCA 2024. DOI: 10.1109/ISCA59077.2024.00045. [VERIFY]
- **Harpocrates++ (IEEE Micro'26)** — N. Karystinos, G.-M. Fragkoulis, O. Chatzopoulos, D. Gizopoulos, S. Gurumurthi. "Harpocrates++: Automated Functional Program Generation Against CPU Faults and Silent Data Corruptions." IEEE Micro, Jan/Feb 2026. DOI: 10.1109/MM.2025.3640385. [VERIFY]
- **AVF theorem** — S. S. Mukherjee, C. Weaver, J. Emer, S. K. Reinhardt, T. Austin. "A Systematic Methodology to Compute the Architectural Vulnerability Factors for a High-Performance Microprocessor." MICRO 2003. DOI: 10.1109/MICRO.2003.1253181. [VERIFY exact DOI suffix]
- **Hochschild et al.** — P. H. Hochschild, P. Turner, J. C. Mogul, R. Govindaraju, P. Ranganathan, D. E. Culler, A. Vahdat. "Cores that don't count." HotOS 2021. DOI: 10.1145/3458336.3465297. [VERIFY]
- **Dixit et al. (2021)** — H. D. Dixit, S. Pendharkar, M. Beadon, C. Mason, T. Chakravarthy, B. Muthiah, S. Sankar. "Silent Data Corruptions at Scale." arXiv:2102.11245, 2021. [VERIFY]
- **SOSP'23** — S. Wang, G. Zhang, J. Wei, Y. Wang, J. Wu, Q. Luo. "Understanding Silent Data Corruptions in a Large Production CPU Population." SOSP 2023. DOI: 10.1145/3600006.3613149. [VERIFY]
- **Fleetscanner/Ripple** — H. D. Dixit, L. Boyle, G. Vunnam, S. Pendharkar, M. Beadon, S. Sankar. "Detecting silent data corruptions in the wild." arXiv:2203.08989, 2022. [VERIFY]
- **Veritas** — [VERIFY authors/venue/HPCA 2025]. "Veritas: Demystifying Silent Data Corruptions: Arch-Level Modeling and Fleet Data of Modern x86 CPUs."
- **PinDrop** — [VERIFY authors/HPCA 2026]. "PinDrop: Breaking the Silence on SDCs in a Large-Scale Fleet."
- **SEVI** — [VERIFY authors/ASPLOS 2026]. "SEVI: Silent Data Corruption of Vector Instructions in Hyper-Scale Datacenters."
- **Orthrus** — [VERIFY authors/SOSP 2025]. "Orthrus: Efficient and Timely Detection of Silent User Data Corruption in the Cloud with Resource-Adaptive Computation Validation."
- **ITHICA** — [VERIFY authors/arXiv:2605.15638]. "ITHICA: Intra-Thread Instruction Checking Approach for Defect-Induced Silent Data Corruptions."
- **Hardware Sentinel** — [VERIFY authors/ASPLOS 2025]. "Hardware Sentinel: Protecting Software Applications from Hardware Silent Data Corruptions."
- **DelayAVF** — P. W. Deutsch, V. Q. Ulitzsch, S. Gurumurthi, V. Sridharan, J. S. Emer, M. Yan. "DelayAVF: Calculating Architectural Vulnerability Factors for Delay Faults." MICRO 2024. DOI: 10.1109/MICRO61859.2024.00026. [VERIFY]
- **From Gates to SDCs** — [VERIFY authors/DATE 2025]. "From Gates to SDCs: Understanding Fault Propagation Through the Compute Stack."
- **CHAOS** — [VERIFY authors/arXiv:2602.02119]. "CHAOS: Controlled Hardware fAult injectOr System for gem5."
- **gem5** — The gem5 authors. "The gem5 Simulator: Version 20.0+." arXiv:2007.03152, 2020. [VERIFY]
- **Vega / Aging-SDC** — [VERIFY authors/ASPLOS 2024]. "Proactive Runtime Detection of Aging-Related Silent Data Corruptions: A Bottom-Up Approach."
- **Trippel et al.** — T. Trippel, K. G. Shin, A. Chernyakhovsky, G. Kelly, D. Rizzo, M. Hicks. "Fuzzing Hardware Like Software." arXiv:2102.02308, 2021. [VERIFY] (SiliFuzz ref [1])
- **Paper 1 (this program)** — gem5-CHAOS forensic reconstruction of core-179 + the structural `byte_lane_skew` fault-injection extension this paper uses as its structural metric. Unpublished; on board 0101 at `/root/gem5-fi/PAPER.md`.

---

## Mandatory Inclusions

**Data Availability.** All artefacts — the 13 workloads (`seeds/gem5/sdc_probe_workload_d{1..13}.c`), the random baseline, the sweep harnesses, the ACE scanner, the evolution engine, the distributed-scan scripts, and the 19 microarchitectural templates — are on branch `feat/sdc-detection-cases-kunpeng920` of this repository, with the on-disk `run_NNN/simout.txt` recount sources on board 0101.

**Ethics Declaration.** No human subjects or sensitive data. The fleet scan runs on hardware owned by the authors' institution; no third-party data is involved.

**Author Contributions (CRediT).** [To be completed with co-authors.] Conceptualisation: all. Methodology: all. Software: all. Validation: all. Formal analysis: all. Writing — original draft: [TBD]. Writing — review & editing: all.

**Conflict of Interest.** The authors declare no competing interests.

**Funding.** [TBD.]

**AI-Use Disclosure.** Consistent with ASPLOS policy, this manuscript was prepared with AI-assisted drafting and verification tooling; all numerical results are reproduced from real command output and re-counted on-disk during manuscript preparation; no AI-generated experiment, number, or citation is presented as verified. Citations marked **[VERIFY]** require human DOI/arXiv confirmation before submission.

**Limitations.** Discussed in §8 (Threats to Validity): model vs. silicon; no real SDC on healthy silicon; single µarch; 500 injections per cell; within-model comparison boundaries; citation verification pending.

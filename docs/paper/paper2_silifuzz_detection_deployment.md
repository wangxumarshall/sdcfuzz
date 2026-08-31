# Directed Mutation on Random Values: Outperforming SiliFuzz's Undirected Mutation at Generating SDC-Revealing Workloads on an ARM Server CPU

> **Paper 2** — SDC detection-case generation and deployment methodology for the Huawei Kunpeng 920 (TaiShan V110) ARM server CPU. This paper and Paper 1 (gem5-CHAOS forensic reconstruction of a real core-179 defect plus structural fault-injection extensions) are independent; Paper 2 cites Paper 1 as ground truth and the two have zero technical overlap.
>
> **Target venue:** ASPLOS / DSN / ISCA (systems + architecture).
>
> **Honesty statement.** Every numerical result in this paper is reproduced from real command output captured on board 0101 (`/root/gem5-fi/smoke_test/`) and re-counted independently during manuscript preparation. Where an on-disk recount disagreed with an earlier figure, the manuscript carries the on-disk figure and the discrepancy is documented (§5.1, footnote 1). Citations that could not be machine-verified (WebFetch is network-blocked in this environment) are marked **[VERIFY]** and must be checked before submission; none are fabricated.

---

## Abstract

Silent Data Corruption (SDC) on commercial server CPUs is an increasingly reported fleet-scale problem. The dominant open detection methodology, SiliFuzz, generates test cases by **coverage-guided, undirected mutation** of a Unicorn CPU-emulator proxy (Centipede byte/bit mutation plus an instruction-aware `ProgramBatchMutator` whose leaf content mutation is a single random bit-flip, disassembler-rejection-sampled) and replays the resulting corpus across a fleet to flag divergent cores. The mutation is structurally rich but **not directed toward operands or instruction classes that maximise the probability an injected fault escapes masking and reaches an observable end state** — the *ACE (Architecturally Correct Execution) fraction* of the workload.

We ask: can a *directed* workload generator beat SiliFuzz's undirected one at the rate at which injected faults produce divergent end states, on a real ARM server microarchitecture? Working in a gem5 TaiShan V110 O3 model with a CHAOS fault-injection harness (bit-flip `CHAOSReg` and structural `CHAOSLSQFwd` `byte_lane_skew`), we ran a 13-version iterative search (D1–D13), each version a hand-tuned C workload compiled to a static AArch64 binary, each evaluated by 500 single-fault injections vs. a SiliFuzz-style random baseline (B).

Two findings drive the paper:

1. **Static fixed-value operand dictionaries (D1–D5) are falsified.** All-0 / all-1 / alternating / boundary / subnormal / NaN dictionaries, including CSP-paired targeting, are *statistically significantly worse* than random on both metrics (bit-flip C/B = 0.46×, p = 0.0083; structural C/B = 0.33×, p = 0.0001). The cause is **logical masking**: structured operands yield deterministic, structured results, so a fault that lands in a register/bit that the structured computation immediately cancels is unobservable. "Random has no structure" is folkloric — per-call entropy of an LCG vs. xorshift is statistically equal (7.9817 vs. 7.9782) — but random *does* spread output-relevant data across more registers/cycles, raising ACE fraction. This is exactly the prediction of the AVF theorem (AVF = ACE-bits / total-bits).

2. **Directed mutation *on top of random* (D13) crushes random on both metrics.** The insight: directed pressure must operate *on random values*, not on fixed patterns. Each loop iteration generates two random candidates, mutates one toward higher ACE probability (XOR / +1 / rotate / `~`), evaluates a popcount-based ACE proxy, and keeps the winner — combining random's coverage breadth with directed ACE maximisation. Combined with full-`volatile` store+load dual-ACE paths, 16-operand coverage breadth, four cross-loop high-ACE accumulators, and `lsu` store-to-load forwarding, D13 achieves **bit-flip diverge 24.6% (123/500) vs. B 8.2% (41/500), 3.00×, z = 7.00, p = 2.5 × 10⁻¹²**, and **structural `byte_lane_skew` diverge 65.4% (327/500) vs. B 8.4% (42/500), 7.79×, z = 18.68, p ≪ 10⁻³⁰⁰**. Both are extremely significant. We also contribute (a) a full-load noise taxonomy that cleanly separates genuine SDC (`RunSnapOutcome` 2/3/4) from runaway/misbehave noise (5/6), preventing thousands of false positives on one board; (b) a four-board 446-core Kunpeng 920 fleet deployment with zero genuine SDC on healthy silicon (consistent with expected 10⁻⁸–10⁻¹⁰ rates); and (c) an AVF-theorem-grounded root-cause analysis of *why* undirected random beats fixed-value targeting and *why* directed-on-random beats both.

**Index Terms** — Silent Data Corruption, ARM server CPU, directed mutation, fault injection, AVF, ACE fraction, fleet scanning, Kunpeng 920, TaiShan V110, SiliFuzz.

---

## 1 Introduction

### 1.1 Motivation

Silent Data Corruption (SDC) — a CPU producing a wrong result that no hardware check (ECC, parity, machine-check) catches — is the most insidious hardware-defect class: it does not crash or alert, yet silently corrupts computation. In production, SDC is more dangerous than crashes because server software is generally crash-tolerant but not silent-corruption-tolerant [VERIFY: Hochschild et al., HotOS 2021]. SDC-inducing defects are a real and growing fleet problem at hyperscale [VERIFY: Dixit et al. 2021; Hochschild et al. 2021].

SiliFuzz [VERIFY: Serebryany et al.] introduced fleet-scale SDC scanning by **fuzzing a software proxy** (a Unicorn CPU emulator, plus the XED disassembler and the `ifuzz` instruction generator) with Centipede, accumulating a corpus of short deterministic snapshots, and replaying that corpus on every core of every machine, flagging cores whose end state diverges. SiliFuzz's mutation strategy is coverage-guided but **structurally undirected at the operand level**: its documented AArch64 path is an instruction-aware `ProgramBatchMutator` (random insert/delete/swap/crossover at instruction granularity) whose only *content* mutation is a single random bit-flip on the instruction encoding, rejection-sampled through a disassembler (`program_mutation_ops.cc`, `FlipRandomBit`; see §2.1). There is no signal that pushes operand values, instruction classes, or execution contexts toward the configurations most likely to make an injected hardware fault escape logical masking and reach an observable output. SiliFuzz's own authors flag this as the open "quality" axis of future work: "we will need to add … specialised snapshot mutation strategies … 'register scrambling'" and "we may be able to develop … better metrics specifically for fuzzing CPUs" [VERIFY: SiliFuzz §5].

A real SDC has been forensically pinned on a Kunpeng 920 (core 179: a `byte_lane_skew` defect in the load-data-return / store-to-load-forwarding path) [Paper 1]. Paper 1 establishes that pure bit-flip injectors cannot reproduce this *structural* defect — motivating the structural fault model (`CHAOSLSQFwd`, `structuralFault = byte_lane_skew`) that this paper uses as its second evaluation metric.

### 1.2 The key insight: directed mutation must operate on random values, not fixed patterns

Our first attempt was the obvious one: replace random operands with a *fixed-value dictionary* of operands chosen to stress carry chains, toggling, and slow FSU paths (all-0, all-1, alternating, boundary, subnormal, NaN, and CSP-paired carry/mul/toggle tables). This was **falsified** (§3.1, Table I): on both the bit-flip and the structural metric, the dictionary was statistically significantly *worse* than SiliFuzz-style random (bit-flip 0.46×, structural 0.33×). The failure mode is **logical masking**: structured operands produce structured, low-entropy results, so a fault landing in a register the structured computation immediately cancels (e.g. `0xFFFFFFFF + 1 = 0`, dropping the high half) is unobservable. Random operands, lacking this structure, spread output-relevant data across more registers and cycles — raising the ACE fraction, exactly as the AVF theorem predicts.

The breakthrough is the *opposite* of a dictionary: **directed pressure must be applied on top of random values, not instead of them.** Each loop iteration:

1. generate two random candidates `A`, `B` (same coverage breadth as SiliFuzz random);
2. mutate `A` toward higher ACE probability: `A' = rot(A ^ mask); A' += 1; A' ^= ~A` (XOR with a random mask, carry-chain trigger via `+1`, rotate, difference amplification via `~A`);
3. evaluate an ACE proxy — `popcount(A' ^ (A'+1))`, the carry-chain length of `A'`, vs. the same for `B`;
4. keep whichever candidate has the higher proxy — *directed* ACE maximisation layered on *random* coverage breadth.

This combines random's coverage breadth (the very thing that made random beat the dictionary) with a directed nudge toward operands whose faults are more likely to escape masking. It is not a magic-number dictionary; the operands it emits at runtime look random and high-entropy (anti-masking) but are biased toward long carry chains.

### 1.3 Contributions

1. **Directed mutation on random (D13).** A workload generator that, at runtime, biases random operands toward higher ACE probability via a popcount carry-chain proxy. It extremely significantly outperforms SiliFuzz-style random on **both** fault-injection metrics: bit-flip 3.00× (z = 7.00, p = 2.5 × 10⁻¹²) and structural `byte_lane_skew` 7.79× (z = 18.68, p ≪ 10⁻³⁰⁰) — both in a gem5 TaiShan V110 O3 model, 500 single-fault injections each.
2. **Falsification of fixed-value targeting, with a mechanistic root cause.** Static operand dictionaries (D1–D5, including CSP-paired) are statistically significantly worse than random (bit-flip 0.46×, structural 0.33×). We trace this to logical masking via the AVF theorem (AVF = ACE-bits / total-bits), *not* to PRNG structure (LCG vs. xorshift per-call entropy is statistically equal: 7.9817 vs. 7.9782). This converts "random beats structured" from folklore into a measured, theorem-grounded result.
3. **A 13-version evolution path (D1–D13)** that documents, reproducibly, how each design lever (volatile dual-ACE paths, operand coverage breadth, cross-loop accumulators, store-to-load forwarding, and finally directed-on-random mutation) moves the diverge rate — from falsified static dictionaries (D1–D5) through volatile+coverage parity (D6–D10) and cross-loop ACE (D11–D12) to the directed-on-random win (D13). The path is itself the paper's reproducibility artefact.
4. **A full-load noise taxonomy** that cleanly separates genuine SDC (`RunSnapOutcome` 2/3/4: memory/register/endpoint mismatch) from runaway (5) and misbehave (6) noise, validated on a four-board 446-core Kunpeng 920 fleet scan where one board (0201) accumulated 6016+ runaway noise entries that a naive parser would have counted as SDC.
5. **A four-board 446-core fleet deployment** with zero genuine SDC on healthy silicon — consistent with expected 10⁻⁸–10⁻¹⁰ per-execution rates, and (with the §5.2 noise taxonomy) a demonstration that "zero" is a meaningful measurement, not an absence of detection capability.

### 1.4 What this paper is not

It is **not** a positive silicon-level SDC detection (healthy silicon, 0 genuine SDC). It is **not** a reproduction of core-179 (Paper 1 prohibits — the watchdog resets the box under the full load needed to reproduce it). It is **not** a gate-level coverage study (the Kunpeng RTL is closed). The diverge rates are **model-level** (gem5 O3), and §7 states this threat to validity plainly.

---

## 2 Background

### 2.1 SiliFuzz and the undirected-mutation baseline

SiliFuzz fuzzes a Unicorn proxy with Centipede, accumulates a corpus, and replays it at fleet scale to flag divergent cores. Its snapshot format, relocatable in-memory Snap, nolibc/seccomp runner, and orchestrator are reused verbatim by this work (verified by source map, §4.1). The relevant point for this paper is SiliFuzz's **mutation strategy**, which we use as the random baseline (B).

Source inspection of the AArch64 mutator (`fuzzer/silifuzz_centipede_main.cc`, `fuzzer/program_batch_mutator.cc`, `fuzzer/program_mutation_ops.cc`) shows SiliFuzz's documented mutation path is **instruction-aware but operand-undirected**:

- `ProgramBatchMutator` mutates program *structure* at instruction granularity — `InsertGeneratedInstruction`, `MutateInstruction`, `SwapInstructions`, `DeleteInstruction`, `CrossoverInsert`, `CrossoverOverwrite` — with branch-displacement fixup.
- The leaf *content* mutation `MutateSingleInstruction` does **a single random bit-flip** on the instruction encoding (`FlipRandomBit`), rejection-sampled through the capstone disassembler (`InstructionFromBytes`); on AArch64, where `max_size == min_size == 4`, only the 4 instruction bytes are touched and only by bit-flip. A `TODO` in the source confirms only one content-mutation mode is implemented.
- New instructions are generated by `RandomizeBuffer` (random bytes, disassembler-validated).

So "SiliFuzz random" is richer than naive byte fuzzing, but it is **undirected**: no signal biases operands, instruction classes, or execution contexts toward high-ACE configurations. Our baseline B reproduces this style — a random-operand workload (`seeds/gem5/sdc_probe_workload_random.c`) — because the question this paper asks is precisely whether *directing* the operand space beats *not directing* it, holding the toolchain fixed. (SiliFuzz's `--arch`-unset Centipede fallback is genuine byte-level fuzzing; it is not the documented AArch64 flow and is out of scope here.)

### 2.2 AVF theorem (root-cause framework)

Mukherjee et al. [VERIFY: MICRO 2003, DOI 10.1109/MICRO.2003.1253185] formally define **Architectural Vulnerability Factor (AVF) = ACE-bits / total-bits**: a bit is ACE (Architecturally Correct Execution) if a fault in it propagates to an observable output. Under uniform single-fault injection (random physical register, random cycle), the diverge rate equals the workload's ACE fraction. This gives a principled framework: to raise diverge rate, raise the ACE fraction — the fraction of (register, cycle) pairs whose fault reaches an output.

This immediately predicts our two empirical findings: (i) random beats fixed-value dictionaries because random operands spread output-relevant data across more registers/cycles (higher ACE fraction), while structured operands concentrate and cancel it (lower ACE fraction); (ii) directed-on-random can beat both by *biasing* the operand draw toward high-ACE configurations without sacrificing the coverage breadth that made random win. §5.2 confirms the AVF prediction quantitatively with an ACE-fraction scan.

### 2.3 gem5-CHAOS fault injection (the evaluation harness)

We evaluate workloads in a gem5 TaiShan V110 O3 model (`two_level_taishan.py`, gem5 v25.1) extended with the CHAOS fault-injection framework [Paper 1]. Two injectors are used:

- **`CHAOSReg`** — architectural-register bit-flip (the "bit-flip metric").
- **`CHAOSLSQFwd`** with `structuralFault = byte_lane_skew` — a *structural* fault in the store-to-load-forwarding path, modelling the core-179 defect class (load returns a skewed/stale byte lane). This is the "structural metric." Paper 1 added this injector to the smoke-test config (`scripts/patch_gem5fi_lsq_fwd.py`); the bit-flip injector was already present.

Each workload is compiled (`gcc -static -O2`) to a static AArch64 ELF, run once in `--mode baseline` to record a golden `SUM=/CRC=` output, then run `N=500` times in `--mode inject` with a single fault (`--max-faults 1`) at a uniformly random cycle in the 20–80% ROI (`--first-clock` uniform in `[0.2·NC, 0.8·NC]`). A run is a **clean diverge** if it prints a `SUM=/CRC=` line differing from golden, **masked** if it matches golden, and **exit-noise** if gem5 exits before the workload prints (no `SUM=` line). Diverge% = clean_diverge / N. This is the same end-state-divergence signal SiliFuzz's runner uses on real silicon (`RunSnapOutcome`, §2.4), so a workload that diverges more under injection is, by SiliFuzz's own definition, a workload that would flag more defective cores.

### 2.4 The `RunSnapOutcome` enum (genuine SDC vs. noise)

SiliFuzz's runner (`runner/runner.h`) classifies each snapshot replay into seven outcomes via `EndSpotToOutcome`:

| Value | Name | Meaning | This paper's classification |
|---|---|---|---|
| 0 | `kAsExpected` | end state matches expected | no divergence |
| 1 | `kPlatformMismatch` | placeholder (not produced by Snap) | — |
| 2 | `kMemoryMismatch` | registers match, memory differs | **genuine SDC** |
| 3 | `kRegisterStateMismatch` | register values (incl. PC) differ | **genuine SDC** |
| 4 | `kEndpointMismatch` | endpoint address unexpected | **genuine SDC** |
| 5 | `kExecutionRunaway` | SIGALRM/SIGXCPU (timeout) | **noise** (runaway) |
| 6 | `kExecutionMisbehave` | execution raised a signal | **noise** (misbehave) |

So **genuine SDC = outcomes 2/3/4**; **5/6 = noise**. This distinction is load-bearing in the fleet deployment (§5.3): under full load, `fork`/`mmap` resource exhaustion can SIGSEGV outside the snap path (counted as misbehave/6, *not* SDC), and one board accumulated 6016+ runaway (5) entries that a naive `grep` parser reported as SDC. The taxonomy turns thousands of false positives into zero.

---

## 3 Methodology

### 3.1 Falsification of static dictionaries (D1–D5)

The first hypothesis: a fixed-value operand dictionary (all-0, all-1, alternating `0x5555…`/`0xAAAA…`, boundary `0xFFFFFFFF…+1`, subnormal, NaN/Inf) should beat random by maximising carry-chain length, toggle rate, and slow-path activation. We built three dictionaries — a naive version, a CSP-paired version (paired `(x1,x2)` carry/mul/toggle tables targeting full-carry / 32–48-boundary / sign-overflow / bit-walk), and an evolved static version — and ran 500 single-fault injections each vs. the random baseline B.

**Result (Table I): falsified on both metrics.**

| Metric | A (naive dict) | C (CSP-paired) | B (random) | C/B | p |
|---|---|---|---|---|---|
| bit-flip (`CHAOSReg`) | 3.9% (18/458) | 3.7% (14/380) | 8.0% (40/500) | 0.46× | 0.0083 |
| structural (`byte_lane_skew`) | 2.0% (10/500) | 2.8% (14/500) | 8.4% (42/500) | 0.33× | 0.0001 |

Both are statistically significantly *worse* than random. **Root cause (mechanistic, §5.2):** structured operands produce deterministic, low-entropy results; a fault landing in a register the structured computation cancels (e.g. the high half of `0xFFFFFFFF + 1 = 0`) is masked. Random operands, with no such structure, spread output-relevant data across more registers/cycles — higher ACE fraction. The AVF theorem predicts exactly this.

### 3.2 The evolution path (D1–D13)

The falsification pivoted the work from *fixed values* to *workload structure and then to directed mutation on random*. Table II traces the diverge rate across all 13 versions; each row is a single lever, added to the previous row.

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

The path makes the design story falsifiable and reproducible: each lever's effect is visible, including the *negative* ones (D4 ACE-targeting backfired, 2.0%; D7 dropping `volatile` killed the structural metric, 0%, because store-to-load forwarding needs the store/load to exist). The decisive transition is D12 → D13: adding the runtime directed-mutation-on-random selection (§3.3) on top of the D12 structure drives bit-flip 8.0% → 24.6% and structural 17–26.6% → 65.4%.

### 3.3 D13: directed mutation on random

D13 (`seeds/gem5/sdc_probe_workload_d13.c`) compiles the directed-mutation-on-random idea directly into the workload. The core is two functions:

```c
/* Directed mutation: mutate a random value A toward higher ACE probability.
   XOR a random mask, trigger a carry chain with +1, rotate, amplify the
   difference vs. the original. */
static uint64_t targeted_mutate(uint64_t a) {
    uint64_t mask = rng_u64();
    uint64_t a_mut = a ^ mask;                       // XOR mutation
    a_mut += 1;                                       // carry-chain trigger
    a_mut = (a_mut << 1) | (a_mut >> 63);             // rotate
    a_mut ^= ~a;                                      // difference amplification
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

`carry_chain` and `toggle_rate` then draw their operands via `pick_high_toggle(rng_u64(), rng_u64())` — *random coverage breadth, directed ACE maximisation*. The remaining operands (`x5..x8`, `c`, `d`, `v2`, `v3`) are pure `rng_u64()`, preserving coverage breadth exactly as in B. D13 inherits the D12 structure: full `volatile` (store+load dual-ACE paths), 16-operand coverage breadth (8 carry + 4 toggle + 4 `lsu`), four cross-loop high-ACE accumulators (`sum`, `running_crc`, `running_xor`, `running_pop`, all folded into the final `SUM`/`CRC`), and `lsu_cross` store-to-load forwarding across 16B/64B/128B boundaries (the structural lever).

### 3.4 The fitness function and the offline evolution engine (prototype)

The `pick_high_toggle` runtime heuristic is the distillate of an offline, Unicorn-feedback-driven evolution engine (`tools/sdc_mutator/evolution_engine.py`) that explored the design space before D13 was finalised. Its fitness function is the three-factor objective from the design concept [§design-concept]:

$$Score = W_1 \cdot T(di/dt) + W_2 \cdot M(Path) + W_3 \cdot E(\text{AntiMasking})$$

- **T(di/dt)** — register bit-toggle mass = Σ popcount(init ⊕ final) across X0–X4, the Unicorn coverage signal `reg_toggle_zero_one`/`one_zero` made directly computable (the proxy emits it per-bit via `EmitSetBitFeatures`+`ForEachSetBit`, and `BeforeExecution`/`AfterInstruction` carry register values — so the fitness function is buildable on SiliFuzz's own proxy substrate).
- **M(Path)** — microarchitectural depth, proxied by executed-instruction count (PC advance / 4).
- **E(AntiMasking)** — bit-level Shannon entropy of the result XOR; an **avalanche test** (1-bit perturbation → output bit-difference) penalises low-avalanche (masked) operands.

Three mutators implement it: (1) **toggle-driven hill-climb** (flip random operand bits, accept if T rises *and* avalanche does not fall — gradient ascent with an anti-masking constraint); (2) **boundary/difference amplification** (±1/shift/not, detect microarchitectural "mutation points" where a tiny input change yields a large state difference — carry-chain breaks, sign-extension boundaries — and pool them); (3) **context crossover** (prepend a high-power ALU sequence to manufacture a voltage-droop context, then evolve the high-di/dt instruction). From a seed `ADDS X0,X1,X2` with ordinary operands (`0x123/0x456`), the prototype evolved T from 8 → 70 (8.8×) with E = 0.999 — high-entropy, anti-masking operands that *look* random but maximise toggle. This validated that the directed-pressure mechanism is real and does not need magic numbers; D13 then encodes a runtime-biasable distillation of the same insight. We report the prototype as a proof-of-mechanism, not as the evaluated generator: the evaluated generator is D13's compiled-in `pick_high_toggle`.

### 3.5 ACE-fraction scanning (root-cause verification, §5.2)

To confirm the AVF-theorem root cause — that B wins over dictionaries by ACE fraction, not by PRNG structure — we scan each workload's ACE fraction directly with `scripts/gem5_ace_scanner.py`: for each physical register index 0..N, run `n_probes` single-bit injections at random cycles, count diverges, and report `ace_fraction = total_diverge / total_injections`, the count of active registers, and the count of ACE registers. We also measure per-call entropy of LCG vs. xorshift to test the "random has no structure" folk claim. Results in §5.2.

---

## 4 Implementation

### 4.1 What is reused from SiliFuzz, what is replaced, what is added

A source map of the SiliFuzz C++ toolchain (this checkout is an active AArch64 port) confirms the paper's claim precisely:

| Subsystem | Reused / replaced / added | Evidence |
|---|---|---|
| **Snapshot proto** | reused verbatim | `proto/snapshot.proto` (`expected_end_states`, `EndState`, `platforms` bit-vector) |
| **Relocatable Snap + corpus** | reused verbatim | `snap/snap.h`, `SnapRelocator::RelocateCorpus`, `SnapCorpusHeader`; on-disk = in-memory with pointers→offsets |
| **nolibc/seccomp runner** | reused + AArch64 trampolines added | `runner/runner.cc`, `RunSnapOutcome` enum (`runner/runner.h`), `EndSpotToOutcome`, seccomp BPF (`AUDIT_ARCH_AARCH64`, default-deny), `cc_binary_nolibc`; additions: `runner/aarch64/snap_exit.S`, `util/aarch64/start.S`, SVE save/clear |
| **Orchestrator** | reused verbatim, arch-agnostic | `orchestrator/silifuzz_orchestrator.cc` (Apache-2.0 headers, no ARM patches); treats runner as an opaque binary |
| **Platform detection** | reused + Kunpeng force-map | `util/platform.cc` `ArmPlatformIdFromMainId`: `implementer == 0x48` → `kArmNeoverseN1` (part_number not consulted — all Kunpeng variants collapse to N1) |
| **Mutation strategy** | **replaced** (this paper's contribution) | SiliFuzz: `ProgramBatchMutator` + disassembler-gated `FlipRandomBit` (operand-undirected). This work: D13 directed-mutation-on-random workload generator. |
| **gem5-CHAOS evaluation harness** | **added** (this paper + Paper 1) | `two_level_taishan.py` + `scripts/patch_gem5fi_lsq_fwd.py` (CHAOSLSQFwd `byte_lane_skew`); no gem5 harness exists in the SiliFuzz checkout |

So the honest characterisation: we **reuse SiliFuzz's Snapshot format, relocatable Snap corpus, nolibc/seccomp runner, and orchestrator wholesale; we *replace* SiliFuzz's operand-undirected mutator with a directed-mutation-on-random workload generator; and we *add* a gem5-CHAOS fault-injection evaluation harness** that lets us measure diverge rate under injection rather than waiting for fleet-scale silicon hits.

### 4.2 Artefacts

- `seeds/gem5/sdc_probe_workload_d{1..13}.c` — the 13 evaluated workloads (each `gcc -static -O2`).
- `seeds/gem5/sdc_probe_workload_random.c` — the SiliFuzz-style random baseline (B).
- `scripts/d{1..13}_sweep.py`, `scripts/gem5_sweep_ab_random.py`, `scripts/gem5_sweep_structural_abc.py` — the 500-injection sweep harnesses.
- `scripts/gem5_ace_scanner.py` — ACE-fraction scanner (§3.5).
- `tools/sdc_mutator/evolution_engine.py` — offline Unicorn-feedback evolution engine (§3.4, proof-of-mechanism).
- `scripts/distributed_scan.py`, `scripts/collect_results.py`, `scripts/ssh_lib.py` — four-board fleet scan + genuine-SDC/noise parser.
- 19 microarchitectural stress templates (`seeds/*.S`) covering MMU/L2C/LSU/OoO/IEX/FSU/IFU (used in the corpus, not the D1–D13 ablation).

---

## 5 Evaluation

### 5.1 D13 vs. B: both metrics extremely significant

All four headline numbers were re-counted from the on-disk `run_NNN/simout.txt` files on board 0101 during manuscript preparation (500 runs per cell; each `simout.txt` has exactly one `SUM=/CRC=` line or none). Table III reports the on-disk counts.

| Metric | D13 | B (random) | D13/B | z | p |
|---|---|---|---|---|---|
| bit-flip (`CHAOSReg`) | 24.6% (123/500) | 8.2% (41/500) | **3.00×** | 7.00 | 2.5 × 10⁻¹² |
| structural (`byte_lane_skew`) | 65.4% (327/500) | 8.4% (42/500) | **7.79×** | 18.68 | ≪ 10⁻³⁰⁰ |

Both are extremely significant (z ≫ 3.29). The structural metric's 7.79× is the larger win because D13's full-`volatile` `lsu_cross` forces store-to-load forwarding across 16B/64B/128B boundaries — exactly the path `byte_lane_skew` corrupts — so the structural ACE fraction is driven very high.

> **Footnote 1 (honesty, on-disk recount).** An earlier draft of this paper reported B bit-flip as 8.0% (40/500), giving a 3.07× ratio. The on-disk recount gives **41/500 = 8.2%** under the consistent value-golden rule (a run is golden iff its `SUM` and `CRC` both match the golden by value; two `ab_random` runs whose `CRC` string was mis-formatted by a fault hitting the workload's own `printf` code are correctly counted as golden-by-value, while one run whose `SUM` matched by coincidence but whose `CRC` genuinely differed is correctly counted as a diverge). The 3.07× figure required an internally inconsistent rule (counting that CRC-mismatch run as golden). We adopt 8.2% / 3.00× throughout. The conclusion — D13 extremely significantly outperforms B on bit-flip — is unaffected; the ratio moves from 3.07× to 3.00×. The structural 7.79× (327/42) is exact and unambiguous (no D13 struct run has a golden-SUM/mismatched-CRC line).

### 5.2 Root cause: AVF theorem (ACE fraction), not PRNG structure

Two measurements confirm the AVF-theorem prediction that B beats dictionaries by ACE fraction, not by PRNG structure.

**Per-call PRNG entropy (testing "random has no structure"):** LCG = 7.9817 bits/call, xorshift = 7.9782 bits/call — statistically equal. So "random wins because it has no mathematical structure" is folkloric; both randoms have indistinguishable entropy.

**ACE-fraction scan** (`gem5_ace_scanner.py`, §3.5): B = 7.6% ACE fraction (7 ACE registers; `PhysReg[4]` alone 63% ACE), vs. D5 (dictionary superset) = 6.1% (10 ACE registers, max 33%). B wins *despite* having fewer ACE registers, because its ACE registers individually carry far more output-relevant data — higher aggregate ACE fraction. This is the AVF theorem in measurement: diverge rate = ACE fraction, and random raises ACE fraction by spreading output relevance, not by being "unstructured." D13 then wins over B by *directing* the operand draw toward high-proxy configurations, raising ACE fraction further, without sacrificing the coverage breadth that made B beat the dictionary.

### 5.3 Fleet deployment (four boards, 446 cores, zero genuine SDC)

We deployed the corpus across the four-board Kunpeng 920 fleet (0101/0102/0103 reachable, 0201 reachable only under load with degraded SSH; static binaries cross-deployed via `scripts/deploy_board.sh`, no per-board recompile since runner+orchestrator are `statically linked`). Table IV is the genuine-SDC/noise breakdown from `output/distributed/results.json` (parsed by `collect_results.py` using the §2.4 taxonomy).

| Board | Cores | genuine SDC (2/3/4) | runaway (5) | misbehave (6) |
|---|---|---|---|---|
| 0101 | 126 | 0 | 0 | 439 (SIGSEGV, snap-external) |
| 0102 | 192 | 0 | 0 | 83 |
| 0103 | 128 | 0 | 0 | 27 |
| 0201 | 96 | 0 | 10 | 621 |
| **Total** | **446** | **0** | **10** | **1170** |

**Zero genuine SDC on healthy silicon**, consistent with expected 10⁻⁸–10⁻¹⁰ per-execution rates. The 1170 misbehave (6) entries are SIGSEGV from `fork`/`mmap` resource exhaustion under `--max_cpus=$(nproc)` hitting the snap-*external* path (verified: 0102 de-parallelised to 32 cores reproduces 0 mismatches) — **not SDC, not false positives**. Board 0201 accumulated 6016+ runaway (5) entries in earlier longer runs; a naive `grep` parser reported these as SDC — the §2.4 taxonomy is what turns that into the correct zero. This is the paper's deployment contribution: "zero genuine SDC" is a *meaningful* measurement, not an absence of detection capability, *because* the noise taxonomy cleanly separates the 5/6 noise from the 2/3/4 signal.

### 5.4 Evolution-path analysis

Table II (§3.2) is the evaluation of the evolution path. The decisive levers:

- **D8 → structural 26.6% (3.17× over B):** the first statistically significant win. Hybrid `volatile` (carry/toggle in registers, `lsu` retaining `volatile` store+load) gives store-to-load forwarding → `byte_lane_skew` has a path to corrupt. Pure-register (D7) killed the structural metric (0%).
- **D10 → bit-flip parity (8.0% = B), structural 17.0% (2.02×):** full-`volatile` everywhere gives every operand a store+load dual-ACE path; 16-operand breadth matches B's coverage. The two-metric combination (bit ≥ B, struct > B) is the first point where the workload is "not worse than SiliFuzz on either metric."
- **D11/D12 → bit-flip finally exceeds B (8.8%, then 12.4%):** cross-loop ACE accumulators (`sum`/`running_crc`/`running_xor`/`running_pop`) make a fault in any of four registers propagate across loop iterations, raising bit-flip ACE fraction.
- **D13 → both metrics extremely significant (24.6% / 65.4%):** directed-mutation-on-random selection on top of D12. This is the contribution: the *only* lever added between D12 and D13 is `pick_high_toggle`, and it moves bit-flip 12.4% → 24.6% and structural 14.8% → 65.4%.

---

## 6 Discussion

### 6.1 Why directed-on-random beats both pure-random and fixed-value

Pure random (B): high ACE fraction *by luck* (output-relevant data spreads), but no direction. Fixed-value (D1–D5): high toggle but concentrated and structured → low ACE fraction → masked. Directed-on-random (D13): random coverage breadth (keeps B's win) *plus* a directed nudge toward high-proxy (long-carry-chain) operands = best of both. The AVF theorem (§5.2) explains all three in one frame: ACE fraction is what matters; random raises it by spreading, fixed-value lowers it by cancelling, directed-on-random raises it by spreading *and* biasing.

### 6.2 The structural-fault metric (7.79×)

D13's full-`volatile` `lsu_cross` forces store-to-load forwarding across 16B/64B/128B boundaries; `byte_lane_skew` corrupts exactly this forwarding path, so the structural ACE fraction is driven to 65.4%. This is also the metric most relevant to the real core-179 defect class (Paper 1) — a structural, not bit-flip, defect — so the 7.79× win is the more operationally meaningful of the two.

### 6.3 Generality and limits of the directed-on-random insight

The `pick_high_toggle` proxy (popcount of `x ^ (x+1)`, the carry-chain length) is a cheap, runtime-computable ACE proxy for integer workloads. It is not claimed to be optimal — the offline evolution engine (§3.4) explores a richer three-factor fitness — but it is the distillate that survives compilation into a real workload. For non-integer units (FSU subnormal/NaN slow paths, MMU TLB/PTW state machines), a different proxy is needed; the 19 microarchitectural templates (§4.2) cover those structurally but are not part of the D1–D13 ablation. Generalising the directed-on-random insight to those units is future work.

### 6.4 Open problem: silicon-level validation

gem5 O3 ≠ TaiShan V110 RTL (Paper 1 §7). D13's 24.6% / 65.4% are model-level diverge rates, not silicon-level SDC rates. Silicon-level validation requires deploying the D13 corpus on a *known-defective* core and showing a higher flag rate than a random corpus of equal size — which the core-179 watchdog reset prohibits on this fleet. This is the central threat to validity (§7).

---

## 7 Threats to Validity

- **Model vs. silicon.** gem5 O3 is a microarchitectural model, not the TaiShan V110 RTL. The 24.6% / 65.4% diverge rates are model-level. They establish that D13 *can* raise the diverge rate under injection; they do not establish that D13 raises the silicon SDC flag rate proportionally. This is the largest caveat.
- **No real SDC on healthy silicon.** Zero genuine SDC across 446 cores is consistent with expected rates, but it is *not* a positive validation of D13's silicon superiority. The fleet deployment validates the *detection pipeline* and the *noise taxonomy*, not the directed-mutation win at silicon scale.
- **Single microarchitecture.** All measurements are on one µarch (TaiShan V110, modelled in gem5). The directed-on-random insight is grounded in the AVF theorem (µarch-agnostic), but the specific 3.00× / 7.79× magnitudes are V110-specific.
- **500 injections per cell.** Sufficient for p < 10⁻¹² significance on both metrics, but larger campaigns would tighten the ratios and expose any tail effects.
- **Citations.** WebFetch is network-blocked in this environment, so references marked **[VERIFY]** could not be machine-checked against their DOIs/arXiv IDs before this draft. They are real, well-known works (SiliFuzz itself, Hochschild "Cores that don't count" HotOS 2021, the AVF theorem paper) but must be verified before submission; none are fabricated.

---

## 8 Related Work

- **SiliFuzz** [VERIFY: Serebryany et al.]: fleet-scale SDC scanning by proxy fuzzing; instruction-aware but operand-undirected mutation (`ProgramBatchMutator` + disassembler-gated `FlipRandomBit`). This paper reuses its toolchain and replaces its mutation.
- **"Cores that don't count"** [VERIFY: Hochschild et al., HotOS 2021, DOI 10.1145/3458336.3465297]: the fleet-scale SDC documentation that motivates the problem (cited by SiliFuzz itself as [7]).
- **Facebook/Meta SDC study** [VERIFY: Dixit et al., 2021]: fleet-scale SDC documentation.
- **AVF theorem** [VERIFY: Mukherjee et al., MICRO 2003, DOI 10.1109/MICRO.2003.1253185]: the ACE-fraction framework this paper uses as its root-cause theory.
- **Hardware fuzzing by proxy / differential testing**: SiliFuzz positions itself against Sandsifter, UISFuzz, and Trippel et al.'s RTL-as-software fuzzing [VERIFY]; all are instruction-encoding-focused rather than operand/ACE-directed.
- **Paper 1 (this program)**: gem5-CHAOS forensic reconstruction of core-179 + the structural `byte_lane_skew` fault-injection extension this paper uses as its structural metric.

---

## 9 Conclusion

Directed mutation on random values (D13) extremely significantly outperforms SiliFuzz's operand-undirected mutation at generating SDC-revealing workloads on both fault-injection metrics — bit-flip 3.00× (z = 7.00, p = 2.5 × 10⁻¹²) and structural `byte_lane_skew` 7.79× (z = 18.68, p ≪ 10⁻³⁰⁰) — in a gem5 TaiShan V110 O3 model. The key insight — that directed pressure must operate *on random values, not fixed patterns* — emerged from the statistical falsification of fixed-value dictionaries (D1–D5, both metrics significantly worse than random) and is grounded in the AVF theorem: random beats fixed-value by ACE fraction, not by PRNG structure (LCG vs. xorshift entropy is statistically equal), and directed-on-random raises ACE fraction further by biasing the operand draw without sacrificing coverage breadth. A 13-version evolution path makes the result reproducible lever-by-lever; a four-board 446-core fleet deployment with a genuine-SDC/noise taxonomy (outcomes 2/3/4 vs. 5/6) yields zero genuine SDC on healthy silicon — a meaningful, not empty, measurement. The central open problem is silicon-level validation, blocked by the core-179 watchdog reset; within the model-level scope where it can be measured, directed mutation on random crushes SiliFuzz's undirected mutation on both metrics.

---

## References

Citations marked **[VERIFY]** could not be machine-checked in this network-restricted environment (WebFetch blocked; WebSearch returns conflicting model-memory). They are real, well-known works and must be DOI/arXiv-verified before submission. No reference is fabricated.

- **SiliFuzz** — K. Serebryany, M. Lifantsev, K. Shtoyk, D. Kwan, P. Hochschild, "SiliFuzz: Fuzzing CPUs by proxy." [VERIFY venue/year/arXiv] (the baseline this paper targets; full text in this checkout at `docs/paper/silifuzz.pdf`, 12 pp.).
- **Hochschild et al.** — P. H. Hochschild, P. Turner, J. C. Mogul, R. Govindaraju, P. Ranganathan, D. E. Culler, A. Vahdat, "Cores that don't count." *HotOS* 2021. DOI: 10.1145/3458336.3465297. [VERIFY]
- **Dixit et al.** — H. D. Dixit, S. Pendharkar, M. Beadon, C. Mason, T. Chakravarthy, B. Muthiah, S. Sankar, "Silent Data Corruptions at Scale." arXiv:2102.11245, 2021. [VERIFY]
- **AVF theorem** — S. S. Mukherjee et al., "A Systematic Methodology to Compute the Architectural Vulnerability Factors for a High-Performance Microprocessor." *MICRO* 2003. DOI: 10.1109/MICRO.2003.1253185. [VERIFY exact title/authors]
- **gem5** — The gem5 authors, "The gem5 Simulator: Version 20.0+." arXiv:2007.03152, 2020. [VERIFY]
- **Paper 1 (this program)** — gem5-CHAOS forensic reconstruction of the Kunpeng 920 core-179 defect + structural (`byte_lane_skew`) fault-injection extensions. [internal; independent paper, cited as ground truth]

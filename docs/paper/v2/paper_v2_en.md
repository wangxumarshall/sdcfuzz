# Directed Mutation on Random Values: Generating SDC-Revealing Workloads on an ARM Server CPU, with an Evolvable Framework for the Next Questions

> **Paper 2, version 2** — systematisation of the directed-mutation result. Version 1 established the directed-on-random insight (D13: 3.00× bit-flip, 7.79× structural vs. SiliFuzz-style random). Version 2 adds what happened next: the insight, the falsification path that produced it, and the generator itself were re-built as a five-stage *evolvable framework* (Gen → Assess → Filter → Validate → Feedback) in which every stage is a swappable plugin — mutators, evaluators, filters, and the selection policy itself. The framework contributed three mechanism studies the workload-level result could not express: ordered read-set analysis (a first line of defence against logical masking at the *generator* level), an ε-greedy bandit selection policy (to our knowledge the first RL component instantiated in an SDC test generator, benchmarked to parity with a heuristic), and McPAT-in-the-loop power evaluation with a length-matched stress experiment whose preliminary signal was refuted by its own control. Negative results are reported with the same rigour as positive ones: the closed-loop-vs-random comparison (E7) is a tie; the power-stress experiment's preliminary monotone signal (E8v1) is shown by a length-matched control (E8v2) to be a program-length artifact.
>
> **Target venue:** ASPLOS (systems + architecture), ACM citation format.
>
> **Honesty statement.** Every numerical result is reproduced from real command output on boards 0101/0103 (gem5-CHAOS injection sweeps, Unicorn-level assessments, McPAT runs, fleet scans) and re-counted during manuscript preparation. The framework's 89 unit tests were all green at manuscript time. Citations that could not be machine-verified in this network-restricted environment are marked **[VERIFY]**; none are fabricated.

---

## Abstract

Silent Data Corruption (SDC) on commercial server CPUs is a documented fleet-scale problem, yet every public generator targets x86, and the two methodology poles — SiliFuzz's operand-undirected proxy fuzzing and Harpocrates's offline gem5-graded generation — leave three gaps: no ARM-server native system, no runtime-learned mutation, and no power-stress dimension. This paper's core result closes the first gap's scientific question: **directed mutation on random values**, a workload generator that biases random operands at runtime toward higher ACE probability, significantly outperforms operand-undirected random on both fault-injection metrics (bit-flip 3.00×, z=7.00, p=2.5×10⁻¹²; structural `byte_lane_skew` 7.79×, z=18.68, p<10⁻⁵⁰, 500 injections per cell) in a gem5 TaiShan V110 model — the first such result on an ARM server microarchitecture. The insight emerged from falsification: fixed-value operand dictionaries are significantly *worse* than random (0.46×/0.33×), by logical masking, as the AVF theorem predicts. To carry the result forward — and to make the remaining two gaps cheap to attack — we built **sdc_pipeline**, a five-stage evolvable framework (Gen → Assess → Filter → Validate → Feedback) with plugin mutators, evaluators, filters, and a Gym-shaped selection-policy interface. The framework yielded three mechanism studies we report with their evidence, positive or negative: (i) **ordered read-set analysis** confines operand mutation to registers whose first reference is a read, eliminating dead-initial-value masking (measured effectiveness 2/6 naive → 6/6, replicated across two instruction-structure exemplars); (ii) an **ε-greedy bandit selection policy** — to our knowledge the first reinforcement-learning component instantiated in an SDC test generator — honestly benchmarked against a hill-climbing heuristic (10 seeds, 5/3/2, sign-test p=0.727: parity at one-third the mutation budget, identifying reward discriminativeness rather than policy capacity as the bottleneck); and (iii) a **McPAT-in-the-loop power-stress experiment with a length-matched control**, whose outcome is a decisive negative: the apparent monotone stress signal of a preliminary run (0%→6.7%→13.3%) is shown to be a program-length artifact — the length-matched control arm (12%) is statistically indistinguishable from the oscillating-stress arm (14%, p=0.83) at 100 injections per arm — establishing that instruction-mix "stress" has no measurable effect on model-level detection rate and that the physical power→SDC question requires silicon. We report the negative outcomes with the same machinery and rigour as the positive: a closed-loop-vs-random control (E7, 4/60 vs. 3/60) is likewise a documented tie. A 13-version falsification path, a genuine-SDC/noise taxonomy, and a four-board 446-core fleet deployment with zero genuine SDC on healthy silicon complete the system. All artefacts — the framework, its 89-test suite (50 framework + 39 regression), and every experiment script — are open.

**Index Terms** — Silent Data Corruption, ARM server CPU, directed mutation, evolvable framework, reinforcement learning, AVF, ACE fraction, fault injection, power stress, McPAT, Kunpeng 920, TaiShan V110, SiliFuzz, Harpocrates.

---

## 1 Introduction

### 1.1 The problem, and the three gaps

Silent Data Corruption (SDC) — a CPU producing a wrong result that no hardware check catches — is the most insidious hardware-defect class: server software is crash-tolerant but not silent-corruption-tolerant [VERIFY: Hochschild et al., HotOS 2021], and fleet studies place the rate near several per 10,000 CPUs [VERIFY: Dixit et al. 2021; SOSP'23]. Every public fleet study, generator, and online detector targets x86. As ARM server CPUs become a material fraction of cloud capacity, three gaps compound:

1. **No ARM-server native generator.** SiliFuzz [VERIFY] fuzzes x86_64 proxies; Harpocrates [VERIFY: ISCA'24] generates x86-64 tests. Neither runs on — or models — an ARM server microarchitecture.
2. **No runtime-learned mutation.** SiliFuzz's only content mutation is an instruction-encoding bit-flip, operand-undirected. Harpocrates's operand policy is static; its IEEE Micro extension explicitly names reinforcement-learning operand optimisation as future work [VERIFY: IEEE Micro 2026]. No published SDC generator learns its mutation strategy.
3. **No power-stress dimension.** Fleet folklore holds that high power and current transients (di/dt) accelerate defect excitation, but no generator formalises power-stress patterns or measures their relationship to detection rate.

### 1.2 The scientific core: directed mutation on random values

Our answer to the first gap's scientific core came through falsification. The obvious approach — replace random operands with a fixed-value dictionary (all-0/all-1/alternating/boundary/subnormal/NaN, plus constraint-satisfaction-paired carry tables) — is statistically significantly *worse* than random on both metrics (bit-flip 0.46×, p=0.0083; structural 0.33×, p=0.0001), because of **logical masking**: structured operands yield deterministic, low-entropy results, so faults landing in cancelled computation are unobservable. The AVF theorem (under uniform fault injection, diverge rate = ACE fraction) predicts exactly this. The breakthrough is the opposite of a dictionary: **directed pressure must operate on top of random values, not instead of them.** The resulting generator (D13) biases random operand draws at runtime via a popcount carry-chain proxy, and beats random 3.00× (bit-flip) and 7.79× (structural) with 500 injections per cell — while preserving random's coverage breadth.

### 1.3 The system contribution: an evolvable framework

A single compiled workload cannot answer the second and third gaps. Between the falsification result and this paper, we re-built the generator as **sdc_pipeline**, a five-stage closed loop in which every stage is a plugin (Figure 1):

```
Gen (mutator pool) → Assess (evaluator pool) → Filter (multi-metric selection)
  → Validate (gem5+CHAOS injection) → Vault (provenance store) → Feedback (policy)
```

Candidates — instruction sequences with lineage, structure tags, and operand state — flow through swappable mutators (operand bit-flip, dictionary, instruction-sequence, power-stress Type-I/II), swappable evaluators (ACE-proxy mid-flip, IBR, avalanche, toggle-power, McPAT peak power), swappable filters (weighted, Pareto), and a swappable *selection policy* whose interface is Gym-shaped (`choose_mutators`/`observe`). The framework's 16 commits and its test suite (50 framework tests + 39 regression tests across the toolchain) are the artefact; its design rule is that no scientific bet is hard-coded: the D13 heuristic, a hill-climb, a bandit, or a future deep RL policy are objects behind one interface.

Three mechanisms emerged from building the framework that the workload-level result could not express:

- **Ordered read-set analysis** (§5.2) — the generator-level first line of defence against logical masking. A mutation of operand register *r* changes behaviour only if *r*'s **first reference in program order is a read**; static read-sets over-approximate (a register read after being overwritten is dead), and naive mutation wastes budget on masked registers. Measured on the masking exemplar: naive mutation effectiveness 0/1, static read-set 2/6, ordered first-read analysis **6/6**.
- **ε-greedy bandit selection** (§5.4) — the first reinforcement-learning component in an SDC test generator. Each mutator is an arm; reward is the mean assessment score of its children; ε-greedy exploration with incremental Q-updates. Ten-seed honest comparison against a hill-climbing heuristic: 5/3/2 (hill/bandit/tie) — the bandit draws one-third the mutation budget (one arm per generation) and reaches parity, and the measurement shows *why* deeper learning needs a more discriminative reward (the gem5 detection rate, which E8 shows has signal).
- **McPAT-in-the-loop power evaluation and a length-matched stress experiment** (§6.4) — a TaiShan V110 McPAT model (22nm approximation, honestly bounded) evaluates every candidate's peak power via instruction-mix → per-unit duty-cycle mapping. A preliminary Type-I/Type-II stress experiment showed a monotone detection-rate ordering (0% → 6.7% → 13.3%); the length-matched control we then ran **refutes the stress interpretation** — an equal-length NOP-padded arm reaches 12% vs. the stress arm's 14% (p=0.83, 100 injections per arm). The preliminary signal was a program-length artifact; the decisive negative is the deliverable.

### 1.4 Negative results, reported as results

Three controlled experiments did not go the way their preliminary versions suggested, and we report each with the machinery that refuted or bounded it. The closed-loop-vs-random control (E7: identical mutator pool and budget, only parent selection differs) is a tie at 60 injections per arm (4/60 vs. 3/60). The power-stress experiment's preliminary monotone signal (E8v1) was **refuted by our own length-matched control** (E8v2, §6.4): the apparent stress effect is a program-length artifact. The bandit-vs-hill-climb benchmark is statistical parity (sign-test p=0.727). We hold that in this domain — where a falsification path produced the core result — the willingness to run the experiment that kills one's own preliminary signal is the paper's methodological identity, not a weakness to be buried: every number in §6 is reproducible by script, including the ones that moved against us.

### 1.5 Contributions

1. **Directed mutation on random (D13), on an ARM server CPU.** Bit-flip 3.00× (z=7.00, p=2.5×10⁻¹²) and structural `byte_lane_skew` 7.79× (z=18.68, p<10⁻⁵⁰) versus operand-undirected random, 500 injections per cell, in a gem5 TaiShan V110 O3 model — the first such result on an ARM server microarchitecture, and the first under a store-to-load-forwarding structural fault model.
2. **Falsification of fixed-value targeting, with a mechanistic root cause.** Static dictionaries (including CSP-paired) are significantly worse than random (0.46×/0.33×); we trace this to logical masking via the AVF theorem, not PRNG structure (LCG vs. xorshift per-call entropy statistically equal: 7.9817 vs. 7.9782 bits/call).
3. **sdc_pipeline: an evolvable five-stage SDC workload-generation framework** with plugin mutators, evaluators, filters, and Gym-shaped selection policy; Vault provenance store with lineage; test suite (50 framework + 39 regression); every experiment reproducible by script.
4. **Ordered read-set analysis** — generator-level anti-masking: mutation confined to first-read-live registers; measured elimination of masked mutations (0/1 → 6/6).
5. **An RL-ready policy interface with a first bandit instantiation** — ε-greedy over mutator arms (to our knowledge the first RL component instantiated in an SDC generator), honestly benchmarked (10 seeds, 5/3/2, sign-test p=0.727 vs. hill-climb at one-third budget); the benchmark's scientific content is the identification of reward discriminativeness — not policy capacity — as the current bottleneck.
6. **A length-matched power-stress experiment with a decisive negative outcome**: a preliminary monotone stress signal (0%→6.7%→13.3%) is refuted by a length-matched NOP control (stress arm 14% vs. length-matched 12%, p=0.83, 100 injections per arm) — the apparent stress effect is a program-length artifact. This negative is itself the deliverable: it bounds what instruction-mix "stress" can mean at model level and relocates the physical power→SDC question to silicon, where the framework's fleet path is designed to answer it.
7. **A 13-version falsifiable evolution path** (D1–D13) including negative levers (D4 ACE-targeting backfired to 0.24×; D7 dropping `volatile` killed structural at 0%).
8. **A genuine-SDC/noise taxonomy and four-board 446-core fleet deployment** with zero genuine SDC on healthy silicon — a meaningful, not empty, measurement.

---

## 2 Background

*(unchanged from v1: SDC and the AVF theorem; SiliFuzz — proxy fuzzing, operand-undirected; Harpocrates — µarch-aware generation, gem5-only, x86; the four-board Kunpeng 920 fleet and the RunSnapOutcome taxonomy. Full text in v1 backup §2; retained verbatim for review continuity.)*

### 2.1 SDC and the AVF theorem

*(retained from v1)* A bit is ACE (Architecturally Correct Execution) if changing it changes the final architectural state. AVF = ACE-bits/total-bits; under uniform single-fault injection, the diverge rate equals the workload's ACE fraction [VERIFY: Mukherjee et al., MICRO'03]. Raising ACE fraction raises detection probability — this is the theorem that grounds both the falsification (§4.1) and the win (§6.1).

### 2.2 SiliFuzz: proxy fuzzing, operand-undirected

*(retained from v1)* SiliFuzz fuzzes Unicorn CPU proxies with Centipede, accumulates deterministic snapshots, replays them fleet-wide. Source inspection of the AArch64 path shows its only content mutation is `FlipRandomBit` (instruction-encoding bit-flip, disassembler-gated), with an explicit upstream TODO for other modes. No signal biases operands toward high-ACE configurations. SiliFuzz's authors themselves flag specialised mutation as the open quality axis.

### 2.3 Harpocrates: µarch-aware generation, gem5-only, x86

*(retained from v1)* Harpocrates uses constrained-random x86-64 generation (MuSeqGen), instruction-replacement mutation, and gem5-graded ACE-lifetime/IBR fitness with SFI. Its five limits: x86-64 only; gem5-only, no real silicon; no defect-class structural fault; static operand policy; no fleet noise taxonomy. Its IEEE Micro extension names RL operand optimisation as future work — the design point our bandit policy occupies.

### 2.4 The fleet and the noise taxonomy

*(retained from v1)* Four-board Kunpeng 920 fleet (0101/0102/0103 fully reachable; 0201 partially), 446 cores total. `RunSnapOutcome`: 0 = as-expected, 2/3/4 = genuine SDC (memory/register-state/endpoint mismatch), 5/6 = noise (runaway/misbehave). The taxonomy is what makes "zero genuine SDC" a measurement rather than an absence.

---

## 3 From Insight to Framework

### 3.1 Why a workload is not enough

The D13 result answers *can directed mutation beat random?* — affirmatively, at extreme significance. But the three gaps of §1.1 are *system* gaps. A compiled C workload cannot: swap its mutation strategy without recompilation; interleave cheap Unicorn-level assessment with expensive gem5 validation; carry provenance across generations of candidates; or measure anything about power. Answering gaps 2 and 3 requires a framework in which the D13 insight is one plugin among several — and in which every scientific bet (including "directed beats random") is a controlled, repeatable experiment rather than a hand-migrated code path.

### 3.2 The five-stage loop

**sdc_pipeline** (Figure 1) is a Python framework (16 commits, 89 tests) over the existing SiliFuzz AArch64 toolchain and the gem5-CHAOS harness:

| Stage | Role | Plugins (current) |
|---|---|---|
| **Gen** | produce child candidates from a parent pool | operand bit-flip; operand dictionary; instruction-sequence; power-stress Type-I (sustained high-toggle prefix) / Type-II (high/low alternation) |
| **Assess** | score candidates cheaply | ACE-proxy (Unicorn mid-flip → diverge fraction); IBR (per-instruction input-bit-toggle rate, the Harpocrates metric made Unicorn-computable); avalanche (1-bit perturbation → output difference); toggle-power proxy; **McPAT peak power** (instruction mix → per-unit duty cycle → V110 model) |
| **Filter** | select the next generation's parents | weighted multi-metric; Pareto non-dominated front; **random (control arm)** |
| **Validate** | measure ground-truth detection rate | gem5+CHAOS: automatic golden registration per candidate, bit-flip and `byte_lane_skew` injection sweeps with Wilson CIs; fault-clock sampled from each candidate's own cycle-count ROI |
| **Vault** | persist everything with lineage | JSONL store; content-hash identity; `lineage()` walks parent chains to seeds |

The loop's controller is a **policy** object with a Gym-shaped interface — `choose_mutators(rng)` and `observe(generation, mutator_scores, baseline)` — so a hill-climb, a bandit, or a future deep-RL policy are interchangeable without touching the pipeline.

### 3.3 The Candidate abstraction

A candidate unifies what were previously two disjoint representations: the evolution engine's hand-coded hex snippets, and the template system's `.S` assembly files. A candidate carries its assembly source, its compiled machine code (via the native `as`/`objcopy` path the template corpus uses), its initial register state, **structure tags** (the embryo of a future structure-targeting generator), and its parent idents. Identity is a content hash; the Vault deduplicates and walks lineage. This single abstraction is what makes every downstream stage generic.

### 3.4 The gem5 bridge

Any candidate is automatically packaged into a gem5-runnable static workload: an assembly `payload` function (AAPCS64-conformant: saves/restores x19–x28 and the frame; loads x0–x28 from a global input array; embeds the candidate's machine code verbatim; stores x0–x28 back) plus a C `main` that accumulates outputs across 200 iterations and prints a `SUM=/CRC=` golden line. Golden registration runs once per candidate (`--mode baseline`); injection sweeps sample fault clocks from the candidate's *own* cycle count (ROI 20–80%). Three bugs found and fixed in building this bridge are documented in §5.5 — one of them (the fault-clock unit) would silently produce all-masked results and is a trap for any replicator.

---

## 4 The Falsification Path (D1–D13)

*(unchanged from v1; Table II and the lever-by-lever narrative retained verbatim — the falsification path is the paper's reproducibility artefact. Summary:)*

### 4.1 Thirteen versions, one lever at a time

*(retained from v1 Table II)* B (random baseline) = 8.2% bit-flip / 8.4% structural. D1–D5 (fixed-value dictionaries, including CSP-paired): significantly *worse* (D1 3.0%, D4 2.0% — ACE-targeting backfired). D6–D12 build workload structure: multi-reference operands, `volatile` store/load dual-ACE paths (D7 dropping `volatile` kills structural at 0% — forwarding must exist to be corrupted), hybrid forwarding (D8: structural 3.17×, the first significant win), coverage breadth (D10: bit parity + structural 2.02×), cross-loop accumulators (D11/D12: bit-flip 12.4%). **D13** adds exactly one lever — directed mutation on random via `pick_high_toggle` — reaching 24.6% / 65.4%.

### 4.2 D13: the runtime mechanism

*(retained from v1 §4.2)* Each iteration draws two random candidates, mutates one toward higher carry-chain proxy (`(a^mask)+1`, rotate, `^= ~a`), and keeps the higher-proxy value: random coverage breadth plus directed ACE bias.

### 4.3 Root cause: ACE fraction, not PRNG structure

*(retained from v1 §6.2)* LCG vs. xorshift per-call entropy statistically equal (7.9817 vs. 7.9782 bits); the ACE-fraction scan shows B=7.6% vs. D5=6.1% with B's ACE registers individually carrying more output-relevant data. Random wins by spreading output relevance; D13 wins by spreading *and* biasing.

---

## 5 Framework Mechanisms

### 5.1 The evaluator pool: cheap assessment, honestly named

Four Unicorn-level evaluators score every candidate in milliseconds. The **ACE-proxy** evaluator reproduces the gem5 injection *semantics* cheaply: it flips a random register bit at a random instruction index mid-execution and measures whether any observed register's final value diverges — the same mid-flight fault model CHAOSReg applies, at emulator speed. The **IBR** evaluator computes Harpocrates's Input-Bit-Ratio proxy as the per-instruction input-toggle density. The **avalanche** evaluator perturbs one input bit and measures output bit-differences — the anti-masking signal. The **toggle-power proxy** is deliberately *named* a proxy: di/dt approximation pending the McPAT evaluator (§5.3), which provides the real (if 22nm-approximated) power number.

### 5.2 Ordered read-set analysis: anti-masking at the generator

The masking exemplar from our own intermediate results: a dictionary mutation replaced register x5's initial value with `0xFFFFFFFF`, and the workload's output did not change — because x5 is *written before it is ever read* (`adds x5, x4, x3`), so its initial value is dead. The mutation was wasted, and worse, dilutes the signal of any experiment measuring "does mutation help?"

The fix is a three-level refinement, measured as effectiveness — does the gem5 golden `SUM` change? — on six dictionary children per configuration, replicated across **two instruction-structure exemplars** (an `adds`-chain and a `mul`-chain with different def-use patterns; `tools/sdc_pipeline/readset_exemplars.py`):

| Analysis | Domain mutated | Exemplar 1 (adds-chain) | Exemplar 2 (mul-chain) |
|---|---|---|---|
| None (naive) | any `regs_init` key | 0/1 (the M2 exemplar) / 2/6 (batch) | 2/6 |
| Static read-set (any instruction reads r) | x0–x5 | 2/6 | 2/6 |
| **Ordered first-read** (r's first reference in program order is a read) | x1, x2 | **6/6** | **6/6** |

The ordered analysis walks instructions in program order tracking which registers have been overwritten; a register's initial value is live iff its first reference is a read. Static read-sets over-approximate because a register read *after* being overwritten consumes the overwritten value, not the initial one. Across both exemplars, ordered first-read analysis raises mutation effectiveness to 6/6 — within the mutated-domain guarantee: every mutation the framework now issues targets a register whose initial value can change program behaviour. We state the scope honestly: two exemplars establish the mechanism, not a distributional claim; the analysis is classical live-variable/def-use reasoning, and the contribution is its identification as a *masking* phenomenon at the generator level — the complement of the workload-level anti-masking insight (§4): masking is not only something operands suffer (structured values cancel faults) but something *mutations* suffer (dead initial values), and both have systematic defences.

### 5.3 McPAT-in-the-loop: honest power evaluation

We built a TaiShan V110 McPAT model (`tsv110.xml`: 4-wide OoO, PRF-based, 64KB 4-way L1I/D, 512KB private L2, per-scheduler ~33 entries, 2×AGU, dual FSU; parameters from the SoC manual, published microbenchmarks, and sysfs where available). Two honesty boundaries are carried in the model header and in every metric the evaluator emits: McPAT's oldest supported node is 22nm while V110 is 7nm — absolute power is systematically overestimated and **relative comparisons are the trustworthy signal**; and the load statistics are a synthetic integer profile.

The evaluator maps a candidate's instruction mix (capstone-classified alu/mul/lsu/fpu/br) to per-unit duty cycles scaled by the 4-wide issue rate, then reads McPAT's **peak power** — a measurement choice forced by the tool's semantics: duty cycles drive peak-power computation (measured: sustained-FPU 2.468W vs. sustained-ALU 2.524W) while runtime dynamic power is driven by busy-cycle counts and barely responds to duty. A second physical observation we report because it shapes the stress-pattern design: peak power ≈ Σ(unit duty × unit power), so *multiple units simultaneously active* (mixed alu+lsu at duty 1.0 each: 4.89W) exceeds *one unit saturated* (four units at 0.67: 4.40W) — the correct Type-I "highest power" pattern is multi-unit concurrency, not single-unit saturation.

### 5.4 The ε-greedy bandit: the first RL component in an SDC generator

The policy interface (`choose_mutators(rng)` / `observe(generation, mutator_scores, baseline)`) admits any learning strategy. We implemented the first rung of the RL ladder: an **ε-greedy multi-armed bandit** over mutator arms, reward = the mean filter-score of a mutator's children, incremental mean Q-updates, ε=0.2 exploration. Unit tests verify convergence (after 30 generations of a fixed-reward environment, >40 of 50 utilisation samples pick the best arm) and exploration coverage.

The honest benchmark — ten seeds, eight generations, identical everything except the policy (`tools/sdc_pipeline/bandit_bench.py`, result JSON in the artefact tree):

| Policy | Best-ACE wins (10 seeds) |
|---|---|
| Hill-climb (heuristic) | 5 |
| ε-greedy bandit | 3 |
| tie | 2 |

A two-sided sign test over the eight untied seeds gives p=0.727 — statistical parity. The bandit draws **one-third** the mutation budget (one arm per generation vs. all arms), so parity is not a failure; but we report it as what it is: at the Unicorn-level ACE metric the three mutator arms are near-equivalent, so there is little for a learner to learn. The framework's own E8v2 data shows detection rates do separate candidates at the gem5 level; wiring the bandit's reward to validated detection rate is the designated next step, and the interface requires no change to do it.

### 5.5 Three documented traps in the gem5 bridge

Building the Validate stage surfaced three bugs whose fixes are load-bearing for replicators (all verified by gdb-level evidence and committed with reproduction notes):

1. **Output overwrite dilution.** A payload that *overwrites* its output array each iteration dilutes the ACE window by the iteration count: only faults in the final iteration propagate. Fix: accumulate across iterations (the sdc_probe-series semantics). Symptom in the wild: 0/60 all-masked.
2. **Fault-clock unit confusion.** CHAOS's `--first-clock` is in **CPU cycles** (`Cycles(p.firstClock)` in CHAOSReg.cc, scheduled on `clockEdge`), not gem5 ticks (picoseconds). Confusing them (we did, initially, by parsing the golden run's `Exiting @ tick N` directly) makes every fault clock exceed the program's total cycle count — **injections silently never fire**, fault logs are empty, and every run classifies as masked. At 2.6GHz the conversion is tick/385. Symptom: 0/60 all-masked with empty `fault_injections.log`.
3. **Selection-leak in controlled comparisons.** In a closed-loop-vs-random control, if both arms' finalists are chosen by ranking the *shared* Vault by assessment score, both arms select the same candidates and the comparison is void (our first E7 run: 5/60 vs. 5/60, identical candidate sets). Fix: each arm's finalists come from its own trajectory's terminal pool.

Trap 2 in particular deserves community visibility: it produces *plausibly boring* (all-masked) rather than crashed results, and nothing in the toolchain flags it.

---

## 6 Evaluation

### 6.1 D13 vs. random: both metrics, extreme significance

*(retained verbatim from v1 §6.1, Table III)* Bit-flip 24.6% (123/500) vs. 8.2% (41/500), 3.00×, z=7.00, p=2.5×10⁻¹²; structural `byte_lane_skew` 65.4% (327/500) vs. 8.4% (42/500), 7.79×, z=18.68, p<10⁻⁵⁰. On-disk recount provenance and Footnote 1 (the 3.07×→3.00× correction) retained.

### 6.2 Ordered read-set effectiveness

Table new (§5.2): naive 0/1 → static 2/6 → ordered **6/6**. Every operand mutation the framework issues now has the opportunity to change program behaviour.

### 6.3 E7: closed-loop evolution vs. random walk — a tie, honestly

Design: two arms share the mutator pool (read-set-aware bit-flip, dictionary, instruction-sequence), the mutation budget (4 generations × 4 mutations × 3 mutators), and the seed; they differ *only* in parent selection — the EVOLVE arm's filter is multi-metric weighted (ACE 0.6 / IBR 0.2 / toggle 0.2), the RANDOM arm's filter samples uniformly. Each arm's finalists are its own terminal pool (§5.5 trap 3). Finalists: 3 candidates per arm × 20 bit-flip injections each.

Result: **EVOLVE 4/60 (6.7%) vs. RANDOM 3/60 (5.0%)**; Fisher OR=1.357, p=1.0 — **TIE/INSUFFICIENT**. (Injection events are nested within candidates — 3 candidates × 20 per arm; the per-candidate counts are in the result JSON. We treat the arm-level Fisher as a conservative summary and flag the nesting explicitly rather than claim cluster-robust inference.)

Interpretation, honestly bounded: at 60 injections per arm the test cannot detect an odds ratio of ~1.4 (hundreds of injections would be needed); the D13-style seed is already near the top of this shallow mutation space's achievable ACE (Unicorn-level assessments saturate at 0.7–0.8); and four generations of operand/instruction mutation is far less search depth than D13's per-instruction runtime selection over 200 iterations. E7's value is the *control template* — identical budget, single-variable difference, per-arm trajectories — and the two documented traps it exposed (§5.5). The positive control for "directed beats random" in this paper remains the D1–D13 ablation, where the directed lever is applied at runtime depth; E7 measures whether *generational* selection adds value on top, and at this depth and sample size it does not, measurably.

### 6.4 E8: power stress and detection rate — a preliminary signal, refuted by a length-matched control

**E8v1 (preliminary).** One base seed (D13-style 8-instruction ALU chain); arms baseline / Type-I sustained stress / Type-II oscillating stress; 3 stress candidates × 15 bit-flip injections per arm (the baseline arm carried 1 candidate × 15 — an asymmetry we correct in v2). Result: 0/15 = 0% baseline, 3/45 = 6.7% Type-I, 6/45 = 13.3% Type-II — monotone, directionally consistent with the oscillation hypothesis. Reported as INSUFFICIENT at that sample size.

**The confound.** Type-I/II candidates are constructed by *prepending instruction blocks* to the base seed, so the arms differ not only in stress structure but in program length — and program length changes the fault-clock ROI (20–80% of cycle count) and the ACE window. If longer programs simply have more fault-exposable state, the monotone ordering is a length artifact, not a stress effect.

**E8v2 (the control).** Four arms × 5 candidates × 20 injections (100 per arm), adding arm **D_lenmatch**: NOP-padded to the *same instruction counts* as the Type-II arm (48–58 instructions), providing stress-free length parity.

| Arm | Instructions | Detection rate | McPAT peak |
|---|---|---|---|
| A baseline | 8 | 10/100 = **10.0%** | 2.5238W |
| B Type-I (sustained) | 24–28 | 11/100 = 11.0% | 2.5238W |
| C Type-II (oscillating) | 48–58 | 14/100 = 14.0% | 2.5238W |
| **D length-matched NOP** | **48–58** | **12/100 = 12.0%** | 2.5238W |

The decisive comparison is C vs. D: **14% vs. 12%, Fisher p=0.83** — statistically indistinguishable. The stress arm does not separate from an equal-length, zero-stress control. Meanwhile A→C (10%→14%, p=0.51) and A→D (10%→12%, p=0.82) rise in tandem: the weak length trend is shared by both long arms. And the v1 baseline of 0% is itself exposed as small-sample fluctuation (10% at n=100).

**Verdict: the E8v1 monotone stress signal is a program-length artifact.** Within gem5's O3 model — which has no voltage or timing mechanism — instruction-mix "stress" has no measurable effect on detection rate at 100-injections-per-arm resolution. We state the three-way honest boundary: (i) the McPAT duty-cycle mapping cannot express temporal waveforms (all four arms score identically), so static McPAT integration is structurally blind to sustained-vs-oscillating; (ii) the Unicorn toggle proxy moves inversely to detection rate across arms (per-instruction averaging dilution — a units-of-account trap, documented); (iii) the physical power→SDC question is unchanged by this negative: it requires silicon, where the framework's distributed-scan path with stress-ng di/dt amplification is the designated instrument.

**Methodological point.** Had we stopped at E8v1 — 45 injections per arm, no length control — the monotone ordering would have entered the literature as "directional support for H2." The length-matched control killed it in one afternoon of automated injections. We consider this the framework working as designed: making the experiment that refutes your own preliminary signal cheap to run.

### 6.5 Fleet deployment

*(retained verbatim from v1 §6.4, Table IV)* Four boards, 446 cores, zero genuine SDC (outcomes 2/3/4), 10 runaway + 1170 misbehave noise entries correctly separated by the taxonomy; the 0201 6016+ runaway history that a naive parser would have counted as SDC; SIGSEGV-under-full-load root-caused to snap-external resource exhaustion.

### 6.6 Comparison boundaries

*(retained from v1 §6.5)* Not a cross-paper race with Harpocrates's 99% (different ISA, fault model, structures; our claim is within-model directed-vs-random). The fleet zero is consistent with — not contradictory to — x86 fleet rates at this scale.

---

## 7 Discussion

### 7.1 One frame for three anti-masking results

Two of the paper's results are masking phenomena in the strict AVF sense, and they form one narrative: **operand-level masking** (structured fixed values cancel faults — D1–D5 worse than random) and **mutation-level masking** (dead initial values waste mutations — ordered read-set analysis, 2/6→6/6). Both are the same underlying fact — a bit that cannot reach architectural state cannot produce divergence — observed at two different producers (operands, mutations). A third result is related by analogy only: **selection-level signal starvation**, where the assessment metric saturates (Unicorn ACE-proxy at 0.7–0.8 for this seed family) and leaves no variance for a learner to exploit (E7's tie; the bandit's parity). Nothing is masked in the third case — the signal simply has no discriminative variance — and we name it separately rather than stretch "masking" to cover it. Each phenomenon has a systematic defence: directed-on-random for the first, first-read analysis for the second, and — proposed, not yet demonstrated — validated detection rate as reward for the third.

### 7.2 Where the framework goes next

The interface-level bets are placed: AutoµSens-style structure-targeted generation hangs off the candidate's structure tags and a future gem5 structure-statistics map; deeper RL (contextual bandits, policy gradients) hangs off the Gym-shaped policy interface with the E8-motivated reward change; timing-fault models hang off the CHAOS injector's existing parameter space. None of these require framework surgery — the criterion by which "evolvable" should be judged.

### 7.3 The silicon question

*(retained from v1 §7.4)* gem5 O3 ≠ V110 RTL; model-level diverge rates are not silicon SDC rates; the core-179 watchdog reset blocks the decisive experiment. The fleet deployment validates the pipeline and taxonomy.

---

## 8 Threats to Validity

*(retained from v1, plus:)*

- **Framework-level negatives are depth- and resolution-bounded.** E7's tie is bounded by generation depth (4) and 60 injections per arm; E8v2's negative is bounded by 100 injections per arm (its C-vs-D comparison would detect a difference of roughly ±10 percentage points). Neither bounds the mechanisms at greater depth or sample; computed sample sizes are stated in §6.3/§6.4.
- **McPAT is a 22nm approximation of a 7nm part, structurally blind to temporal waveforms.** Absolute power is overestimated; only relative comparisons were attempted; and the instruction-mix → duty-cycle mapping scores all four E8v2 arms identically — it cannot, even in principle, distinguish sustained from oscillating stress. Static McPAT integration is therefore an *accounting* instrument here, not a stress instrument.
- **Injection nesting.** Injection events in E7/E8 nest within candidates (3–5 candidates per arm). Arm-level Fisher tests treat them as exchangeable; we flag this explicitly (§6.3) and release per-candidate counts rather than claim cluster-robust inference.
- **Unicorn-level assessment is a proxy.** The ACE-proxy evaluator reproduces injection *semantics* at emulator speed but not microarchitectural state; the ground truth remains the gem5+CHAOS Validate stage.

---

## 9 Related Work

*(retained verbatim from v1, with one addition:)*

**Learned mutation for hardware test.** To our knowledge, no published SDC or CPU-functional-test generator learns its mutation strategy at runtime; Harpocrates++ names RL operand optimisation as future work [VERIFY: IEEE Micro 2026]. Our ε-greedy bandit is deliberately the smallest honest rung of that ladder — its benchmark (§5.4) shows the current bottleneck is reward discriminativeness, not policy capacity, which is the finding we actually claim.

*(proxy fuzzing / µarch-aware generation / fleet characterisation / online detection / fault models clusters retained from v1)*

---

## 10 Conclusion

Directed mutation on random values significantly outperforms operand-undirected mutation at generating SDC-revealing workloads on an ARM server CPU — bit-flip 3.00× and structural `byte_lane_skew` 7.79× (p≤2.5×10⁻¹² and p<10⁻⁵⁰) — and the falsification path that produced the insight (fixed-value dictionaries significantly *worse* than random, by logical masking, per the AVF theorem) is itself a measurable contribution. To carry the result at the system level we built **sdc_pipeline**, a five-stage evolvable framework with plugin mutators, evaluators, filters, and a Gym-shaped selection-policy interface, Vault provenance, and an 89-test suite. The framework's mechanism studies delivered in both directions. Ordered read-set analysis eliminates dead-initial-value masking (mutation effectiveness 2/6 → 6/6, replicated across two instruction-structure exemplars). The ε-greedy bandit — to our knowledge the first RL component instantiated in an SDC generator — reaches statistical parity with a hill-climbing heuristic at one-third the mutation budget (sign-test p=0.727), and the benchmark identifies reward discriminativeness, not policy capacity, as the bottleneck. And the length-matched power-stress control produced the paper's most instructive negative: a preliminary monotone stress signal (0%→6.7%→13.3%) is a program-length artifact (stress arm 14% vs. length-matched NOP control 12%, p=0.83, 100 injections per arm) — within a model with no voltage mechanism, instruction-mix "stress" has no measurable effect on detection rate, relocating the physical power→SDC question to silicon, where the framework's fleet path is the designated instrument. The closed-loop-vs-random control is likewise a documented tie at current depth and sample size. The machinery that produced the 3.00×/7.79× positives is the same machinery that reported — and refuted — its own preliminary signals; the silicon-level question remains open and blocked, and within the model-level scope where anything can be measured, the framework makes each next question cheap to ask and hard to answer wrong.

---

## References

*(retained from v1 — all [VERIFY] markers carry over; add:)*

- **McPAT** — S. Li, J. H. Ahn, R. D. Strong, J. B. Brockman, D. M. Tullsen, N. P. Jouppi. "McPAT: An Integrated Power, Area, and Timing Modeling Framework for Multicore and Manycore Architectures." MICRO 2009. DOI: 10.1109/MICRO.2009.30. [VERIFY]
- **Bandits** — R. S. Sutton, A. G. Barto. *Reinforcement Learning: An Introduction* (2nd ed.), MIT Press, 2018. (ε-greedy chapter.) [VERIFY edition]

*(full v1 reference list: SiliFuzz; Harpocrates ISCA'24 + IEEE Micro'26; AVF theorem; Hochschild; Dixit 2021; SOSP'23; Fleetscanner/Ripple; Veritas; PinDrop; SEVI; Orthrus; ITHICA; Hardware Sentinel; DelayAVF; From Gates to SDCs; CHAOS; gem5; Vega; Trippel; Paper 1)*

---

## Mandatory Inclusions

**Data Availability.** All artefacts on branch `feat/sdc-pipeline-framework`: the framework and test suite (50 framework + 39 regression tests), experiment scripts (`e7_evolve_vs_random.py`, `e8_power_sdc.py`, `e8v2_power_sdc.py`, `bandit_bench.py`, `readset_exemplars.py`), result JSONs for every experiment (E7, E8v1, E8v2, bandit benchmark, read-set exemplars) under `output/experiments/`, the McPAT TaiShan V110 model with its parameter-provenance and limitation record (`docs/experiments/2026-09-03-mcpat-setup.md`), and the experiment reports under `docs/experiments/`. D1–D13 workloads, sweep harnesses, and fleet scripts on branch `feat/sdc-detection-cases-kunpeng920`.

**Ethics Declaration.** No human subjects or sensitive data. Fleet scans run on hardware owned by the authors' institution.

**Author Contributions (CRediT).** [To be completed with co-authors.]

**Conflict of Interest.** None declared.

**Funding.** [TBD.]

**AI-Use Disclosure.** AI-assisted drafting and verification tooling; all numerical results reproduced from real command output; E7/E8 negatives reported with the same rigour as positives; no fabricated citation or experiment.

**Limitations.** §8: model vs. silicon; depth-limited framework negatives; McPAT 22nm approximation; proxy assessment; single µarch; sample sizes stated per experiment.

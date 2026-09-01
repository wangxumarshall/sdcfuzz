# Data Availability Statement

All artefacts supporting the claims in this paper are available on the `feat/sdc-detection-cases-kunpeng920` branch of this repository.

## Source artefacts (in-repo, version-controlled)

| Artefact | Path | Role |
|---|---|---|
| Evaluated workloads D1–D13 | `seeds/gem5/sdc_probe_workload_d{1..13}.c` | The 13 ablation workloads (§4.1, Table II) |
| Random baseline B | `seeds/gem5/sdc_probe_workload_random.c` | SiliFuzz-style operand-undirected baseline (§2.2) |
| Falsified dictionary workloads | `seeds/gem5/sdc_probe_workload.c`, `_csp.c`, `_evolved.c` | D1–D5 naive / CSP-paired / evolved static (§3.1, Table I) |
| 500-injection sweep harnesses | `scripts/d{1..13}_sweep.py`, `scripts/gem5_sweep_ab_random.py`, `scripts/gem5_sweep_structural_abc.py` | Fault-injection drivers (§4.2) |
| ACE-fraction scanner | `scripts/gem5_ace_scanner.py` | Root-cause verification (§4.4, §6.2) |
| Offline evolution engine | `tools/sdc_mutator/evolution_engine.py` | Proof-of-mechanism (§4.3) |
| Fleet scan + noise parser | `scripts/distributed_scan.py`, `scripts/collect_results.py`, `scripts/ssh_lib.py` | 4-board deployment (§4.5, §6.4) |
| Structural fault patch | `scripts/patch_gem5fi_lsq_fwd.py` | CHAOSLSQFwd `byte_lane_skew` extension (§2.4) |
| 19 microarchitectural templates | `seeds/*.S` (MMU/L2C/LSU/OoO/IEX/FSU/IFU) | Structural coverage breadth (§4.5) |
| SiliFuzz toolchain (reused) | `proto/`, `snap/`, `runner/`, `orchestrator/`, `fuzzer/`, `proxies/` | Snapshot/Snap/runner/orchestrator/mutator/proxy substrate (§5.1) |

## On-disk recount sources (board 0101, not in-repo)

The on-disk `run_NNN/simout.txt` files from which every diverge count was re-counted during manuscript preparation reside on board 0101 at `/root/gem5-fi/smoke_test/` (the gem5-CHAOS work tree). These are the authoritative sources for:
- D13 bit-flip 123/500, D13 structural 327/500, B bit-flip 41/500, B structural 42/500 (Table III, §6.1, Footnote 1).
- The D1–D13 evolution-path counts (Table II, §4.1).
- The ACE-fraction scan (§6.2).

The `output/distributed/results.json` file (in-repo) is the aggregated fleet-scan result parsed by `collect_results.py` for Table IV (§6.4).

## Reproducibility recipe

1. Build the SiliFuzz runner + orchestrator per `README_AArch64_Deployment.md` (AArch64/openEuler porting prerequisites apply).
2. Compile each workload: `gcc -static -O2 -o sdc_probe_workload_d13 seeds/gem5/sdc_probe_workload_d13.c`.
3. On the gem5-CHAOS work tree (board 0101, `~/gem5-fi/`), run baseline then 500 injections: `python3 ~/gem5-fi/smoke_test/gem5_sweep_*.py 500 --seed 7` (§4.2).
4. Parse `run_NNN/simout.txt` with the value-golden rule (Footnote 1): a run is golden iff `SUM` and `CRC` both match golden by value.
5. For the fleet: `python3 scripts/distributed_scan.py --duration <T>` then `python3 scripts/collect_results.py` (§4.5).

## Limitations on reproducibility

- The gem5 TaiShan V110 O3 model (`two_level_taishan.py`) is itself a model, not the Kunpeng RTL (§8); diverge rates are model-level and will not match silicon SDC rates.
- The four-board fleet (0101/0102/0103 reachable; 0201 degraded) is institutional hardware; access is not public. The static binaries, however, are buildable from this repo and deployable on any AArch64 Linux host.
- Silicon-level reproduction on a known-defective core is blocked by the core-179 watchdog reset (§7.4, §8) — this is the central open problem, not a reproducibility gap we can close.

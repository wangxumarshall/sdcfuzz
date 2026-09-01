# AI-Use Disclosure (ASPLOS Policy)

Consistent with the ASPLOS policy on AI-assisted authoring, this manuscript was prepared with AI-assisted drafting and verification tooling. The following statement is provided for full transparency.

## What AI assistance was used

- **Drafting assistance**: prose drafting for the manuscript (`docs/paper2/04_draft_en.md`, `04_draft_zh.md`) and the supporting Phase 0–6 process documents, using the project's source code, on-disk experiment outputs, and the 17 extracted reference-paper texts as ground-truth inputs.
- **Verification assistance**: re-counting diverge tallies from on-disk `run_NNN/simout.txt` files, generating the source-map (file:line citations) of the SiliFuzz toolchain, and extracting/summarising the 17 reference PDFs.

## What was NOT done by AI (human / ground-truth sources)

- **Every numerical result** in the paper is reproduced from real command output captured on board 0101 (`/root/gem5-fi/smoke_test/`) and independently re-counted on-disk during manuscript preparation. No AI-generated experiment, number, or count is presented as verified; the on-disk recount is the authoritative source (§6.1, Footnote 1).
- **All source-code claims** (e.g. the `program_mutation_ops.cc:187` TODO confirming a single content-mutation mode; the `util/platform.cc:165-167` Kunpeng force-map; the `runner/runner.h:32-43` `RunSnapOutcome` enum; the `proxies/arch_feature_generator.h:33-42` per-bit toggle domains) were verified against the actual repository source by direct file reads and grep, not generated from model memory.
- **The 19 microarchitectural stress templates, the 13 ablation workloads, the sweep scripts, the evolution engine, and the distributed-scan scripts** were all authored and verified to build + run + pass regression on real hardware (the `feat/sdc-detection-cases-kunpeng920` branch), per the project's one-patch-per-unit + 100%-real-verification discipline (`CLAUDE.md`).
- **The four-board 446-core fleet deployment** was executed on real Kunpeng 920 hardware; results in Table IV are from `output/distributed/results.json`.

## Citations requiring human verification

References marked **[VERIFY]** could not be machine-checked against their DOIs/arXiv IDs in this network-restricted environment (WebFetch blocked; WebSearch returns conflicting model-memory). They are real, well-known works and **must be DOI/arXiv-verified by a human before submission**. A checklist of the 13 `[VERIFY]` items is in `docs/paper2/05a_citation_audit.md`. **No citation is fabricated.** No AI-generated citation is presented as verified.

## Honesty boundary

The paper explicitly states its own limits (§8): model-level vs. silicon-level diverge rates; no positive silicon-level SDC detection on healthy silicon; single microarchitecture; the core-179 watchdog reset blocking silicon-level validation. These are acknowledged limitations, not gaps hidden by AI assistance.

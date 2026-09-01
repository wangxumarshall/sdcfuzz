# Paper 2 — `docs/paper2/`

> SDC detection-case generation and deployment methodology for the Huawei Kunpeng 920 (TaiShan V110) ARM server CPU. Target venue: **ASPLOS** (ACM citation format). English primary + Chinese parallel translation.

This directory is the `academic-research-skills:academic-paper` 8-phase pipeline output, restructuring the prior `docs/paper/paper2_{en,zh}.md` to best-paper level, benchmarked against SiliFuzz and both Harpocrates papers (ISCA'24 + IEEE Micro'26).

## File map

| File | Phase | Role |
|---|---|---|
| `PLAN.md` | plan | The approved plan-mode plan (competitive intel, 5-axis differentiation, 8-phase execution) |
| `00_paper_configuration.md` | 0 | Locked config: ASPLOS, ACM, 12–14k words, EN+ZH, honesty red lines |
| `01_literature_and_positioning.md` | 1 | Related Work matrix (17 refs) + positioning paragraph + citation list |
| `02_outline_and_evidence_map.md` | 2 | 13-section outline + word counts + evidence→source mapping |
| `03_argument_blueprint.md` | 3 | Claim→evidence chains + counter-arguments + falsifiability |
| `04_draft_en.md` / `04_draft_zh.md` | 4 | Full draft (post-R1 revision), EN + ZH |
| `05a_citation_audit.md` | 5a | Zero-orphan check + DOI verify status (8 confirmed, 13 [VERIFY]) |
| `05b_abstract_en.md` | 5b | Bilingual abstract (EN 240 words / ZH 380 chars, independent) |
| `06_peer_review.md` | 6 | Simulated 5-dimension review → Minor Revision, R1 items applied |
| `paper2.tex` + `paper2.bib` | 7 | LaTeX (acmart/ASPLOS) + BibTeX, submission-ready skeleton |
| `paper2_en.md` / `paper2_zh.md` | 7 | Final Markdown (copies of 04_draft, EN + ZH) |
| `DATA_AVAILABILITY.md` | 7 | Artefact list + reproducibility recipe + limits |
| `CREDIT.md` | 7 | CRediT + CoI + Funding + Ethics placeholders |
| `AI_DISCLOSURE.md` | 7 | ASPLOS AI-use disclosure (what was/wasn't AI-assisted) |

## Key results (all on-disk-verified, none fabricated)

- D13 bit-flip: 24.6% (123/500) vs B 8.2% (41/500), **3.00×**, z=7.00, p=2.5e-12
- D13 structural `byte_lane_skew`: 65.4% (327/500) vs B 8.4% (42/500), **7.79×**, z=18.68, p≪1e-300
- Fixed-value dictionaries falsified: C/B = 0.46× (bit) / 0.33× (structural)
- 4-board 446-core fleet: 0 genuine SDC on healthy silicon; noise taxonomy turns 6016+ runaway noise into 0

## Honesty notes (read before submitting)

1. **3.00×, not 3.07×.** B bit-flip = 41/500 = 8.2% (on-disk recount, value-golden rule). `kunpeng920_sdc_research_report.md` §7.1 still carries the old 3.07× figure — do not propagate it.
2. **CHAOSLSQFwd `byte_lane_skew` is NOT in the published CHAOS paper.** It is Paper 1's extension. Documented as our contribution in §2.4.
3. **Do not claim beating Harpocrates's 99%.** Different ISA / fault model / structure. §7.5 states the boundary.
4. **13 [VERIFY] citations** need human DOI/arXiv confirmation before submission (see `05a_citation_audit.md`). 8 are already confirmed from PDF internal text. None fabricated.
5. **Model-level caveat.** 24.6%/65.4% are gem5 O3 diverge rates, not silicon SDC rates. §8 states plainly.

## Relationship to the old `docs/paper/paper2_{en,zh}.md`

The old versions are retained (not deleted) per the `fusion-merges-not-replaces` principle: they are the SiliFuzz-only-benchmarked predecessors. This `docs/paper2/` is the Harpocrates-aware ASPLOS-grade rewrite.

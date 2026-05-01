# Eval Factsheet — `transversal_modeler/tafi_2025`

> Per playbook § 9 (Eval Factsheets, arXiv:2512.04062). Composes with Datasheets-for-Datasets (Gebru et al., CACM 2021).

## Slice identity

| Field | Value |
|---|---|
| Slice ID | `transversal_modeler/tafi_2025` |
| Slice version | 0.1.0 |
| Slice spec | `spec.md` |
| Construct | "Transversal-modeling correctness" — see `spec.md` § 1 |
| Status | **SCAFFOLD-ONLY** — agent not yet provisioned, zero trials at ship |

## Dataset

| Field | Value |
|---|---|
| Source | Synthesized to match ingestion v2 output schema. Values illustrative only. |
| Items | 1 case × 3 paraphrases. Decision-sized n: 10 paired for A/B regression detection; 25/paraphrase for variance characterization. |
| Item-quality audit | PENDING — fixtures synthetic; user has not signed off as Benevolent Dictator |
| `expected.json` content sha256 | (auto-filled by runner once trials run) |
| Frozen at | 2026-04-30 |
| Refresh policy | Quarterly contamination decay audit |

## SUT (System Under Test)

| Field | Value |
|---|---|
| SUT shape | Managed agent + its mitigation set (per playbook § 9 — Anthropic Sabotage Evals 2024). NOT bare model. |
| Default agent | **NOT YET PROVISIONED.** Will be `agent_<id>` `insignia_transversal_modeler` once created. |
| Agent system_prompt sha256 | (will be filled when provisioned; reference draft at `runs/2026-04-14T21-37-35Z/design/system_prompts/transversal_modeler.md`) |
| Agent model | TBD — likely `claude-sonnet-4-6` to match ingestion |
| Agent temperature | (auto-filled by runner) |
| Foundation commit sha | (auto-filled by runner) |

## Scoring

| Field | Value |
|---|---|
| Scoring tier | Tier-1 programmatic + tier-2 verifiable. No LLM-judge. |
| Score columns | `process` / `outcome` / `environment` reported separately |
| Reporting unit | `<rate> [<lo>, <hi>] (Wilson 95%, n=N)` |
| MDE pre-registered | Δ ≥ 0.20 for headline A/B claims |
| Power | Decision-sized — n=10 paired McNemar detects ≥3 regression at α=0.05 |
| Multiplicity | Bonferroni default; Holm-Bonferroni or BH if k ≥ 4 |
| Paired tests | McNemar's exact for binary; Wilcoxon signed-rank for ordinal |
| Judge model | n/a (no LLM-judge in this slice) |
| New assertion types | `xlsx_sheet_exists`, `xlsx_named_range_exists`, `xlsx_validation_cell` — stubs in `evals/score.py` until `openpyxl` is wired |

## Reproducibility

```bash
# Once the transversal_modeler agent is provisioned:
./evals/runner.py transversal_modeler/tafi_2025 \
  --agent-id <agent_id> \
  --env-id <env_id> \
  --paraphrases v1_canonical \
  --trials-per-paraphrase 1   # smoke; bump to 10 for A/B
```

## Limitations honestly reported

- **Agent not provisioned.** Cannot run live trials. This slice is forward-looking scaffold.
- **`xlsx_*` assertion handlers are stubs.** They raise `NotImplementedError` so a runner that tries to score this slice fails loudly rather than producing a fake pass.
- **Fixtures are synthesized**, not captured from a real ingestion run. Values are illustrative; only structure is asserted upon.
- **No production traces.** Cannot do open + axial coding.
- **No held-out validation case.**
- **No sensitivity-variant cases yet shipped.**

## Anti-pattern compliance audit (per playbook § 8)

| Anti-pattern | Compliant? |
|---|---|
| Likert scoring | ✓ binary only |
| Generic metrics | ✓ all role-specific |
| Premature LLM-judge | ✓ none |
| Single-prompt cell | ✓ ≥3 paraphrases |
| Stub-file masking | ✓ structural xlsx assertions defeat empty workbooks |
| n=1 measurement claims | ✓ slice flagged scaffold-only; no claims at ship |
| Static contamination decay | ✓ SemVer + quarterly audit policy |
| No run manifest | ✓ inherits runner.py manifest emission |
| Process/outcome/env conflation | ✓ column tags in `expected.json` |
| No Bean's-8 worksheet | ✓ `spec.md` |
| Whack-a-mole tweaking | ✓ pre-registered MDE |
| Wald CIs at small n | ✓ Wilson only |
| Multiplicity unhandled | ✓ Bonferroni default |
| Stacked abstractions | ⚠ `expected.json` authored by model, awaits user sign-off; fixtures are synthetic |
| Phenomenon-proxy gap | ⚠ scaffold-only at ship — proxy gap is "does scaffold work for this role" rather than "does the agent work" |

## Pre-registered predictions for next ablation

(none — agent not yet provisioned)

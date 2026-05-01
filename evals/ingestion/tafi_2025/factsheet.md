# Eval Factsheet — `ingestion/tafi_2025`

> Per playbook § 9 (Eval Factsheets, arXiv:2512.04062). Composes with Datasheets-for-Datasets (Gebru et al., CACM 2021). Auto-updated by `runner.sh` on every full run; manually maintained between runs.

## Slice identity

| Field | Value |
|---|---|
| Slice ID | `ingestion/tafi_2025` |
| Slice version | 0.1.0 (semver — bump on any breaking expected.json change) |
| Slice spec | `spec.md` |
| Construct | "Ingestion correctness" — see `spec.md` § 1 |
| Status | EXPLORATORY (single-trial; not a measurement) |

## Dataset

| Field | Value |
|---|---|
| Source | Captured from `runs/2026-04-30T18-40-29Z-poc/smoke/` (production-shaped POC) |
| Items | 1 case × ≥3 paraphrases (target n=25/paraphrase = 75 trials/version) |
| Item-quality audit | PENDING — user has not yet signed off as Benevolent Dictator |
| `expected.json` content sha256 | (auto-filled by runner) |
| Frozen at | 2026-04-30 |
| Refresh policy | Quarterly contamination decay audit per playbook § 8 (Chen EMNLP 2025; Tang ACL 2025) |

## SUT (System Under Test)

| Field | Value |
|---|---|
| SUT shape | Managed agent + its mitigation set (per playbook § 9 — Anthropic Sabotage Evals 2024). NOT bare model. |
| Default agent | `agent_011CaaVZBRsEyuN4hXWMRR4Z` (`insignia_ingestion` v1) |
| Agent system_prompt sha256 | (auto-filled by runner) |
| Agent model | `claude-sonnet-4-6` (recorded per-trial) |
| Agent temperature | (auto-filled by runner from agent config) |
| Tool descriptions sha256 | (auto-filled by runner) |
| Foundation commit sha | (auto-filled by runner from local git) |

## Scoring

| Field | Value |
|---|---|
| Scoring tier | Tier-1 programmatic + tier-2 verifiable (parser-validation). No LLM-judge. |
| Score columns | `process` / `outcome` / `environment` reported separately |
| Reporting unit | `<rate> [<lo>, <hi>] (Wilson 95%, n=N)` |
| MDE pre-registered | Δ ≥ 0.20 for headline A/B claims |
| Power | ~90% for Δ=0.20 at n=75 (per playbook § 9 — Miller arXiv:2411.00640) |
| Multiplicity | Bonferroni by default; Holm-Bonferroni or BH if k ≥ 4 |
| Paired tests | McNemar's exact for binary; Wilcoxon signed-rank for ordinal |
| Judge model | n/a (no LLM-judge in this slice) |
| Judge prompt sha256 | n/a |

## Reproducibility

```bash
# Replay an existing capture
./evals/score.py ingestion/tafi_2025 --run <captured-run-dir>

# End-to-end (when runner ships)
./evals/runner.sh ingestion/tafi_2025 \
  --agent-id agent_011CaaVZBRsEyuN4hXWMRR4Z \
  --env-id env_01WaJyfTQu9YDfQC5vXiXWj5 \
  --files file_011CaaVTNcQEKbg4Dt1vCcCF,file_011CaaVTupcqW1ZuPvi63z1M \
  --paraphrases all \
  --trials-per-paraphrase 25
```

## Limitations honestly reported

- **n=1 at slice ship.** Every claim is exploratory until the runner backfills to n≥75.
- **No production-trace failure-mode taxonomy yet.** Open + axial coding (playbook § 4) pending ≥20 traces.
- **No held-out validation case.** Tafi is the seed; the next client is held-out.
- **No sensitivity-variant cases yet shipped** (PDF-only, CSV-only, corrupted-PDF).
- **Self-clean masking partially defended.** The scorer checks `>0 bytes` and parseability, but does not yet verify *content correctness* of normalized CSVs. A future enhancement: schema-validate each CSV's columns and value distributions.

## Anti-pattern compliance audit (per playbook § 8)

| Anti-pattern | Compliant? |
|---|---|
| Likert scoring | ✓ binary only |
| Generic metrics | ✓ all case-specific |
| Premature LLM-judge | ✓ none |
| Single-prompt cell | ✓ ≥3 paraphrases (data backfill pending) |
| Stub-file masking | ✓ content checks present |
| n=1 measurement claims | ✓ flagged exploratory |
| Static contamination decay | ✓ SemVer + quarterly audit policy |
| No run manifest | ✓ this factsheet + auto-emitted manifest.json |
| Process/outcome/env conflation | ✓ column tags in `expected.json` |
| No Bean's-8 worksheet | ✓ `spec.md` |
| Whack-a-mole tweaking | ✓ pre-registered MDE; regression set |
| Wald CIs at small n | ✓ Wilson only |
| Multiplicity unhandled | ✓ Bonferroni default |
| Stacked abstractions | ⚠ `expected.json` authored by model, awaits user sign-off |
| Single-attack ASR-as-ASR | n/a (not an adversarial slice) |
| Phenomenon-proxy gap | ⚠ partial — `spec.md` § 8 names the construct, but two non-target routes ("agent emits envelope without doing work" via stub files) need stronger defense than current content checks |

## Pre-registered predictions for next ablation

> Lock these BEFORE running, per playbook § 9 (Lin et al. arXiv:2604.25850 decision observability). Empty until the next ablation is queued.

(none pending)

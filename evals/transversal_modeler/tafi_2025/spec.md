# Slice spec: `transversal_modeler/tafi_2025`

> **Construct-validity worksheet.** Required by `playbook/PLAYBOOK.md` § 9 (Bean et al., NeurIPS 2025 D&B). Every measurement claim made from this slice must trace back to an answer below.

> **Status: scaffold-only.** The `transversal_modeler` agent is not yet provisioned on the platform. This slice exists to prove the eval scaffold drops in cleanly to a different agent role with a materially different I/O shape. Live trials begin once the agent is provisioned.

## Bean's 8

### 1. Precise definition + scope

**Phenomenon:** *Transversal-modeling correctness* — an agent acting in the `transversal_modeler` role, when given one contract's normalized financial CSVs + manifest, produces an Excel workbook (`model.xlsx`) that:

- Contains exactly four sheets: `P&L`, `Balance Sheet`, `Cash Flow`, `Valuation`.
- Preserves the named ranges (`industry_benchmarks`, `bespoke_assumptions`, etc.) that downstream `bespoke_modeler` depends on.
- Uses Excel formulas for every computed cell (no hard-coded subtotals); only input cells (reported historicals) hold literals.
- Each sheet has a validation cell returning `OK` or `UNBALANCED <delta>`; tolerance is 0.01 of the reporting currency.
- Returns a parseable envelope `{status, model_path, transversal_sheets[], validation, notes}`.
- Zero `is_error: true` events; `stop_reason: end_turn`.

**In scope.** Single-contract sessions; standard P&L / Balance / Cashflow / Valuation core; reported periods + 3 forecast years; NIIF/IFRS or US GAAP; Spanish or English source manifests.

**Out of scope.** Bespoke industry overlays (`bespoke_modeler`'s job); valuation parameter tuning (WACC choice — flagged as TODO not computed); multi-contract orchestration; mid-session interrupt recovery.

### 2. Confounder list + format-control + parser-validation

**Confounders we know about.**

| Confounder | Source | Mitigation |
|---|---|---|
| `xlsx` skill writes corrupting named ranges | process | prompt explicitly requires `bash + openpyxl` for writes; eval verifies named ranges survive |
| Template path missing on container | environment | retry; log as `environment` column |
| Tool-budget exhaustion mid-build | process | trial counts; flag if > 5% of trials |
| Float-precision balance failures (1e-6 < δ < 0.01) | construct | tolerance set to 0.01 of reporting currency, not zero |
| Single-prompt formulation noise | construct | ≥3 paraphrases per playbook § 8 |
| Numerical fixture values shifting interpretation | construct | fixtures are synthetic — assertions target structure, not values |

**Format-control.** All `kickoff.json` paraphrases share the same `contract_id`, `normalized_dir`, `manifest_path`, and target `model_path`; only natural-language phrasing differs.

**Parser-validation.** `xlsx_sheet_exists` and `xlsx_named_range_exists` open the file with `openpyxl` and check structurally — file existence alone is insufficient (defeats stub-file masking).

### 3. Sampling strategy + item-quality + sensitivity-variants

**Initial slice (this PR).** One case (`tafi_2025`), three paraphrases. **Trials at slice ship: 0** — agent not yet provisioned. The directory is reviewed and the assertions are frozen so live trials produce honest measurements as soon as the agent exists.

**Item-quality.** Fixtures are **synthesized** to match the schema ingestion produces. They are illustrative, not real Tafi numbers. The eval tests structural contracts (sheet shape, named range survival, formula presence), not numerical accuracy of the output. A second case based on real ingestion output is the next step.

**Sensitivity-variants (planned, not in this PR).**

- `tafi_2025_xlsx_skill_writes` — same case but with the prompt's "use bash + openpyxl ONLY" rule removed; expect named-range loss.
- `tafi_2025_short_history` — fixture with only 1 period; expect `status: ok` with limited forecast.
- `tafi_2025_unbalanced` — deliberate balance-sheet imbalance in fixture; expect `status: failed` with diagnostic.

### 4. Reuse documentation + new-vs-original delta

This is the first `transversal_modeler` slice. Scaffold reuses the `ingestion/tafi_2025` shape verbatim (spec.md, factsheet.md, expected.json, resources.json, kickoff_v*.json) — that is the point. Differences:

- `expected.json` introduces three new assertion types: `xlsx_sheet_exists`, `xlsx_named_range_exists`, `xlsx_validation_cell`. These are stubbed in `evals/score.py` until `openpyxl` is wired.
- `resources.json` mounts six fixture files instead of two original-document files.

### 5. Contamination test + held-out set

**Inputs.** Synthesized fixtures based on public-domain micro-credit financial structure. Zero contamination risk; the model has no exposure to these specific numbers.

**Ground truth.** Sheet structure (`P&L`, `Balance Sheet`, `Cash Flow`, `Valuation`) is the agent's contract from its system prompt — the model could "learn" to produce these sheets only if it had memorized that prompt, which is the point: the prompt is the spec.

**Held-out set.** The next case (different client, different period, real ingestion output) is the held-out validation. No model evaluation against this slice may also have been used to tune the agent's prompt.

### 6. N + power + uncertainty

Same decision-sized MDE table as `ingestion/tafi_2025`:

| Decision | Pre-registered MDE | n required |
|---|---|---|
| **A/B regression detection** | Detect any 3-of-N drop with α=0.05 via paired McNemar exact | n=10 paired |
| **Headline characterization** | Δ ≥ 0.10 with 95% CI half-width ≤ 0.05 | n=25/paraphrase × 3 paraphrases |
| **Construct-validity audit** | Across-paraphrase variance ≥ 0.10 | n=25 × all paraphrases |

**Reporting unit.** `<rate> [<lo>, <hi>] (Wilson 95%, n=N)`. Wald CIs forbidden.

**A/B contrasts.** Paired McNemar's exact when same trials run under two configs.

**Multiplicity.** Bonferroni default; Holm-Bonferroni or BH if k ≥ 4.

### 7. Qualitative + quantitative error analysis with confounder check

**Status at slice ship:** *zero* traces. Agent not yet provisioned. This slice supports zero measurement claims at ship; it is purely scaffold to prove the framework drops cleanly.

### 8. Phenomenon → task → metric → claim chain

| Layer | This slice |
|---|---|
| **Phenomenon** | Deployed transversal_modeler builds correct standardized financial cores. |
| **Task** | End-to-end transversal modeling of one contract's ingestion output → `model.xlsx`. |
| **Metric** | Pass-rate of structural assertions per (paraphrase × agent_version) cell, with `process / outcome / environment` columns reported separately, all with Wilson 95% CIs. |
| **Claim shape** | "Agent `<id>` v`<version>` has process pass-rate p_proc [lo, hi] and outcome pass-rate p_out [lo, hi] on `transversal_modeler/tafi_2025` at n=N." |

## Failure-mode classification

Same `process / outcome / environment` columns as ingestion. A trial is a "real fail" only if `process` failed; `environment`-only failures excluded with footnote.

## Anti-patterns this slice explicitly avoids

Same as ingestion + one new entry:

| Anti-pattern | This slice |
|---|---|
| ... (inherits from ingestion/tafi_2025/spec.md) | |
| Stub-file masking via empty .xlsx | `xlsx_sheet_exists` + `xlsx_named_range_exists` defeat empty workbooks |

## Outstanding gaps

- **Agent not provisioned.** Live trials cannot run yet.
- **`xlsx_*` assertion implementations** are stubs in `evals/score.py`. They raise `NotImplementedError` so a runner that processes this slice fails loudly until openpyxl is wired.
- **Fixtures are synthesized.** Real ingestion output capture is the next step.
- **No human Benevolent Dictator pass on `expected.json` yet.**

## Versioning

`expected.json` carries `schema_version`. Bumping is a breaking change to ground truth.

# Slice spec: `ingestion/tafi_2025`

> **Construct-validity worksheet.** Required by `playbook/PLAYBOOK.md` § 9 (Bean et al., NeurIPS 2025 D&B — eight construct-validity recommendations). Every measurement claim made from this slice must trace back to an answer below.

## Bean's 8

### 1. Precise definition + scope

**Phenomenon:** *Ingestion correctness* — an agent acting in the `ingestion` role, when given one contract's raw documents (PDF financial statement + CSV portfolio snapshot), produces:

- A parseable final envelope matching the published contract shape (`status`, `normalized_dir`, `manifest_path`, `missing_fields`).
- A complete manifest at `manifest_path` containing `entity`, `periods`, `pdf_extraction`, `csv_extraction`, `quality_flags`, `reconciliations`, and `outputs`.
- Normalized financial CSVs (P&L, balance sheet, cash flow) whose internal balance-sheet identity and cash-flow continuity reconcile within ±1.0 currency unit.
- A `quality_flags` array surfacing data-quality issues; **at least one** flag is required for any non-trivial real-world contract.
- Zero `is_error: true` events on the trial event stream and a `stop_reason: end_turn` termination.

**In scope.** Single-contract sessions; PDF text-based or scanned; CSV any reasonable size up to platform cap; financial statements in NIIF/IFRS or US GAAP; Spanish or English source.

**Out of scope.** Multi-contract orchestration, mid-session interrupt recovery, downstream synthesis quality, agent self-improvement, latency, cost.

### 2. Confounder list + format-control + parser-validation

**Confounders we know about.**

| Confounder | Source | Mitigation |
|---|---|---|
| Platform 5xx during file mount | environment | retry; log as `environment` column failure, not `process` |
| Environment cold-start failure | environment | retry; same column tagging |
| Tool-budget exhaustion mid-run | process | trial counts; flag if > 5% of trials |
| Model nondeterminism (temperature > 0) | process | record temperature in run manifest |
| Concurrent sessions on same env | environment | runner serializes |
| Single-prompt formulation noise | construct | ≥3 paraphrases per playbook § 8 |
| Self-clean masking (empty stub files) | process | scorer checks `> 0 bytes` and parseability, not just `exists` |

**Format-control.** All `kickoff.json` paraphrases share the same `contract_id`, file paths, and output path; only natural-language phrasing differs.

**Parser-validation.** Every output file is opened by the scorer in its declared format (JSON parsed, CSV read with `csv` module). `file_exists` alone is insufficient — defeats the "stub-file" failure mode.

### 3. Sampling strategy + item-quality + sensitivity-variants

**Initial slice (this PR).** One case (`tafi_2025`), three paraphrases, n target = 25 trials per (paraphrase × agent_version) cell. **Actual collected n = 1** at slice ship — flagged loudly as exploratory until the runner backfills.

**Item-quality.** The Tafi 2025 case was captured from a real production-shaped POC run. Ground-truth assertions in `expected.json` are structural and categorical only (no specific borrower names, no specific balance figures). Two-reviewer audit pending — at present only the model authored the assertions; the user has not yet signed off as Benevolent Dictator (per playbook § 8).

**Sensitivity-variants (planned, not in this PR).** Future slices add:

- `tafi_2025_pdf_only` — same case, CSV omitted, expect `missing_fields` non-empty.
- `tafi_2025_csv_only` — same case, PDF omitted, expect partial pass and explicit flag.
- `tafi_2025_corrupted_pdf` — first 100 bytes zeroed; tests fallback chain (pypdf → pdfplumber → OCR).
- A clean second case from a different client (held-out).

### 4. Reuse documentation + new-vs-original delta

This is the first ingestion case in the repo. No reuse to disclose. Future cases that build on this one MUST document construct drift per Bean § 5.4 (run new-vs-original on a held model, justify the modification).

### 5. Contamination test + held-out set

**Inputs.** The Tafi 2025 source documents are private client data not in any public corpus. Contamination risk for the inputs themselves is near-zero.

**Ground truth.** Balance-sheet identity (`assets = liabilities + equity`) is a domain invariant, not a memorable fact — model recall would not produce a passing trial. Reconciliation tolerances (`±1.0` currency unit) are tight enough that "guessing" is statistically infeasible.

**Held-out set.** This case is the seed. The next ingestion case (different client, different period) becomes the held-out validation set. No model evaluation against this slice may also have been used to tune the agent's prompt (ratchet rule — playbook § 8 contamination decay).

### 6. N + power + uncertainty

**MDE.** For headline claims comparing two `insignia_ingestion` versions:
- Pre-registered minimum detectable effect: **Δ ≥ 0.20** in pass-rate.
- At n=75 (3 paraphrases × 25 trials), two-proportion Wilson test has ~90% power for Δ=0.20.
- Pre-registration is mandatory per playbook § 9 (Lin et al. arXiv:2604.25850).

**Reporting unit.** Every rate reported as `<rate> [<lo>, <hi>] (Wilson 95%, n=N)` per playbook § 8 (Bowyer ICML 2025; ICLR Blogposts 2025). Wald / CLT-based intervals are explicitly forbidden — they under-cover at small n near the boundaries that dominate this slice (p ≈ 1.0).

**A/B contrasts.** Paired McNemar's exact test when same trials are run under two configs (per playbook § 9 — Miller arXiv:2411.00640). Wilcoxon signed-rank for ordinal/continuous.

**Multiplicity.** With k contrasts at uncorrected α=0.05, family-wise error ≈ 1−(0.95)ᵏ. Pre-register the contrasts; apply Bonferroni (α/k) by default; Holm-Bonferroni or Benjamini-Hochberg if k ≥ 4 (playbook § 8 — Luo et al. NeurIPS 2025 AI4Science).

### 7. Qualitative + quantitative error analysis with confounder check

**Required before this slice ships measurement claims:** ≥20 captured traces, open + axial coding into a discovered failure-mode taxonomy (playbook § 4). The first batch will likely come from real client onboarding — not this single Tafi run.

**Status at slice ship:** *one* trace, *one* happy path, *zero* error coding. This is explicitly insufficient for a measurement claim; this slice supports only smoke-grade assertions until the corpus reaches saturation (~20–40 traces per playbook § 1).

### 8. Phenomenon → task → metric → claim chain

| Layer | This slice |
|---|---|
| **Phenomenon** | Deployed ingestion agent processes new contracts correctly. |
| **Task** | End-to-end ingestion of one contract's input pair → declared output bundle. |
| **Metric** | Pass-rate of structural + content assertions per (paraphrase × agent_version) cell, with `process / outcome / environment` columns reported separately, all with Wilson 95% CIs. |
| **Claim shape** | "Agent `<id>` v`<version>` has process pass-rate p_proc [lo, hi] and outcome pass-rate p_out [lo, hi] on the `ingestion/tafi_2025` task at n=N." **Never** "agent X is correct." |

## Failure-mode classification (process / outcome / environment)

Per playbook § 8 (Microsoft Universal Verifier 2026), every assertion in `expected.json` is tagged with one of:

- **`process`** — agent intent or behavior. The agent emitted the right text, called the right tool, applied the right discipline. Failure here is a real agent regression.
- **`outcome`** — artifact materialized correctly. The file exists, parses, contains the asserted structure. Failure here may be agent or environment; co-tagged with the same trial's `environment` column for triangulation.
- **`environment`** — platform / tooling confounder. Cold-start failure, 5xx, quota exhaustion, scheduler latency. Failure here is **not** scored against the agent.

Aggregation reports the three columns separately. A trial is a "real fail" only if `process` failed; an `environment`-only failure is reported and excluded from the rate denominator with a footnote.

## Anti-patterns this slice explicitly avoids

| Anti-pattern (playbook § 8) | This slice |
|---|---|
| Likert scoring | Binary only |
| Generic off-the-shelf metrics | All assertions are case-specific |
| Premature LLM-judge | None present |
| Single-prompt cell scoring | ≥3 paraphrases (will be backfilled to 25 trials each) |
| Stub-file masking (self-clean) | Content checks defeat empty stubs |
| n=1 measurement claims | Smoke-grade only at slice ship; CI reported for honesty |
| Static-benchmark contamination decay | SemVer'd in `expected.json` schema_version field; cleanup-pass policy in README |
| No run manifest | Every run emits `manifest.json` with shas + model + temp + seed (see `factsheet.md`) |
| Process / outcome / environment conflation | Explicit column tagging |

## Outstanding gaps (open issues, not blockers)

- **n still equals 1.** Runner backfills to 25/paraphrase = 75 trials/version. Until then, every claim from this slice is "exploratory."
- **No human Benevolent Dictator pass on `expected.json` yet.** The user has not yet signed off; assertions were authored by reading the agent's own output. Schedule a manual review pass.
- **No production-trace failure-mode taxonomy.** Open + axial coding pending arrival of ≥20 traces.
- **Sensitivity-variant cases not yet shipped.** See § 3 list.

## Versioning

`expected.json` carries `schema_version`. Bumping the version is a breaking change to ground truth and requires a corresponding entry in this slice's "Reuse documentation" section above.

# Slice spec: `ingestion/tafi_2025_v3`

> Sibling of `ingestion/tafi_2025` — same case, but exercises the **v3-only**
> manifest extensions: `client_email_draft` (Spanish follow-up) and the
> `missing_fields_referenced ⊆ missing_fields` invariant. v2 ignores these.

## Bean's 8 (concise — full worksheet inherits from `tafi_2025`)

### 1. Definition + scope

**Phenomenon.** When the v3 ingestion agent receives a kickoff missing one
required input (a PDF dictamen the case has been pruned to omit), it must:

- Return envelope `{status: "blocked", missing_fields: [...]}` (not `ok`).
- Emit a manifest with a populated `client_email_draft` whose:
  - `language == "es"` (matches `email_context.language`)
  - `body` is ≥ 50 chars and contains zero of `TBD`, `TODO`, `[…]`
  - `missing_fields_referenced` ⊆ envelope `missing_fields`

**Out of scope.** Reconciliation correctness, normalized-CSV column counts —
those signals are inherited from the v2 slice and would just duplicate work.
This slice is a focused regression check on the v3 deltas.

### 2. Confounders

| Confounder | Mitigation |
|---|---|
| Single-prompt formulation noise | one paraphrase ships at v0.1; n is exploratory |
| Language detection on body | scorer uses `langdetect` if installed; falls back to byte-class probe |
| Substring match for forbidden literals | exact `in` check (case-sensitive — TBD ≠ tbd) |

### 3. Sampling

n = 1 (exploratory) at slice ship. Same paraphrase strategy as parent slice;
defer to it for the construct-validity worksheet on phrasing-induced variance.

### 4. Reuse

Copies the parent slice's resources + factsheet by reference; only `expected.json`
and `kickoff_v3.json` are slice-specific.

### 5. Contamination

Same domain invariants as parent — Spanish follow-up tone is content the model
hasn't seen, drawn from the contract's email thread metadata.

### 6. N + power

Exploratory v0.1. Pre-register before scaling.

### 7. Worker-kit reuse / 8. Reporting

Per parent slice. Wilson 95% CIs; paired McNemar across v2/v3 envelope columns
(only the v3-only assertions count for v3-specific regression).

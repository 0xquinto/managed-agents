# Slice spec: `ingestion/tafi_2025_v3_two_missing`

> Sibling of `ingestion/tafi_2025_v3`. Same input bundle (PDF balance + CSV cartera, no dictamen) but the kickoff's `required_documents` adds a second missing item — `memoria` — to validate that the v3.2 kickoff-driven mechanism generalizes to:
> 1. **Plurality** — multiple missing items, not just one.
> 2. **Names not in v3.2 iteration history** — `memoria` is not a term v3.2 was tested against during prompt iteration, so a passing trial confirms the agent isn't memorizing a specific document name.
>
> The agent should detect 2 missing items, populate `missing_fields: ["dictamen", "memoria"]` (order-insensitive, both required), and draft an email referencing BOTH.

## Bean's 8 (concise — full worksheet inherits from `tafi_2025_v3`)

### 1. Definition + scope

**Phenomenon.** When v3.2 receives a kickoff with `required_documents = [balance, cartera, dictamen, memoria]` and `input_files` containing only balance + cartera:

- Envelope: `{status: "blocked", missing_fields: ["dictamen", "memoria"]}` (set equality).
- Manifest's `client_email_draft.missing_fields_referenced ⊆ missing_fields` and contains both `dictamen` and `memoria`.
- Email body references both missing items by canonical name (Spanish: "dictamen del auditor", "memoria de cálculos" or similar).

**Out of scope.** Reconciliation correctness, manifest-schema completeness — those are covered by the parent slice `tafi_2025_v3`.

### 2. Confounders

| Confounder | Mitigation |
|---|---|
| Agent might collapse 2 items into 1 generic "missing data" mention in the email | scorer requires `body` to contain BOTH "dictamen" and "memoria" (case-insensitive substring) |
| Agent might add other items it thinks are also missing (e.g., notas, anexos) | scorer requires `missing_fields ⊇ {dictamen, memoria}` (superset, not exact) |
| Field naming drift (`dictamen` vs `dictamen del auditor` vs `auditor`) | required_documents uses canonical short names; agent's `missing_fields` must use those exact strings |

### 3. Sampling

n = 1 at slice ship. Pre-register n=10 before scaling — Wilson 95% CI claims need n≥10.

### 4. Reuse

Copies parent's PDF + CSV file_ids. Memory store config inherited from parent.

### 5. Contamination

`memoria` is intentionally chosen because it was NOT in the v3.2 prompt iteration set or the tone_examples training corpus. A passing trial here is evidence the agent is following the kickoff-driven mechanism, not memorizing.

### 6. N + power

Exploratory v0.1.

### 7+8

Per parent slice.

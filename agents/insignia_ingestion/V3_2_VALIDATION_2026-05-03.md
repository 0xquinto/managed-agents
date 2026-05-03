# Ingestion v3.2 — validation suite — 2026-05-03

After v3.2 hit 18/18 PASS at n=1, ran two follow-up sweeps to (a) confirm the n=1 result holds at n=10 and (b) verify the kickoff-driven required-documents mechanism generalizes beyond the single-missing-item slice it was iterated against.

Agent: `agent_011Cafd9hFGY7U239itLqJ8n` (insignia_ingestion_v3_2, sonnet-4-6).

## Sweep 1 — n=10 fan-out on `tafi_2025_v3` slice

Captured: `evals/runs/2026-05-03T13-02-05Z-ingestion-tafi_2025_v3-agent_011Cafd9hFGY7U239itLqJ8n/`.

**Aggregate: 17/18 assertions at 10/10 PASS. One real flake.**

| Column | Mean pass-rate | n | Wilson 95% lower bound (worst per-assertion) |
|---|---|---|---|
| process | 0.983 | 6 | 0.596 (the flake; rest at 0.722) |
| outcome | 1.000 | 12 | 0.722 |
| environment | n/a | 0 | — |

### The 1 real flake: `envelope_format.no_surrounding_prose` 9/10 [0.596, 0.982]

Trial `v3_004` emitted:
```
All outputs are in place. Final envelope:

{"status":"blocked",...,"missing_fields":["dictamen"]}
```

Same prose-preamble pattern that surfaced in the v3 baseline (100%) and v3.1 (still 100%). v3.2's strong response-format discipline rule ("FIRST char must be `{`, no announce-completion, no closing summary") brings the rate from ~100% to ~10% but doesn't eliminate it. **Other content assertions on `v3_004` still PASSed** — `score.py::_extract_envelope_object`'s largest-balanced-span scanner is prose-tolerant, so the agent's underlying judgment (status, missing_fields, draft) is captured even when the cosmetic wrapping fails.

### Production implication

`no_surrounding_prose` is `column: process` today. Two ways to handle the 10% flake:
- **(A) Ship as-is.** The cosmetic failure has no functional impact on the deployed pipeline because the SDK-side envelope extractor is prose-tolerant. The eval assertion still runs as an early-warning signal if the extractor or the prompt ever weakens.
- **(B) Move to `column: environment`** (parallel to the resolver `no_markdown_fences` decision documented in `agents/insignia_resolver/MODEL_TIER_FINDINGS_2026-05-02.md` § "no_markdown_fences moved from process to environment"). Stops charging the agent for a behavior that doesn't break production.

**Decision deferred** until we have at least one trial where the prose preamble *did* break something downstream — so far it hasn't. Keep on `process` as a tripwire.

### What stayed at 10/10

The content assertions that matter for the production decision:

| Assertion | k/n | Wilson 95% CI |
|---|---|---|
| `envelope.status == "blocked"` | 10/10 | 1.000 [0.722, 1.000] |
| `envelope.missing_fields ⊇ ["dictamen"]` | 10/10 | 1.000 [0.722, 1.000] |
| `envelope_format.no_markdown_fences` | 10/10 | 1.000 [0.722, 1.000] |
| `manifest.client_email_draft` (object) | 10/10 | 1.000 [0.722, 1.000] |
| `manifest.client_email_draft.language == "es"` | 10/10 | 1.000 [0.722, 1.000] |
| `manifest.client_email_draft.body` ≥ 50 chars | 10/10 | 1.000 [0.722, 1.000] |
| `manifest.client_email_draft.body` no forbidden tokens | 10/10 | 1.000 [0.722, 1.000] |
| `missing_fields_referenced ⊆ missing_fields` | 10/10 | 1.000 [0.722, 1.000] |
| 8 manifest-schema required_keys assertions | 10/10 each | 1.000 [0.722, 1.000] |
| `outputs.file_exists_and_nonempty` | 10/10 | 1.000 [0.722, 1.000] |

All Wilson lower bounds ≥ 0.722. v3.2's classification + draft mechanism is reliable at the n=10 sample.

## Sweep 2 — generalization slice `tafi_2025_v3_two_missing` (n=1)

Captured: `evals/runs/2026-05-03T13-06-49Z-ingestion-tafi_2025_v3_two_missing-agent_011Cafd9hFGY7U239itLqJ8n/`.

Same input bundle as the parent slice (PDF balance + CSV cartera, no dictamen). Kickoff carries `required_documents = [balance, cartera, dictamen, memoria]` — adds `memoria` to test:

1. **Plurality** — does v3.2 handle multiple missing items, not just one?
2. **Names not in v3.2 iteration history** — `memoria` was never used during prompt iteration. A passing trial confirms the agent is following the kickoff-driven mechanism, not memorizing canonical names.

**Result: 18/18 PASS at n=1.**

Envelope:
```json
{"status":"blocked","missing_fields":["dictamen","memoria"],...}
```

Email body (excerpt):
> "Hola Ana,
>
> Gracias por el envío del balance y la cartera — ya los tenemos procesados. Para cerrar el análisis Q1 nos faltan dos documentos:
>
> 1. **Dictamen del auditor independiente** — el informe de auditoría firmado como PDF independiente. **Notamos que el texto del informe aparece incluido dentro del EF, pero necesitamos el documento firmado por separado.**
> 2. **Memoria anual** — el informe de gestión / memoria correspondiente al ejercicio 2025."

Two notable things:

- The agent referenced both missing items by name in the body (`contains_all_substrings_ci ["dictamen", "memoria"]` PASS, n=2/2 across the body's 2 assertions).
- The agent **explicitly applied the v3.2 prompt's "embedded ≠ present" rule in its email** — calling out that the auditor text appears embedded in the EF but isn't a standalone signed PDF. This is the rule v3.2 was added to teach, surfacing in the agent's communication unprompted. Strong evidence v3.2 internalized the rule, not just the keyword.

Generalization confirmed at n=1. Pre-register n=10 before scaling claims; for now, the n=1 result is consistent with the parent slice's n=10 — the mechanism is doing what we asked.

## Combined picture

| Slice | n | Process | Outcome | Notes |
|---|---|---|---|---|
| `tafi_2025_v3` (single missing) | 10 | 0.983 | 1.000 | 1 prose-preamble flake; content all 10/10 |
| `tafi_2025_v3_two_missing` (two missing) | 1 | 1.000 | 1.000 | Generalization confirmed at n=1 |

## Cost + cadence

- 11 trials × ~$0.10 = ~$1.10 spend. Wall-clock: ~50 min serial for the n=10, ~5 min for the two_missing.
- Could parallelize the n=10 across slices if needed for the v2↔v3.2 paired-McNemar; the current runner serializes within a paraphrase loop.

## Production decision (pending v2↔v3.2 A/B)

v3.2 is the **prompt-side production candidate** for the email-driven POC. The remaining unknown is whether v3.2 actually beats v2-deployed on this kind of slice — the v2 prompt has no required-documents logic, no memory-store integration, no email-draft mechanic, so the prediction is "v3.2 ≫ v2 on missing-document handling." That's a paired-McNemar at n=25 per side per playbook § 9 — ~$5 spend, ~2h wall, deferred until explicitly authorized.

## Open follow-ups

1. **Prose-preamble flake at 10%.** Worth a v3.3 attempt? Or accept the 10% and move on — the production envelope extractor handles it, and chasing the last 10% of cosmetic compliance has diminishing returns.
2. **Memory-store mount-path probe extension.** The kebab-cased-store-name behavior (sessions-expert.md L196) is documented from one observation. Add a `behavior-auditor` probe `P-sessions-2` covering `memory_store` mount semantics across underscore vs. mixed-case vs. hyphenated store names.
3. **`no_surrounding_prose` column attribution.** Decide A vs B (process vs environment) when we have at least one trial where the preamble caused a real downstream failure. So far we have zero such cases.

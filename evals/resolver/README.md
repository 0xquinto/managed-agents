# Resolver eval slices

Four cases covering the resolver agent's three decisions per spec § 3.5
(`new_contract` | `continuation` | `triage`) plus the supersession edge case
(`continuation` with `superseded_by_prior: true`).

| Case | Decision | What it tests |
|---|---|---|
| `new_contract` | `new_contract` | empty registry; sender domain unseen → propose new contract |
| `continuation` | `continuation` | registry contains matching open contract by sender + subject |
| `supersession` | `continuation` | attachment hashes seen for same contract → `superseded_by_prior: true` |
| `triage` | `triage` | ambiguous case (multiple candidates within similar score) → triage payload populated |

Resolver is `claude-haiku-4-5` (per spec § 3.2). Read-only — no `bash`,
no `write`. The whole role is "read kickoff JSON, emit envelope JSON."

**Slice version 0.1.0.** Per case n=1 at ship; pre-register before scaling.
Construct-validity inherits the ingestion slice's worksheet — see
`evals/ingestion/tafi_2025/spec.md`.

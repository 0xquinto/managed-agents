# `insignia_resolver` changelog

The deployed `system` field on the platform is the source of truth; this file
is the local diffable artifact for prompt versions.

## v1 — 2026-05-02

Initial version. Spec: `docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md` § 3.

- **Identity:** classifies inbound emails into `continuation` / `new_contract` / `triage`; flags literal-duplicate attachment bundles via `superseded_by_prior`.
- **Model:** `claude-haiku-4-5` (per spec § 3.2). Bumping to Sonnet is a v2 option if eval shows triage-precision drop.
- **Tools:** `read` only (for on-demand `/mnt/memory/priors/<contract_id>.json` lookups). No `bash`, no `write`, no skills.
- **Kickoff:** `ResolverKickoff` per `poller/poller/schemas.py` (email + attachments + full registry + `attachment_hashes_seen_for_candidate`).
- **Output:** `ResolverEnvelope` per `poller/poller/schemas.py`. Single JSON object; no prose, no fences.
- **Decision discipline:** continuation requires *exact* sender-address match plus conversationId-in-priors OR subject-tag match (confidence ≥ 0.9). Anything ambiguous → `triage` (confidence ≤ 0.7).
- **Supersession:** only checked on `continuation`. Literal hash duplication only; meaningful-supersession (byte-different but same content) is not in v1 scope.

Eval slices live under `evals/resolver/{continuation,new_contract,supersession,triage}/`.

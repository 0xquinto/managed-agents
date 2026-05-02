# `insignia_resolver` changelog

The deployed `system` field on the platform is the source of truth; this file
is the local diffable artifact for prompt versions.

## v2 — 2026-05-02

Surgical iteration off v1 baseline (paired-McNemar A/B test pair). Two targeted changes only — fits playbook § 9 minimal-diff requirement.

- **Format discipline tightened.** v1 baseline showed 4/4 slices wrapped envelope in ```json fences and supersession also leaked prose preamble. v2 adds: literal "FIRST char must be `{`, LAST char must be `}`" rule; explicit ✅ correct example; explicit ❌ wrong examples (fence wrapper, prose-before, prose-after) so the failure modes are named in the prompt.
- **`new_contract` requires confident client_name.** v1 misclassified the triage slice as `new_contract` because the literal rule "zero registry match → new_contract" fired even though the email body was bare ("attached are the financials" — no client name, no context). v2 adds: bare-body cases route to triage, with the inferred client in `triage_payload.inferred_new_contract`.

Same model (`claude-haiku-4-5`), same tools (`read` only). Eval slices unchanged.

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

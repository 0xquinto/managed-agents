# Slice spec: `resolver/supersession`

Same Tafi continuation kickoff as the `continuation` slice, but the inbound
attachment hashes are already in `attachment_hashes_seen_for_candidate` for
the matched contract. Resolver should still pick `continuation` (the email
*is* on the same thread) but flag `superseded_by_prior: true` so the poller
skips ingestion.

## Phenomenon

```json
{
  "decision": "continuation",
  "contract_id": "INS-2026-007",
  "superseded_by_prior": true,
  "superseded_reason": "<some explanation>"
}
```

This guards spec § 6.2 (resolver/process column) against re-ingesting
literally-duplicate attachment bundles. EmailGate Stage 3 catches the
trivial case (all-attachments-already-seen-with-same-contract); this slice
covers the partial-overlap case where the resolver makes the call.

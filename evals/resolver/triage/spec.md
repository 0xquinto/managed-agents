# Slice spec: `resolver/triage`

Two open contracts (Tafi + Tucumán Capital) with overlapping subject patterns,
inbound email from a sender domain (`finanzas.com.ar`) that's NOT on either
row's `sender_addresses`, but whose subject matches both. Resolver should not
guess — it should triage.

## Phenomenon

Given an ambiguous registry match — sender unknown to both candidate
contracts, similar subject patterns to multiple — the resolver returns:

```json
{
  "decision": "triage",
  "contract_id": null,
  "confidence": <= 0.7,
  "rationale_short": "<some reason mentioning ambiguity>",
  "triage_payload": {
    "question": "<a one-sentence question for the human>",
    "candidates": [
      {"contract_id": "INS-2026-007", "score": ..., "reason": "..."},
      {"contract_id": "INS-2026-008", "score": ..., "reason": "..."}
    ]
  }
}
```

`new_contract_proposal` may be present (if the resolver also surfaces the
"or it's brand new" hypothesis) but is optional.

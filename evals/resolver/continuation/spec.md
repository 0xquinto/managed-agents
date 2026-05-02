# Slice spec: `resolver/continuation`

Registry contains an open contract `INS-2026-007` for Financiera Tafi. Inbound
email from `ana@tafi.com.ar` (a registered sender on that row) with a related
subject. Resolver should pick `continuation` and the matching `contract_id`.

## Phenomenon

Given a kickoff with one registry row whose `sender_addresses` includes the
inbound email's `from` address, and a subject related to the existing
contract, the resolver returns:

```json
{
  "decision": "continuation",
  "contract_id": "INS-2026-007",
  "confidence": >= 0.7,
  "rationale_short": "<sender match / subject match / both>",
  "superseded_by_prior": false
}
```

`triage_payload` and `new_contract_proposal` must both be `null`.

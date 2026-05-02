# Slice spec: `resolver/new_contract`

Empty registry; brand-new sender domain. Resolver should classify as
`new_contract` and emit a `NewContractProposal`.

## Phenomenon

Given a `ResolverKickoff` with `registry: []` and a sender domain not present
under any registry row, the resolver returns:

```json
{
  "decision": "new_contract",
  "contract_id": null,
  "confidence": >= 0.5,
  "rationale_short": "<some reason mentioning new sender or empty registry>",
  "new_contract_proposal": {
    "client_name": "<inferred from email>",
    "sender_domain": "tafi.com.ar",
    "suggested_contract_id": "INS-YYYY-NNN",
    "suggested_onedrive_path": "/Contracts/<...>/",
    "suggested_teams_channel_name": "<...>"
  }
}
```

## Out of scope

The agent's contract-id pattern: format is enforced by the `ResolverEnvelope`
Pydantic schema (regex `^INS-\d{4}-\d{3}$`); we don't assert which specific
number it picks.

## Construct validity

Inherits parent ingestion-slice worksheet. n=1 at ship.

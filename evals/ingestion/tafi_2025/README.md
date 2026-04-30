# Case: `ingestion/tafi_2025`

First eval case for any agent acting in the `ingestion` role. Frozen from the 2026-04-30 POC smoke run.

## What it tests

The agent is given a 39-page Spanish-language NIIF/IFRS audited financial statement PDF (~1.5 MB) and a 27 MB cumulative-snapshot loan portfolio CSV (156k rows × 24 cols), and must produce:

1. A structured **final envelope** — `status`, `normalized_dir`, `manifest_path`, `missing_fields`.
2. A complete **manifest** at the declared `manifest_path`.
3. **Normalized outputs** — entity, P&L, balance sheet, cash flow, classification.
4. **Reconciliation checks** — both balance sheets and both cash-flow statements must reconcile to zero (or be flagged with severity `error`).
5. **Quality flags** — at least 5 distinct categories, including a going-concern signal (the underlying entity has negative equity and a 98× YoY loss deterioration), an encoding issue (UTF-8 mojibake in ~9% of CSV rows), and a CSV-snapshot-series caveat (rows must be filtered by `Source.Name` for period-specific work).

## What it does NOT test

- **Specific values.** Borrower counts, balance figures, and other client-specific data are not asserted — those would leak PII and would be brittle. Assertions are structural and categorical.
- **Wall-clock latency.** First-run cold-start overhead is platform-side; not part of agent correctness.
- **Tool-call efficiency.** A separate eval (`ingestion/tafi_2025_perf`) can be added if perf becomes a contract, but the first case is correctness-only.

## Provenance

- **Captured run:** `runs/2026-04-30T18-40-29Z-poc/smoke/`
- **Agent:** `insignia_ingestion` v1 (`agent_011CaaVZBRsEyuN4hXWMRR4Z`)
- **Session:** `sesn_011CaacsF6hNQ5GJPNQMie2E`
- **Verified by:** manual review of `ingestion_run_log.md` + the final envelope + the manifest's quality flags

## Re-using the platform resources

The captured session and its files are still alive on the platform (verified post-run). The eval `runner.sh` can either re-use them via the IDs above or upload fresh copies — both modes are supported.

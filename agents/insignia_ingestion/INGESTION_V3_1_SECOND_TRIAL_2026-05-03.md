# Ingestion v3.1 — second live trial — 2026-05-03

After v3.1 prompt fixes addressing first-trial findings 1, 2, 3 + runner fix for finding 4 + scorer fix for `reconciliations` dict shape. Sonnet-4-6 v3.1 prompt (`agent_011CafbK1SfSiKB7HtWMGca4`), 1 trial, n=1, same `evals/ingestion/tafi_2025_v3` slice.

Captured at `evals/runs/2026-05-03T11-55-48Z-ingestion-tafi_2025_v3-agent_011CafbK1SfSiKB7HtWMGca4/`.

**Score: 8/19 assertions pass** (vs. 0/5 for v3 first trial; the denominator grew from 5→19 because v3's run crashed score.py before reconciliations + manifest schema assertions ran).

## Status of the 4 findings

| # | Finding | v3.1 status |
|---|---|---|
| 1 | Memory mount path | **Fully fixed.** Agent read directly from `/mnt/memory/insignia-memory/...` via the kickoff-supplied paths — no probing needed. Sessions-expert.md note updated. |
| 2 | Required-documents detection (status=blocked when dictamen absent) | **Not fixed.** New mode of failure: agent classified embedded auditor narrative inside the EF PDF as the dictamen. Quote (event 47): *"Good — the PDF contains both financial statements AND the embedded auditor's report (pages EF-2, 4-7)."* The prompt's required-docs list is now in place but the agent's *classification* of the EF PDF's contents is what's wrong. |
| 3 | Format discipline | **Partially fixed.** Markdown fences gone (assertion 1/1 PASS). But prose preamble remains: *"All outputs are in the correct locations. Everything is verified and complete."* before the JSON envelope. The "FIRST char must be `{`" rule alone isn't enough on Sonnet ingestion. |
| 4 | Manifest fetch broken | **Fully fixed.** `extract_write_tool_content` reads the agent's `agent.tool_use(write)` event directly. Manifest captured (5400 chars, all required keys present, schema correct). 7 unit tests added. |

## What's actually new: the "embedded dictamen" hallucination (finding 2 mode 2)

The slice is built around `Borrador de EF 2025 - Financiera Tafi - MICI.pdf` — a *draft* of the financial statements. The email body explicitly says *"el dictamen del auditor te llega la próxima semana"* (the auditor's report arrives next week). So the dictamen is NOT in the input bundle.

But the agent reads the PDF, finds boilerplate auditor-related text inside the EF (sign-off blocks, references to the auditor's role, page headers like "Estados Financieros" + "Informe de Auditoría"), and concludes the dictamen *is* embedded. The hard-coded required-docs rule in v3.1 doesn't help because the agent thinks `dictamen ∈ files_classified`.

**Two fixes worth considering:**

- **(A)** Add a "dictamen is a SEPARATE document" rule to the prompt: *"The dictamen del auditor is a standalone, signed PDF — not pages within an EF. Auditor sign-off boilerplate inside an EF binder does not count. Only count `dictamen` as present if there's a separate file in `input_files` whose classification is `dictamen` with confidence ≥ 0.8."*
- **(B)** **Move required-documents to kickoff schema (option B from first findings doc).** Kickoff carries `expected_documents: ["balance", "cartera", "dictamen"]` and the agent matches by `files_classified[*].type` against the expected set. The orchestrator owns the contract spec; the agent owns classification+extraction. Cleaner production shape.

Option B is what we should ship for the production poller. Option A is a stop-gap if we want to re-validate the v3.1 mechanism on this slice today.

## What's working that wasn't before

- 8/8 manifest schema assertions pass (`required_keys.{entity, periods, pdf_extraction, csv_extraction, quality_flags, reconciliations, missing_fields, outputs, client_email_draft}`). v3.1 produces a structurally correct manifest.
- Memory-store reads succeeded — agent read priors + 3 tone examples without probe attempts.
- Trial completed in ~5 min (vs. 8 min for v3) — fewer probe-and-explore tool calls because the kickoff paths were correct.
- `manifest_captured: true` with `manifest_source: "write_event"` — the runner's new fast path worked first try; the bash fallback was never invoked.

## NEW finding: score.py `reconciliations` dict-vs-list bug

`evals/ingestion/tafi_2025_v3/expected.json` declares `"reconciliations": {"_note": "v3 slice does not check reconciliations..."}` (a dict, deliberately empty of assertions). `score.py::score_reconciliations` did `for a in expected.get("reconciliations", []):` — iterating a dict yields the string key `"_note"`, which crashed `a.get("column", ...)`. Fixed: scorer now treats dict-shaped reconciliations as no-op.

## Cost

~$0.10 (one Sonnet ingestion session, ~14 tool calls, ~5 min).

## Recommended next step

**v3.2 with kickoff-driven document spec (option B).** Move `required_documents` from prompt to kickoff. Re-run on this slice — should expose the embedded-dictamen hallucination as a classification-confidence question (the agent has to put `dictamen` in `files_classified` with confidence≥0.8 OR it's missing).

Alternative: pick a DIFFERENT eval slice for the missing-document validation — one where the missing item is unambiguous (e.g., a CSV-only kickoff with no balance PDF at all). The current slice's premise (PDF "EF" without dictamen) is genuinely ambiguous to a Spanish-reading agent because EF binders sometimes embed the auditor's report.

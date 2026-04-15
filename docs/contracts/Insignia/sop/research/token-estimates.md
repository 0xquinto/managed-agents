# Per-agent token estimates (one Insignia contract)

_Engineering projection pre-smoke-test. Update with actuals after first live run. Based on the Tafi representative contract (2 input files: one scanned PDF financial statement `Borrador de EF 2025 - Financiera Tafi - MICI.pdf`, and one 27MB CSV `Cartera Total TAFI.csv`)._

## Methodology

**System prompt token counts** are estimated as word-count × 1.3. Word counts were derived from reading each prompt directly: coordinator (~330 w → ~430 tok), ingestion (~490 w → ~640 tok), transversal_modeler (~490 w → ~640 tok), bespoke_modeler (~530 w → ~690 tok), synthesis (~540 w → ~700 tok).

**Turn counts** use the task-guidance anchors adjusted for Tafi-specific complexity:

- `coordinator` anchored at 10 turns: one turn per worker dispatch (4 foreground calls), plus the initial routing decision, reading the user envelope, writing the coordinator.log, assembling the final JSON envelope, and 2 contingency turns for a blocked or retry scenario.
- `ingestion` anchored at 15 turns (midrange of 10–20): classifying 2 files (2 turns), extracting the scanned PDF (3 turns: pdf skill attempt → detect near-blank → fallback to pdfplumber + OCR), extracting the 27MB CSV (2 turns), normalizing to canonical CSVs (3 turns), quality-checking (2 turns), writing manifest (2 turns), returning JSON envelope (1 turn).
- `transversal_modeler` anchored at 45 turns (midrange of 30–60): reading template + 3 normalized CSVs (4 turns), populating P&L with formulas (10 turns), populating Balance Sheet (10 turns), populating Cash Flow (8 turns), populating Valuation with DCF + sensitivity table (8 turns), running validation cells (3 turns), writing Assumptions sheet TODOs (2 turns).
- `bespoke_modeler` anchored at 45 turns (midrange, but weighted toward web_search): industry identification from client name + P&L (3 turns), 10 web_search/web_fetch turns for microfinance benchmarks (Tafi is a MICI-registered microfinance institution — no standard playbook likely exists, so full web-research path activates), populating industry_benchmarks and bespoke_assumptions named ranges (8 turns), resolving Assumptions TODO rows (8 turns), adding bespoke P&L/Balance rows (8 turns), re-running validation (4 turns), writing assumption_notes.md (4 turns).
- `synthesis` anchored at 30 turns (midrange of 20–40): reading model sheets + extracting KPIs via openpyxl (5 turns), computing 4 framing-question diagnostics (4 turns), ranking and selecting insights (3 turns), populating 7 slides via python-pptx (14 turns, ~2 per slide), saving deck + assembling JSON envelope (4 turns).

**Input token accumulation** models context growth across turns. Each turn's input includes: system prompt (constant) + all prior turns (history accumulates) + tool outputs from that turn. Tool outputs vary: read/write acknowledgements are small (~200 tok), skill outputs for PDF/xlsx extraction are large (1,000–5,000 tok), web_search results average ~1,500 tok per call, and the 27MB CSV is never passed whole — pandas/bash extracts a summary view estimated at ~2,000 tok.

For each agent the per-turn average input is computed as:
`(system_prompt + avg_prior_history + avg_tool_output) ≈ system_prompt + (turns/2 × avg_turn_size) + tool_output_avg`

where `avg_turn_size` (assistant message + tool call structure) ≈ 300 tok and `avg_tool_output` is agent-specific.

**Output tokens per turn** are modest: most turns produce a brief tool call or a partial JSON object. Averaged across turns: coordinator ~200, ingestion ~250 (more JSON writing), transversal_modeler ~400 (openpyxl code generation is verbose), bespoke_modeler ~450 (includes inline citations), synthesis ~350 (narrative insight drafting).

## Estimate table

| Agent | Model | Turns | Input tokens (total) | Output tokens (total) | Notes |
|-------|-------|------:|---------------------:|----------------------:|-------|
| coordinator | claude-sonnet-4-6 | ~10 | ~22,000 | ~2,000 | Router only; short turns, no heavy tool output. Sys prompt ~430 tok; avg input/turn ~2,200. |
| ingestion | claude-sonnet-4-6 | ~15 | ~75,000 | ~4,000 | Scanned-PDF fallback chain adds 3 extra turns with large skill outputs (~3,000 tok each). CSV extraction produces a pandas summary ~2,000 tok. Avg input/turn ~5,000. |
| transversal_modeler | claude-opus-4-6 | ~45 | ~270,000 | ~18,000 | openpyxl code blocks are verbose (~400 tok output/turn avg). Tool outputs include sheet previews and formula echoes (~1,200 tok avg). Context grows significantly across 45 turns. Avg input/turn ~6,000. |
| bespoke_modeler | claude-opus-4-6 | ~45 | ~310,000 | ~20,000 | ~10 web_search turns add ~1,500 tok each to input. No standard microfinance playbook for MICI expected — full web-research path. assumption_notes.md generation is verbose. Avg input/turn ~6,900. |
| synthesis | claude-opus-4-6 | ~30 | ~165,000 | ~10,500 | openpyxl extraction passes ~3,000 tok of KPI data into context early; python-pptx code generations average ~450 tok output. Avg input/turn ~5,500. |
| **Total** | | **~145** | **~842,000** | **~54,500** | |

## Assumptions and caveats

- Tool use results (web_search) averaging ~1,500 tokens each. This is conservative for comprehensive microfinance sector searches; actuals could reach 3,000 tok per search if result snippets are long.
- openpyxl code generation is counted as output tokens (~350–450 per turn). If the model generates longer scripts (e.g. iterating 50+ rows of the portfolio CSV), output could be 2× this estimate.
- The 27MB CSV (`Cartera Total TAFI.csv`) is never loaded wholesale into context. ingestion reads it via pandas and passes a summary/schema view (~2,000 tok). If the model needs to inspect specific rows during quality checks, additional read turns could add 5–10 turns to ingestion.
- Context accumulation across 45 turns (transversal_modeler, bespoke_modeler) is the dominant cost driver. A full-context model with no truncation was assumed; if the API applies context windowing, actuals may differ.
- No prompt caching assumed in this baseline. If system prompts are cached (they are static), input tokens for coordinator and ingestion drop by ~60–80% of system-prompt tokens per turn — a potential saving of ~20,000–40,000 tokens total.
- Sonnet used for coordinator and ingestion; Opus used for the three modeling/synthesis agents — consistent with the design spec. Pricing impact is significant: Opus is ~5× more expensive per token than Sonnet at list rates.
- The "blocked_on_client" path (coordinator halts after ingestion returns missing_fields) is not modeled here; that would be a ~25-turn partial run, mostly coordinator + ingestion cost only.
- Numbers are order-of-magnitude estimates accurate to ±30–50%. The first live Tafi run should be instrumented to record actual token usage per session and per agent turn to replace these projections.

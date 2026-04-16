# Per-agent token estimates (one Insignia contract)

_Engineering projection. Input-side components (system prompts, PDF extraction size, CSV summary size) have been measured directly via the Anthropic `count_tokens` API and local pdfplumber/pandas runs on the real Tafi inputs on 2026-04-16. Turn counts and per-turn output tokens remain projections — update with actuals after first live run. Based on the Tafi representative contract (2 input files: `Borrador de EF 2025 - Financiera Tafi - MICI.pdf` — **measured non-scanned**, 39 pages, 1,117 chars/page extracted cleanly via pdfplumber — and one 27MB CSV `Cartera Total TAFI.csv`, 156,309 rows × 24 cols)._

## Measured inputs (2026-04-16)

| Component | Measured tokens |
|---|---:|
| System prompt — coordinator | 721 |
| System prompt — ingestion | 1,207 |
| System prompt — transversal_modeler | 1,199 |
| System prompt — bespoke_modeler | 1,263 |
| System prompt — synthesis | 1,265 |
| **Total system prompts** | **5,655** |
| Tafi PDF full text extraction (pdfplumber, 39 pages) | 15,961 |
| Tafi CSV pandas summary (info + head(10) + describe) | 2,718 |
| Web search result per query (**still estimate, not measured**) | ~1,500 |

**Key revisions vs. pre-measurement projection:**

1. System prompt sizes are ~82% larger than the `words × 1.3` approximation (5,655 measured vs ~3,100 projected). Accumulated across ~145 total turns, this is a modest per-contract input-cost bump.
2. **The Tafi PDF is not scanned** — pdfplumber extracts cleanly. The fallback chain (pymupdf OCR) will not fire on this file. Ingestion turn count adjusts from ~15 down to ~12.
3. PDF extraction is larger than the scanned-OCR estimate assumed: 15,961 tok vs. 3,000 tok. This is input that ingestion holds in context and that flows (in distilled form) to downstream agents via normalized CSVs.
4. Web search per-query size remains a 1,500-tok estimate — not measured, since no live search was run.

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

## Estimate table (revised with measured inputs — 2026-04-16)

| Agent | Model | Turns | Input tokens (total) | Output tokens (total) | Notes |
|-------|-------|------:|---------------------:|----------------------:|-------|
| coordinator | claude-sonnet-4-6 | ~10 | ~25,000 | ~2,000 | Measured sys prompt 721 tok adds +290/turn over prior estimate. Router only; short turns, no heavy tool output. |
| ingestion | claude-sonnet-4-6 | ~12 | ~80,000 | ~3,000 | **Tafi PDF is NOT scanned** — fallback chain not needed, saves ~3 turns vs prior estimate. But measured PDF extraction (15,961 tok) is larger than the previous OCR assumption (3K). Net: similar order of magnitude. Measured sys prompt 1,207 tok. |
| transversal_modeler | claude-opus-4-6 | ~45 | ~295,000 | ~18,000 | Measured sys prompt 1,199 tok adds +559/turn × 45 turns = +25K over prior estimate. openpyxl code blocks verbose. Context grows significantly across 45 turns. |
| bespoke_modeler | claude-opus-4-6 | ~45 | ~336,000 | ~20,000 | Measured sys prompt 1,263 tok adds +573/turn × 45 turns = +26K. ~10 web_search turns still estimated at 1,500 tok each (not measured). No microfinance playbook exists in v1 — full web-research path. |
| synthesis | claude-opus-4-6 | ~30 | ~182,000 | ~10,500 | Measured sys prompt 1,265 tok adds +565/turn × 30 turns = +17K. openpyxl + python-pptx code generation. |
| **Total** | | **~142** | **~918,000** | **~53,500** | Input up ~9% vs prior estimate; output essentially unchanged. |

## Refined cost estimate (2026-04-16, measured inputs)

| Line item | Value |
|---|---:|
| Coordinator tokens (Sonnet, $3/$15 per MTok) | $0.105 |
| Ingestion tokens (Sonnet) | $0.285 |
| Transversal modeler tokens (Opus, $5/$25 per MTok) | $1.925 |
| Bespoke modeler tokens (Opus) | $2.180 |
| Synthesis tokens (Opus) | $1.173 |
| **Tokens subtotal** | **$5.67** |
| Session runtime (~3 hr × $0.08) | $0.24 |
| Web search (~10 queries × $0.01) | $0.10 |
| **Per contract (revised)** | **~$6.01** |

**Annual projection at candidate volumes:**

| Volume | Context | Annual cost |
|---|---|---:|
| 25 | Current baseline (2026) | ~$150 |
| 35 | Cleared queue (near-term) | ~$210 |
| 50 | 2× expansion | ~$300 |
| 75 | Full 3× target | ~$451 |

## Assumptions and caveats

- **Measured:** All five system prompt sizes, the Tafi PDF full-text extraction size, and the Tafi CSV pandas-summary size — via `anthropic.messages.count_tokens` with `claude-sonnet-4-5` as the tokenizer reference and local pdfplumber/pandas runs.
- **Still estimated:** Turn counts per agent, per-turn output token averages, web_search result token size (~1,500 per query), accumulated-history growth across turns, session runtime duration.
- Tool use results (web_search) averaging ~1,500 tokens each. This is conservative for comprehensive microfinance sector searches; actuals could reach 3,000 tok per search if result snippets are long.
- openpyxl code generation counted as output tokens (~350–450 per turn). If the model generates longer scripts (e.g. iterating 50+ rows of the portfolio CSV), output could be 2× this estimate.
- The 27MB CSV is never loaded wholesale into context. Ingestion reads it via pandas and passes a summary view (measured at 2,718 tok). If the model needs to inspect specific rows during quality checks, additional read turns could add 5–10 turns to ingestion.
- Context accumulation across 45 turns (transversal_modeler, bespoke_modeler) is the dominant cost driver. A full-context model with no truncation was assumed.
- **No prompt caching assumed** in this baseline. If system prompts are cached (they are static), at 5-minute TTL the effective input rate drops to $0.30/MTok (Sonnet) or $0.50/MTok (Opus) on cache-hit turns — a realistic saving of ~10–15% on total input cost for agents with 30+ turns (transversal, bespoke, synthesis). Worth enabling pre-launch.
- Sonnet used for coordinator and ingestion; Opus used for the three modeling/synthesis agents — consistent with the design spec. Pricing impact is significant: Opus is ~5× more expensive per token than Sonnet at list rates.
- The "blocked_on_client" path (coordinator halts after ingestion returns missing_fields) is not modeled here; that would be a ~25-turn partial run, mostly coordinator + ingestion cost only.
- Uncertainty band: with measured inputs the projection tightens from ±30–50% (pre-measurement) to roughly **±15–25%**. The residual uncertainty is dominated by turn counts and tool output sizes, which only an actual run will resolve.
- The first live Tafi run should be instrumented to record actual token usage per session and per agent turn, to replace the remaining projected values with measured ones.

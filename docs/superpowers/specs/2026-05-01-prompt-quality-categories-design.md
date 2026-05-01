# Spec: Prompt-quality categories — handoff for next session

> **Origin:** brainstormed at end of 2026-05-01 thread that shipped PRs #5–#12 (eval framework + lint + schema + behavior-auditor pipeline + transversal_modeler scaffold + CLAUDE.md update). The L6 prevention scaffolding closed; this spec defines the next layer.
>
> **Audience:** the next Claude session. Read this top-to-bottom before doing anything; it overrides any contradicting impulse to "just patch v3 of the ingestion prompt."

## Motivation — what this spec exists to fix

Two non-deterministic observers (in-session Claude review + platform "Ask Claude") looked at the same v1 ingestion trace (`runs/2026-04-30T18-40-29Z-poc/smoke/`) and produced parallel, partially-overlapping recommendation lists:

| Source | Issues found | Overlap with the other |
|---|---|---|
| In-session review | 4 (mount path, redundant cp, /tmp persistence, sequential CSV) | 2 of 4 |
| Platform "Ask Claude" | 7 (single-pass extract, page maps, more-parallel, encoding fix, outputs/ path, schema validation, lazy skill load) | 2 of 7 |
| Union, deduped | 8–9 distinct issues | — |
| **Explicit disagreement** | 1: in-session said "skip the cp, keep custom out path"; platform said "drop the custom path entirely, use /mnt/session/outputs/" — **platform was right; v2 has this wrong** | — |

**The lesson is one layer up from the issues themselves.** Patching v2→v3 with the merged list would still be n=1 whack-a-mole. The actual takeaways:

1. **Single-observer review is structurally unreliable.** Two non-det observers on the same trace overlap only ~25–50%.
2. **Issues fall into a small number of categories.** All 8 fit in 4 buckets. New issues from the next contract should mostly fit the same buckets.
3. **The right enforcement layer is repo systems (lint + schema + scorer), not per-prompt edits.** PRs #7–#10 already demonstrated this for some categories; others are uncovered.

## The 4 categories

Permanent vocabulary. Every prompt change going forward references which category it addresses.

| ID | Name | Examples from the v1 trace | Where it should be enforced |
|---|---|---|---|
| **C1** | Contract knowledge gaps | wrong mount path; custom out path vs `/mnt/session/outputs/` | Lint (R001–R003 partial; needs new R007 for outputs/ path) |
| **C2** | State unawareness | PDF re-extraction; CSV re-load; pypdf double-call | Lint (R004 partial) + new runtime token-efficiency metric in scorer |
| **C3** | Missing output guardrails | no schema validation before envelope; encoding flagged but not auto-fixed | Lint (R005/R006 partial; needs R008 schema-validation-step + R009 encoding-attempt-for-LatAm) + schema requirement |
| **C4** | Context hygiene | full skill docs read regardless of need; full PDF read when only structured pages needed; auditor boilerplate consumed ~10K tokens | Hard to lint at edit time; needs runtime measurement (token counts, tool-call counts per output byte) |

## In scope for this work

1. **Spec doc itself** (this file)
2. **CLAUDE.md update** — multi-observer workflow rule:
   > Every v(N)→v(N+1) prompt-version bump requires both Claude-in-session review AND platform Ask Claude on the same trace. Observations merged with disagreements explicit. Single-observer review is rejected as workflow.
3. **Per-category coverage tool** — `lint/category_coverage.py`, modeled after `lint/audit_coverage.py`. Maps each lint rule to its category; reports per-category coverage gaps.
4. **4 new lint rules:**
   - **R007** `output-path-not-auto-captured` (C1) — actor prompt writes outputs to a path other than `/mnt/session/outputs/<contract_id>/`. Severity: warn. Override allowed via in-prompt comment `# lint-allow R007: <reason>` for prompts that intentionally use a custom path.
   - **R008** `missing-schema-validation-step` (C3) — actor prompt declares a JSON envelope referencing file paths but does not include a "validate output schema before returning envelope" step in the Job section. Severity: warn.
   - **R009** `latam-pipeline-no-encoding-attempt` (C3) — actor prompt processes Spanish/LatAm CSV/PDF data (heuristic: prompt mentions Argentina, Brazil, Spanish, ARS, BRL, NIIF, etc.) but doesn't include encoding auto-fix guidance. Severity: warn.
   - **R010** `extraction-without-single-pass-discipline` (C2) — actor prompt extracts large documents but doesn't have explicit "extract once, persist, do not re-extract" guidance. Extends R004's `/tmp/` persistence rule with a stronger structural check.
5. **Runtime efficiency metrics in scorer** — close the C4 gap. Add 3 new score columns under the existing `process` column:
   - `tokens_per_output_byte` (range assertion)
   - `tool_calls_per_output_file` (count_at_most assertion)
   - `thinking_time_seconds` (range assertion)
   Each is computed from the run manifest fields the runner already captures; no new runtime instrumentation needed.
6. **Updated CHANGELOG template** — every prompt-version entry must tag (a) which categories it addresses, (b) which it explicitly does NOT address. Forces the abstraction at edit time. Add the template to `agents/<role>/CHANGELOG.md` as a comment header.
7. **v3 of insignia_ingestion** as the deliverable that proves the framework — the FIRST prompt rewritten to comply with all category-aware rules. v3 also retracts v2's `outputs/` mistake. Once v3 passes lint clean against R001–R010, the framework is proven on real material.

## Explicitly out of scope

- **Building a "C5 — model-internal behaviors" category.** Things like "lazy skill loading" (platform Rec 7) are model-internal — the model would need to know whether it needs the skill before reading the docs. Wrong layer to fix in prompt.
- **Page maps / contract-specific page guidance** (platform Rec 2). Contract-shape-specific; not generalizable; if the next contract has different shape, hardcoded page maps become wrong.
- **More aggressive parallelization rule** (platform Rec 3). v2 already covers parallel writes; further rules are marginal returns for added prompt complexity.
- **Building L1 pipeline smoke tests / L2 specialist evals / L3 auditor self-tests** (the gaps from the L0–L10 audit). Earlier brainstorm; lower priority than category framework.

## Pre-registered prediction

> Once the 4 categories are formalized and the 4 new lint rules ship, the next ingestion contract's failure list (run through both observers) will fit ≥75% in the existing 4 categories.
>
> **If significantly more lands outside the categories** (e.g., 3+ new failure types that don't map), the category taxonomy is wrong and needs revision BEFORE more prompts are written against it. Treat this as a hard halt condition for the framework.

Pre-registered before any next-contract trace is captured, per playbook § 9 (Lin et al. arXiv:2604.25850 decision observability).

## Suggested PR sequence for the next session

1. **PR A: spec + CLAUDE.md update** — land this spec, add the multi-observer workflow rule. Pure docs. (~30 min)
2. **PR B: category_coverage.py + R007 + R008** — first two new lint rules + coverage tool. (~1.5 hr)
3. **PR C: R009 + R010** — remaining lint rules. (~1 hr)
4. **PR D: runtime efficiency score columns** — extend `evals/score.py` with the 3 new metrics + update `expected.json` schema_version. (~2 hr)
5. **PR E: v3 of insignia_ingestion + CHANGELOG template** — first prompt that complies with all category rules; retracts v2's outputs/ mistake. (~1 hr)

Total estimated scope: 1 day of focused work, 5 PRs. Sequential because each PR builds on the previous.

## What this spec does NOT predetermine

- The exact regex / heuristic for each new lint rule. R007–R010 are described above as goals; the implementer makes the call on what string pattern in a prompt counts as evidence (same convention as R001–R006 — see `lint/from_audit.py` for the reasoning).
- Whether v3 should be a new platform agent (`insignia_ingestion_v3`) or an in-place version bump on `insignia_ingestion_v2`. Defer until v3 is ready to deploy. Note the harness pattern (CLAUDE.md `Conventions`): production-resource mutations need explicit action-naming authorization; generic "proceed" won't unblock.

## Honest gaps in this spec itself

- **v2 retraction is implied but not yet documented.** Once PR E lands v3, `agents/insignia_ingestion/CHANGELOG.md` should add a v2 retraction note: the `outputs/` decision was wrong; do not deploy v2.
- **C4 (context hygiene) only partially closes.** Runtime metrics give visibility but no enforcement. A prompt that wastes tokens still passes lint; it just shows up red in the scorer. Hard enforcement at edit time would require static analysis of which skill files a prompt references vs declares, which is out of scope here.
- **Multi-observer rule is unenforceable.** It's a workflow standard in CLAUDE.md, not a CI gate. A determined contributor could skip it. Acceptable trade-off — cultural norm beats hard gate for a 1-person repo.
- **n=1 caveat unchanged.** Even with the framework + 5 PRs, we still have one trace to validate against. The pre-registered prediction is the only honest check; if it fails, the framework needs revision.

## Files this spec touches (reference for the next session)

- **New:** `lint/category_coverage.py`
- **Modified:** `lint/prompt_lint.py` (4 new rules), `lint/schema.md` (new required clauses), `lint/README.md` (category vocabulary + new tools), `evals/score.py` (3 new score-column handlers), `evals/ingestion/tafi_2025/expected.json` (schema_version bump + new metric assertions), `evals/MANIFEST_SCHEMA.md` (new manifest fields if needed for runtime metrics), `agents/insignia_ingestion/CHANGELOG.md` (v3 entry + v2 retraction + new template), `agents/insignia_ingestion/v3_system_prompt.md` (new), `.claude/CLAUDE.md` (multi-observer rule in Conventions section)
- **Frozen, do not edit:** `agents/insignia_ingestion/v1_system_prompt.md` (paired-McNemar baseline), `runs/` (historical capture)

## Suggested first action in the new session

```bash
git checkout main && git pull
git checkout -b feat/prompt-quality-categories-spec
# Read this spec in full
# Then start PR A: this spec already exists; just add the multi-observer rule
# to .claude/CLAUDE.md Conventions section, commit, push, open PR.
```

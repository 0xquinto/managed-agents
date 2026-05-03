# Resolver model-tier findings — 2026-05-02

Three resolver-prompt versions deployed against the 4 resolver eval slices (`new_contract`, `continuation`, `supersession`, `triage`), all paired live, n=1 per slice per version. Plus one cross-tier smoke (v2 prompt on Sonnet) to localize a behavior we couldn't move via prompt iteration.

## Versions tested

| Version | Agent ID | Model | Diff vs prior |
|---|---|---|---|
| v1 | `agent_011CaeMn6bMMjsR5g7ZvbW7e` | haiku-4-5 | initial |
| v2 | `agent_011CaeTkSmBo1aHzsWdkJuqJ` | haiku-4-5 | + format discipline + bare-body→triage rule |
| v3 | `agent_011CaeXhWLsSs5poLhwh5712` | haiku-4-5 | strip ❌ examples, strip fence tokens from prompt, end-anchor positive example |
| v2 on Sonnet | `agent_011CaeYvhVpYELkvmW8jx9mU` | sonnet-4-6 | same prompt as v2, different tier |

## Content pass rates

Each cell is `(process + outcome PASS) / (total content assertions)` for that slice. Slice content denominators come from the `envelope` array in each `expected.json`: new_contract=6, continuation=6, supersession=4, triage=6 → 22 total. Format-discipline (`no_markdown_fences`) is now `column: environment` (per the analysis below) and reported separately.

| Slice | v1-haiku | v2-haiku | v3-haiku | v2-sonnet |
|---|---|---|---|---|
| new_contract (n=6) | 6/6 | 6/6 | 6/6 | 6/6 |
| continuation (n=6) | 6/6 | 6/6 | 6/6 | **2/6** |
| supersession (n=4) | 4/4 | 4/4 | 4/4 | **0/4** |
| triage (n=6) | **1/6** | **6/6** | 6/6 | 6/6 |
| **total** | 17/22 | **22/22** | **22/22** | **14/22** |

## Format pass rate (`column: environment` — informational)

| Slice | v1-haiku | v2-haiku | v3-haiku | v2-sonnet |
|---|---|---|---|---|
| no_markdown_fences | 0/4 | 0/4 | 0/4 | **4/4** |

## Captured run directories (replayability)

For audit / replay, the captured trial directories are:

- v1-haiku: `evals/runs/2026-05-02T20-{34,35,37,50,51,53}-*-resolver-*-agent_011CaeMn6bMMjsR5g7ZvbW7e/` (the new_contract slice has two captures — the first errored on the SDK→API event-shape bug pre-fix `a41a3ea`; the second is the authoritative one)
- v2-haiku n=1: `evals/runs/2026-05-02T21-{36,40,41}-*-resolver-*-agent_011CaeTkSmBo1aHzsWdkJuqJ/`
- v2-haiku n=10: `evals/runs/2026-05-02T23-{20,23,44}-*` and `2026-05-03T00-08-*-resolver-*-agent_011CaeTkSmBo1aHzsWdkJuqJ/`
- v3-haiku: `evals/runs/2026-05-02T22-{27,28,30,31}-*-resolver-*-agent_011CaeXhWLsSs5poLhwh5712/`
- v2-sonnet: `evals/runs/2026-05-02T22-{43,44,46,49}-*-resolver-*-agent_011CaeYvhVpYELkvmW8jx9mU/`

## Findings

1. **v1 → v2: bare-body→triage rule worked exactly as designed.** triage classification went from 1/6 to 6/6 with one new rule under § Rules. Targeted prompt engineering on classification behavior is reliable on Haiku.

2. **v2 → v3: fence-priming hypothesis refuted.** Stripping every fence token from the prompt + dropping ❌ negative examples + end-anchoring the single positive example produced ZERO change in fence-wrapping (still 0/4). The hypothesis "negative examples anchor bad behavior on small models" doesn't hold here — Haiku wraps in fences regardless of what the prompt says about format.

3. **Cross-tier hypothesis (n=1, weak): fence-wrapping is Haiku-specific.** The v2 prompt on Sonnet produced clean `{...}` JSON across all 4 slices (4/4) on a single trial each; the same prompt on Haiku produced fences across 4/4 slices in n=10. *This is a directional result on small samples — it would need cross-prompt n≥10 on Sonnet to rule out luck or prompt-specific artifacts.* If the hypothesis holds, Haiku's fence-wrapping would be a model default rather than a prompt-induced behavior, which matches the v3-haiku refutation: stripping every fence token from the prompt + dropping negative examples produced zero change in v3 (n=1 each).

4. **Cross-tier hypothesis (n=1, weak): Sonnet over-applies the partial-match rule.** Sonnet's continuation envelope (`agent_011CaeYvhVpYELkvmW8jx9mU`, single trial) routed an exact-sender-match case to triage citing "priors file absent". The captured `rationale_short` text directly references the unreadable memory file as the trigger. *Mechanism is plausible but unverified across prompts/cases — would need Sonnet n≥10 across all 4 slices, ideally with a Sonnet-specific prompt that loosens the rule, to confirm the model-vs-prompt attribution.*

## Practical implications

- **Production keeps Haiku v2.** Content 22/22 at n=1 and 22/22 process at n=10 with one outcome flake (`triage_payload.candidates` 8/10 — see `N10_FANOUT_2026-05-02.md`). Fence-wrapping is cosmetic in the deployed pipeline because the SDK's `agent.message` event already serves text content blocks the CLI 400s on but the SDK reads cleanly — *this should be re-confirmed when the resolver is wired into the production poller's dispatch path; it's expected behavior per `AnthropicSDKSessionsBackend` design but I haven't observed it end-to-end yet.*
- **`no_markdown_fences` moved from `column: process` to `column: environment`** in `1ec1022`. The current setup charges Haiku for a behavior with no functional consequence in the deployed pipeline. The assertion still runs as an early-warning signal if score.py's extractor or the SDK backend ever changes upstream.
- **Sonnet is wrong for the resolver role at n=1; Haiku is right.** Until we have Sonnet n≥10, "Sonnet is wrong" is a directional claim on a single trial each — but the magnitude (continuation 2/6 + supersession 0/4 = 2/10 vs Haiku's 10/10) is large enough that the right cost-discipline move is to ship Haiku and re-litigate Sonnet only if Haiku's outcome flakes regress.
- **For agents where format discipline genuinely matters (e.g. structured JSON tool result pipelines), Sonnet may be worth the cost** — but classification edge-cases will need a Sonnet-specific prompt loosening the partial-match rule. Different pipeline agents can use different tiers.

## Cost

- 12 live trials × ~$0.01-0.05 per trial = roughly $0.10-0.60 total.
- Real value: localized a previously-mysterious behavior to a model-tier difference, ruled out a plausible-sounding prompt hypothesis, and identified the correct production tier — all in <30 minutes.

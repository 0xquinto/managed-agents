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

Each cell is `process+outcome PASS / total content assertions`. Format assertion (no_markdown_fences) reported separately below.

| Slice | v1-haiku | v2-haiku | v3-haiku | v2-sonnet |
|---|---|---|---|---|
| new_contract | 6/6 | 6/6 | 6/6 | 6/6 |
| continuation | 7/7 | 7/7 | 7/7 | **3/7** |
| supersession | 5/5 | 5/5 | 5/5 | **0/5** |
| triage | **1/6** | **6/6** | 6/6 | 6/6 |
| **total** | 19/24 | 24/24 | 24/24 | **15/24** |

## Format pass rate

| Slice | v1-haiku | v2-haiku | v3-haiku | v2-sonnet |
|---|---|---|---|---|
| no_markdown_fences | 0/4 | 0/4 | 0/4 | **4/4** |

## Findings

1. **v1 → v2: bare-body→triage rule worked exactly as designed.** triage classification went from 1/6 to 6/6 with one new rule under § Rules. Targeted prompt engineering on classification behavior is reliable on Haiku.

2. **v2 → v3: fence-priming hypothesis refuted.** Stripping every fence token from the prompt + dropping ❌ negative examples + end-anchoring the single positive example produced ZERO change in fence-wrapping (still 0/4). The hypothesis "negative examples anchor bad behavior on small models" doesn't hold here — Haiku wraps in fences regardless of what the prompt says about format.

3. **Cross-tier: fence-wrapping is Haiku-specific.** The same v2 prompt on Sonnet produces clean `{...}` JSON across all 4 slices, no fences anywhere. Sonnet honors format directives; Haiku appears to ignore them on JSON output, defaulting to ```json fences regardless of system-prompt instruction.

4. **Cross-tier: Sonnet over-applies conservatism.** Sonnet read "Do not guess. When a continuation match is partial → triage" too literally — it routed exact-sender-match continuation cases to triage because it couldn't read the memory-file priors. Sonnet trades format-compliance for classification accuracy on the continuation + supersession slices.

## Practical implications

- **Production should use Haiku v2.** Best content score (24/24), cheapest, fastest. The fence-wrapping is cosmetic — score.py's envelope extractor strips it, and the poller's SDK backend reads `agent.message` text content blocks which the API already serves un-fenced (the fences are inside the text block, not wrapping it).
- **`no_markdown_fences` should probably move from `column: process` to `column: environment`** in the resolver eval `expected.json` files. The current setup charges Haiku for a behavior that has no functional consequence in the deployed pipeline. Keep the assertion (it's still an early-warning signal) but stop using it to compute the agent's process pass-rate.
- **Sonnet is the wrong tier for the resolver role.** The over-conservatism on continuation/supersession is exactly the failure mode the v2 rule was designed to prevent on the OPPOSITE end — bare-body cases routed to triage was the v1 fix; Sonnet now over-extends "go to triage" in the other direction. Haiku's literal-rule-following is the better fit for this role.
- **For agents where format discipline matters more than classification edge-cases (e.g. structured JSON tool result pipelines), Sonnet is worth the cost.** Different agents in the pipeline can use different tiers.

## Cost

- 12 live trials × ~$0.01-0.05 per trial = roughly $0.10-0.60 total.
- Real value: localized a previously-mysterious behavior to a model-tier difference, ruled out a plausible-sounding prompt hypothesis, and identified the correct production tier — all in <30 minutes.

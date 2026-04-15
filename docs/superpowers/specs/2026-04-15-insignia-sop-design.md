# Insignia SOP — Design Spec

**Status:** Draft, pending review
**Date:** 2026-04-15
**Owner:** Diego

## Purpose

Produce a pre-signing SOP document that Insignia's Business Owner can read end-to-end and walk away understanding (a) exactly how the automated financial-modeling pipeline works, (b) what surrounds the work — security, determinism, quality, oversight, cost — and (c) what engaging us would look like in practice. The SOP complements the existing AS-IS diagnostic (`docs/contracts/Insignia/diagnostics/insignia_diagnostics.md`) and serves as the technical+operational annex to the commercial proposal.

## Audience

**Primary — and only.** The Business Owner at Insignia. Non-technical. Financial-consulting background. Skeptical of "AI magic" and wants to understand how the work actually happens before signing.

Every design choice below flows from this: no jargon, no API-speak, every technical concept translated into a human analogy.

## Deliverable

- **Source format** — Markdown, single file, authored in English
- **Delivery format** — Translated to Spanish, exported to PDF for sending/printing
- **Length target** — 20–25 pages (substantive but scannable; exhaustive depth lives in appendix)
- **Visual assets** — one team-flow diagram (mermaid or equivalent), one per-contract journey timeline, agent cards laid out as consistent two-page spreads

## Source of truth

The SOP must stay faithful to the v1 run design in `runs/latest/design/` and the diagnostic in `docs/contracts/Insignia/diagnostics/insignia_diagnostics.md`. Any conflict between this spec and those documents resolves in favor of the run design (which has already been validated).

## Structure

### Part I — Opening (cross-cutting, ~8–10 pages)

1. **Executive summary** (1 page) — what the pipeline does in one paragraph; the capacity shift (5–12 days → 3 days; 20 → 60+ contracts/year); one-line promise of each agent; a single takeaway sentence.

2. **How the team works together** (1–2 pages) — diagram of the coordinator + 4 specialists; explanation of the sequential flow (ingestion → transversal → bespoke → synthesis); the "one contract per run" invariant.

3. **Where it runs** (1 page) — Anthropic-managed cloud; each contract runs in its own isolated container; no data persists on our infrastructure between runs; container lifecycle explained in human terms.

4. **Security & confidentiality** (1–2 pages) — how client files enter, where they're stored during a run, what's purged after, what's logged vs. what's ephemeral; credential handling (framed as "we never see your Microsoft or bank credentials" in v2); the CLI-as-auth-boundary principle translated into plain language; data residency posture.

5. **Determinism & reproducibility** (1 page) — explicit table:
   | Agent | Determinism | What this means for you |
   |-------|-------------|-------------------------|
   | ingestion | Near-deterministic | Same file → same normalized data |
   | transversal_modeler | Deterministic math, judgment on assumption fill-ins | Same inputs → same model skeleton |
   | bespoke_modeler | Judgment within guardrails | Two runs may pick different valid sources; both cited |
   | synthesis | Judgment (this is the point) | The 3–5 insights may differ; all are number-backed |

6. **Quality controls** (1 page) — Excel self-validation cells (balance check, cash tie-out); missing-field halts (pipeline refuses to model bad data); every numeric assumption carries a source citation; formula-only computed cells (no hard-coded subtotals).

7. **Human oversight** (1 page) — three moments where the Business Owner is in the loop: (a) dropping the input files, (b) receiving a "blocked on client" envelope when data gaps are detected, (c) final review of the deck and model before hand-off to their client. No silent auto-sends.

8. **Audit trail** (0.5–1 page) — every input, intermediate, and output is file-addressable; assumption_notes.md lists every injected assumption with source; classification.json records how ingestion interpreted each input file.

9. **Running cost estimate** (1–2 pages) — itemized table: per-agent token estimate × Anthropic rate; platform costs (environment runtime, file storage); per-contract total; annual projection at 60 contracts/year; methodology note so the Business Owner can recompute if rates change; disclaimer that Managed Agents is beta and rates may move. **Rate values pulled via Exa research at write time — not cached here.**

10. **v1 limits** (1 page) — honest list of what the pipeline does NOT do yet: no MS Teams/OneDrive auto-intake (manual file drop), no PowerBI refresh, no cross-contract memory, no batch mode (one contract at a time), no outcome-validation rubrics. Frames limits as "here's what v2 adds" rather than deficiency.

### Part II — Agent chapters (~10–12 pages, ~2 pages each)

Five chapters, one per agent: `coordinator`, `ingestion`, `transversal_modeler`, `bespoke_modeler`, `synthesis`. Same card structure, in this order:

- **Role** — one sentence + a human analogy
  - coordinator → "the project manager"
  - ingestion → "the intake clerk"
  - transversal_modeler → "the standard modeler"
  - bespoke_modeler → "the industry specialist"
  - synthesis → "the strategist"
- **What it reads / what it delivers** — concrete inputs and outputs in client terms (not file paths)
- **How it thinks** — plain-language description of the agent's decision logic; what it decides vs. what it looks up
- **Tools & skills** — in client-friendly names (e.g. "reads Excel workbooks" not "xlsx skill")
- **Why this model** — one line (Sonnet for routing/intake; Opus for modeling and strategy)
- **Determinism profile** — inherited from the table in §5, agent-specific commentary
- **Security posture** — what data this agent touches; whether it reaches the internet (bespoke_modeler and synthesis do; others don't); what it logs
- **Failure modes** — what can go wrong (e.g., scanned-only PDF on ingestion → pipeline halts with missing-field flag), what happens when it does
- **What you can verify** — the artifacts the Business Owner can open after the run (manifest.json, validation cells, assumption_notes.md, deck speaker notes)

### Part III — Closing (~2–3 pages)

11. **Your workflow as the Business Owner** (0.5 page) — three steps: drop files in the shared folder; receive either a "blocked" envelope or the finished deliverables; review and forward to your client.

12. **What we need from you** (0.5 page) — input file expectations (formats, naming, completeness); turnaround commitments on clarification loops; sign-off at delivery.

13. **v2 roadmap** (1–2 pages) — expanded, each with a one-paragraph description and the pain it eliminates:
    - MS Teams / OneDrive automatic intake
    - PowerBI dashboard refresh from synthesis output
    - Industry playbook library (reduces web-research dependency)
    - Cross-contract memory (pipeline learns from past clients in same sector)
    - Multi-contract batch mode
    - Outcome validation (rubric-graded quality checks before hand-off)

### Appendix — Technical reference (~2–3 pages)

- Agent name, model ID, tool list, skill list, mcp server list (empty for v1, populated in v2)
- File-path conventions (`/mnt/session/input/`, `/mnt/session/out/`, `/mnt/session/templates/`, `/mnt/session/playbooks/`)
- Environment package list
- Links to Anthropic Managed Agents documentation

Placed at the end so non-technical readers can skip it. Present for anyone (e.g. Jose Rogelio, if shared internally later) who wants exact technical grounding.

## Voice and tone

- **Plain language.** Every technical concept has a human analogy. No "openpyxl", no "mcp_servers", no "tool_use blocks." When exact technical terms are needed, they go in the appendix.
- **Confident but honest.** Limits are explicit, not hidden. Failure modes are described, not implied.
- **Second person.** "You drop the files." "You receive the envelope." "You verify the model." The Business Owner is the protagonist.
- **Short paragraphs, short sentences.** This will be read on a laptop, maybe skimmed.
- **Financial consulting register.** The reader is a finance professional. Use their vocabulary for P&L, DCF, WACC, comparables. Don't over-explain those; do over-explain AI concepts.

## Translation handoff

- Draft in English first. Review and approve.
- Translate to Spanish (LatAm register; "usted" not "tú" given the professional context).
- Translation can be done by LLM pass (GPT/Claude) with a glossary for financial+AI terms; human review before delivery.
- PDF export after Spanish sign-off.

## Open questions

None blocking. The running-cost estimate requires Exa research at write time to pull live Anthropic rates (Opus and Sonnet per-million-token input/output; environment and file-storage line items if published). Flagged in §9 of the structure.

## Scope boundaries

- **In scope:** the SOP document itself (content, structure, voice, visuals).
- **Out of scope:** commercial terms (our fees), contract/SOW legal language, Insignia-side internal change management, the actual Spanish translation (covered as a handoff step, not produced in this plan).

## Success criteria

The Business Owner finishes reading the SOP and can:
1. Describe the pipeline's flow in their own words
2. Explain to a partner what each of the 5 agents does
3. Point to the specific pain from the diagnostic that each agent eliminates
4. State the running cost range per contract and per year
5. Name three things in v2 they're looking forward to
6. Articulate one limit of v1 honestly

If the document achieves this without ever being referred to as "the AI thing," it's successful.

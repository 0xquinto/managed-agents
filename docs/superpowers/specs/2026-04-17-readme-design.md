# README Design — Managed Agent Orchestrator

**Date:** 2026-04-17
**Target file:** `/Users/diego/Dev/managed_agents/README.md`
**Purpose:** First-time-visitor orientation for the repo. Hybrid: hooks portfolio reviewers at the top, supports developers who want to run the pipeline below.

## Audience & framing

Two audiences, ordered:

1. **Reviewer (primary):** someone evaluating the project as a showcase — recruiter, prospective collaborator, or engineer curious about the architecture. Lands on GitHub, skims for 60 seconds, decides whether to dig in.
2. **Developer (secondary):** someone who actually wants to run the pipeline against their own Anthropic account.

The README must hook the reviewer in the first screen, then hand off smoothly to usage content for the developer.

## Tone

Terse, technical, honest. No marketing voice. No emojis unless a diagram calls for one. Match the voice of `project-story.md` and `.claude/CLAUDE.md` — spare, factual, opinionated where useful.

## Length target

500–700 lines. Medium depth: reviewer-relevant context lives inline; agent-file-level detail is linked out.

## Structure

Ten sections, in order:

### 1. Title + tagline + problem statement

- H1: `Managed Agent Orchestrator`
- Subtitle italic: `A terminal pipeline for designing, provisioning, and smoke-testing Claude Managed Agents.`
- One-paragraph problem statement. Draft:
  > Provisioning a Claude Managed Agent by hand means coordinating ~10 API domains — agents, environments, sessions, events, tools, files, skills, memory, MCP servers, and vaults. This repo is a Claude Code agent pipeline that interviews you, designs the config, provisions it in dependency order after your approval, and smoke-tests it. The Anthropic API key never enters the agent context.

Length: ~5 lines including whitespace.

### 2. Demo transcript

A single fenced code block styled as a real terminal session. Shows the end-to-end happy path, trimmed aggressively. Phases to cover in order:

1. User input: one-sentence request (e.g., "I want an agent that triages GitHub issues and posts a triage comment.")
2. lead-0 asks 2–3 clarifying questions (one at a time, user replies inline)
3. lead-0 presents the proposed design (agent name, model, skills, MCP servers, tools — as a short block)
4. Approval gate (user types `approve`)
5. Provisioning log (elided with `...` — show the order: files → vaults → skills → agents → environments → sessions)
6. Smoke test output (one input event, one outcome, PASS)
7. Final line: `runs/latest/ready.md` pointer

Target length: ~40 lines inside the code block. If it grows past 60, wrap in a `<details>` block with the first 12 lines inline.

The transcript is illustrative, not captured verbatim from a real session — but every line must be plausible given the actual lead-0 prompt and specialist outputs. No fake CLI flags, no invented commands.

### 3. How it works

~150 words of prose plus one ASCII diagram.

Prose covers:
- The 11-agent shape: 1 Opus lead-0 (routing-table only) + 10 Sonnet domain specialists (full API reference each) + 1 research-expert (Exa).
- lead-0 is the only agent that spawns subagents. Specialists return 1–2 sentence summaries; verbose output goes to `runs/$RUN_ID/`.
- Three callouts as short bold-lead paragraphs:
  - **Routing table, not encyclopedia.** lead-0 stays context-light so multi-turn design dialogues don't drown in API reference.
  - **CLI-as-auth-boundary.** The `ant` CLI is the only thing that reads `$ANTHROPIC_API_KEY`. Agents never see it.
  - **Summary-only returns.** Specialists write verbose output to the run directory, return 1–2 sentences to lead-0.

ASCII diagram: lead-0 at the top, 11 specialists fanned out below, with a side box showing `$RUN_DIR/` as the artifact sink. Reuse the credential-flow diagram from `.claude/CLAUDE.md` inline in the CLI-as-auth-boundary callout.

### 4. The 6 orchestration skills

A table with three columns:

| Skill | Pattern | Example |
|---|---|---|
| `reactive-pipeline` | Event → Agent → Artifact → Delivery | Issue-to-PR fixer |
| `evaluator` | Artifact → Criteria Check → Feedback | Code reviewer / quality gate |
| `transformer` | Input → Systematic Modification → Output | Codebase migrator |
| `researcher` | Question → Gathering → Synthesis → Report | Competitor monitor |
| `operator` | System A + B → Extract → Reconcile → Act | Procurement reconciler |
| `team-coordinator` | Task → Decompose → Parallel → Reassemble | Plan-build-review team |

Each skill name links to `.claude/skills/<skill>/SKILL.md`. Lead-in sentence above the table:
> Six abstract orchestration patterns, each usable as a slash command (`/reactive-pipeline`, `/evaluator`, etc.). Each skill wraps the right subset of specialists for its pattern.

### 5. Quickstart

~20 lines. Four subsections:

**Prerequisites**
- Claude Code CLI installed
- `ant` CLI installed (the implementation plan must look up the current official install command; if it isn't discoverable, link to the Anthropic install docs rather than hardcoding a command)
- `ANTHROPIC_API_KEY` exported

**Run**
```
git clone <repo-url>
cd managed_agents
claude
```
Then talk to lead-0: describe what you want, or invoke a skill with `/reactive-pipeline`, `/evaluator`, etc.

**Phases (one line each)**
0. Readiness check — 1. Design dialogue — 2. Approval gate — 3. Provisioning — 4. Smoke test — 5. Summary

**Output**
All artifacts land under `runs/$RUN_ID/`. The `runs/latest` symlink points to the most recent run.

### 6. Run directory layout

~10 lines, fenced `tree`-style block. Structure:

```
runs/
  2026-04-17T14-23-05Z/
    design.md          # approved design from Phase 2
    provision.log      # Phase 3 CLI output
    smoke.md           # Phase 4 test results
    ready.md           # final summary, IDs, next steps
  latest -> 2026-04-17T14-23-05Z
```

One-line caption: "Every session gets an ISO-8601-timestamped directory. Nothing is written to `runs/` root."

### 7. Design rationale

Four short bullets, ~100 words total. Each bullet: bold lede + 1–2 sentences.

- **Routing table, not encyclopedia.** lead-0 carries only a dispatch table. API reference lives in the specialist that owns it. Keeps multi-turn design dialogues cheap and coherent.
- **CLI-as-auth-boundary.** Whitelisting `ant beta:*` prefixes in `settings.json` prevents agents from constructing raw curl calls with embedded credentials. The API key flows environment → `ant` → API, invisible to the agent layer.
- **Abstract over concrete.** Six orchestration skills, not sixty recipes. `reactive-pipeline` serves issue-to-PR, support responder, alert fixer, and CI fixer — all with different MCP configs.
- **Research before building.** Each feature gets a go/no-go research pass before any code. Two of five proposed features were correctly rejected (multi-turn sessions, persistent registry) before implementation.

Source: distilled from `project-story.md` "Lessons Learned" — not copy-pasted, reworded for README voice.

### 8. Repo map

Annotated tree, ~15 lines:

```
.claude/
  agents/            # 11 system prompts (lead-0 + 10 specialists + research-expert)
  skills/            # 6 orchestration skill bundles
  CLAUDE.md          # project contract: invariants, credential handling
  settings.json      # Bash/tool permissions (ant beta:* whitelist)
docs/
  api-reference/     # Anthropic API docs snapshot used by specialists
  research/          # success cases + per-pattern research
  superpowers/specs/ # design specs for this repo's own work
runs/                # session artifacts (gitignored)
project-story.md     # narrative arc of the build
README.md            # you are here
LICENSE              # MIT
```

### 9. Learn more

Bulleted links:
- [`project-story.md`](./project-story.md) — the build narrative
- [`.claude/CLAUDE.md`](./.claude/CLAUDE.md) — invariants & credential contract
- [`docs/research/managed-agents-success-cases.md`](./docs/research/managed-agents-success-cases.md) — 10+ production patterns studied
- Per-skill READMEs — linked from the skills table above
- Per-agent prompts under [`.claude/agents/`](./.claude/agents/)

### 10. License

One line: `MIT — see [LICENSE](./LICENSE).`

Plus a new `LICENSE` file at repo root containing standard MIT text with year `2026` and copyright holder matching the repo owner. The implementation plan should confirm the holder name (`0xQuinto` per git config, or whatever the user prefers).

## Explicitly out of scope

- "Project status" / roadmap section — dropped per user.
- Badges (build, version, etc.) — no CI yet, not useful.
- Contributing guide — not a collaboration project right now.
- Screenshots / GIFs — terminal transcript is enough; GIF adds weight without clarity.
- v2 plans (`lead-0-v2-patterns-design.md`) — still in flux, don't pre-announce.

## Validation criteria

The finished README must:

1. Render correctly on GitHub (no broken links, valid markdown).
2. Fit the first screen (demo + tagline) on a standard laptop browser at default zoom — demo fully visible above the fold on 1080p.
3. Every `ant` command in the transcript must be a real command from one of the specialist `.md` files. No invented flags.
4. Every link must resolve to a file that exists at the path given.
5. The credential-flow diagram must match the one in `.claude/CLAUDE.md` exactly (reuse, don't redraw).
6. No emoji unless the user adds them post-review.

## Files touched

- `README.md` — create
- `LICENSE` — create (MIT)
- No other files modified.

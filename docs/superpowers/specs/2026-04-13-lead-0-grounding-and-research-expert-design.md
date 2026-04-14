# Design: lead-0 grounding behavior + research-expert specialist

**Date:** 2026-04-13
**Status:** Approved for planning

## Problem

First pipeline run retrospective surfaced two related issues:

1. **Unverified schemas in `agent-specs.json`.** During Phase 1 design dialogue, `lead-0` drafted spec sections (custom tools, skill structures, environment YAML, vault specs, `callable_agents` wiring) against imagined API shapes. Domain specialists that own each API were idle during design and only engaged during Phase 3 provisioning, where schema mismatches surface too late.
2. **`tools-expert` overloaded as Exa research proxy.** Commit `d33e82b` added Exa MCP tools to `tools-expert` to unblock external pattern research (scorecard design, financial modeling, compliance frameworks, synthesis patterns, evaluator rubrics, env recommendations, smoke-test prompts). Result: `tools-expert`'s real domain (agent tool configuration) is diluted, and there is no dedicated home for web research — including structured output, bibliography tracking, and query dedup.

Both issues erode the trust signal of Phase 2's approval gate: the user currently approves a narrative markdown table rather than a spec validated against live API schemas.

## Goals

- `agent-specs.json` contains only fields verified against the owning specialist's API reference docs.
- Phase 2 approval is backed by a validation report ("N/M fields verified"), not narrative trust.
- External web research has a dedicated owner with consistent output format.
- `tools-expert` returns to its original scope (agent tool configuration only).
- Parallel dispatch of independent specialist calls becomes the explicit default, not an occasional optimization.

## Non-goals

- Live API dry-run (`ant ... --dry-run`) validation. Phase 2 uses schema-only checks against specialist-held reference docs. Live dry-run and cross-reference validation may be added later if schema-only proves insufficient.
- Changes to Phases 0, 3, 4, 5. Only Phase 1 and Phase 2 change.
- New specialists beyond `research-expert`.

## Design

### 1. Phase 1 — Proactive grounding (Option A)

When a topic-guide step touches a specialist's domain, `lead-0` dispatches that specialist **before framing detailed follow-up questions to the user**, so the question uses verified field names.

**Grounding matrix:**

| Topic guide step | Grounding dispatch |
|---|---|
| 6–7 Tools / permission policies | `tools-expert` + `agents-expert` |
| 8 MCP servers | `mcp-vaults-expert` |
| 9 Skills | `skills-expert` |
| 12 Environment | `environments-expert` |
| 13 Resources | `files-expert` + `environments-expert` (repo auth patterns) |
| 15 Vaults | `mcp-vaults-expert` |
| 17 Persistent data | `files-expert` (mounts) or `memory-expert` (memory stores) |
| Team wiring step | `multiagent-expert` |

Trivial topics (name, purpose, model choice, create-or-update, runtime identity) skip grounding.

**Mechanics:**

- `lead-0` creates a `Ground: <domain> schema` task immediately before the related design task.
- The grounding task is invisible to the user — no approval gate, not rendered to the user, completes when the specialist returns the verified shape.
- The grounding task is NOT subject to the "one pending/in_progress design task" invariant — grounding tasks and design tasks are separate task categories. Concretely: the invariant is rescoped to read "At most one task with `subject` starting `Design:` may be pending or in_progress at a time." Grounding tasks (`subject` starting `Ground:`) are not counted.
- Grounding tasks should be marked `completed` before the corresponding `Design:` task is created.

**Parallel dispatch:** when multiple upcoming topics need independent grounding (e.g., tools AND skills), `lead-0` may pre-ground them in a single message with multiple Agent tool calls. Sequential grounding is only used when a later topic's grounding depends on answers from an earlier topic.

### 2. Phase 2 — Schema-only dry-run validation (Option C)

Phase 2 becomes a two-part gate.

**Part A — Validation dispatch (parallel).**
`lead-0` dispatches every relevant specialist in a single message with the full draft `agent-specs.json`. Each specialist:

1. Reads only its own domain's sections of the spec.
2. Validates each field against its API reference docs.
3. Writes a detailed report to `$RUN_DIR/validation/<domain>.md`.
4. Returns a structured summary to `lead-0` with shape:
   ```
   { domain, fields_total, fields_verified, warnings: [...], errors: [...] }
   ```
   Warnings and errors each include `{ path, field, issue }`.

The 1-2 sentence prose summary is returned in addition to the structured summary (existing convention).

**Part B — User-facing report.**
`lead-0` renders a composite report:

```
Spec validation: 47/47 fields verified against live API schemas
 ✓ agents (12/12)
 ✓ environments (8/8)
 ⚠ vaults (6/7) — 1 warning: rotation_policy field unsupported (will be ignored)
 ✗ multiagent (3/4) — 1 error: callable_agents[1].dispatch_mode "async" invalid; use "background"

Human summary:
<existing markdown table of spec contents>

Approve, or request changes?
```

**Blocking rule:** if any specialist reports `errors > 0`, `lead-0` fixes the spec inline — re-grounds and redrafts the offending fields — and re-runs validation. The user is only shown clean or warning-only reports. If validation fails twice on the same field, escalate to the user with both the specialist's error and the current spec value; do not silently loop.

**Updates (existing agent).** Validation includes a diff summary. `lead-0` dispatches `agents-expert` with the current version (fetched from the API) alongside the proposed changes. The validation report adds a "N fields changed" line above the per-domain rollup.

### 3. `research-expert` specialist (narrow)

New agent at `.claude/agents/research-expert.md`.

**Role.** External research. Queries the web and returns structured findings with source, date, and confidence label.

**Toolset.** `mcp__exa__web_search_exa`, `mcp__exa__web_search_advanced_exa`, `mcp__exa__crawling_exa`, `mcp__exa__get_code_context_exa`, `Read`, `Write`.

**Output contract.**

- Full findings written to `$RUN_DIR/research/<topic>.md`. Each finding is `{ claim, source_url, date_accessed, confidence }` where `confidence ∈ {verified, likely, speculative}`.
- Each dispatch appends one-line entries to `$RUN_DIR/research/bibliography.md` (format: `YYYY-MM-DD | <topic> | <url>`), shared across dispatches within a run.
- Returns 1-2 sentence summary to `lead-0` as usual.

**Dedup rule.** Before issuing a new Exa query, `research-expert` reads `$RUN_DIR/research/bibliography.md`. If the same query was issued this run, it references the existing findings instead of re-querying.

**Scope boundary (explicit in prompt).** `research-expert` does NOT answer Anthropic API schema questions — those belong to the domain specialists. If given an API-schema question, it refuses and points `lead-0` to the correct specialist.

### 4. Changes to existing files

**`.claude/agents/tools-expert.md`** — remove Exa tools from the `tools` line (restore scope to agent tool configuration only). Remove any Exa-specific guidance added in commit `d33e82b` and preceding related commits. Retain the `get-code-context-exa` skill reference only if it is also used for agent-tool-config purposes; otherwise remove.

**`.claude/agents/lead-0.md`** — apply the following edits:

1. Add `research-expert` row to the "Available specialists" table:
   > | `research-expert` | External web research via Exa | Looking up patterns, benchmarks, templates, or examples from sources outside the Anthropic API |
2. Add new `## Dispatch defaults` section immediately before `## Phase 0`:
   ```
   ## Dispatch defaults

   - **Parallel by default.** Independent specialist dispatches go in a single message with multiple Agent tool uses. Sequential dispatch is opt-in and requires a data dependency between calls.
   - **Grounding dispatches are invisible to the user.** No approval gate, no user-facing design task. Internal `Ground: <domain>` tasks only.
   - **Validation dispatches (Phase 2) are parallel.** One message, all relevant specialists, structured return shape.
   - **Specialists return 1-2 sentence summaries.** Verbose output goes to $RUN_DIR/{research,validation,provisioned}/.
   ```
3. Phase 1 `### Task protocol` — amend the invariant to: "At most one task whose `subject` starts with `Design:` may be `pending` or `in_progress` at a time. Grounding tasks (`Ground:`) are not counted."
4. Phase 1 `### Topic guide` — insert grounding annotations inline. For each step with a grounding row in the matrix above, prepend: `_Ground first: dispatch <specialist>._`
5. Phase 1 — insert the team-wiring grounding step: "Before opening the `Design: callable_agents wiring` task, ground via `multiagent-expert`."
6. Phase 2 — replace the current two paragraphs with the Section 2 two-part gate, including the structured return shape and the blocking rule.
7. `## Rules` — add two new bullets:
   - "Ground before drafting. For schema-heavy topics (tools, skills, env, vaults, resources, team wiring, persistent data), dispatch the owning specialist to confirm field names before framing follow-up questions."
   - "All external web research goes through `research-expert`. `lead-0` never calls Exa tools directly. Domain specialists are never dispatched for web research."

**`.claude/CLAUDE.md`** — update the Architecture section:

- Change "9 domain specialists (Sonnet), each carrying full API reference docs for their domain" to "10 domain specialists (Sonnet) carrying full API reference docs for their domain, plus 1 research specialist (`research-expert`) for external web research."

## Contracts and interfaces

**Grounding dispatch prompt shape.** `lead-0` sends a specialist a prompt of the form:
```
Grounding request for topic "<topic>". I am about to ask the user detailed questions about <topic>. Return the verified API schema for the fields the user will need to answer (field names, types, enums). Do not answer anything the user has not been asked yet. Summary only; no provisioning.
```

**Validation dispatch prompt shape.**
```
Validation request. Read $RUN_DIR/design/agent-specs.json. Validate only the <domain> section against your API reference docs. Return structured summary:
{ domain, fields_total, fields_verified, warnings: [{path, field, issue}], errors: [{path, field, issue}] }
Write detailed report to $RUN_DIR/validation/<domain>.md.
```

**Research dispatch prompt shape (unchanged from existing specialist dispatches).** `lead-0` describes the research question and target output file. `research-expert` handles bibliography/dedup internally.

## Testing

Given this is a prompt/configuration change, testing is behavioral — verified by running a second pipeline end-to-end with the updated prompts:

- Phase 1 produces at least one `Ground:` task before schema-heavy topics.
- `agent-specs.json` contains no fields that are not present in specialist API reference docs (manual review of one run).
- Phase 2 report shows "N/M fields verified" format; no narrative-only approval.
- `research-expert` is dispatched for all external web queries; `tools-expert` is NOT dispatched for research topics.
- `tools-expert.md` no longer references Exa tools.

Verification gate: one completed pipeline run where the user confirms no specialist schema surprises appeared in Phase 3 provisioning that were not already surfaced in the Phase 2 validation report.

## Migration / rollout

Single commit set (or one commit per file) touching:

- New file: `.claude/agents/research-expert.md`
- Edit: `.claude/agents/lead-0.md`
- Edit: `.claude/agents/tools-expert.md`
- Edit: `.claude/CLAUDE.md`

No data migration — all existing `runs/` output remains valid.

## Open questions

None at design time. Open items for the implementation plan:

- Exact wording of the grounding prompt template stored in `lead-0.md` (vs. inline each time). **Resolved during implementation:** grounding and validation get verbatim templates in `lead-0.md`'s `## Dispatch defaults` section; research has no template (deliberate — the research prompt varies by question, so codifying it would mislead).
- Whether the `Ground:` task invariant should be enforced by `lead-0` behaviorally only, or whether a light helper/convention is worth adding (likely: behavioral only, keeping the orchestrator lean).
- Whether `tools-expert` loses its Exa skill reference entirely or keeps `get-code-context-exa` for code-snippet lookups in its own domain (decide during implementation by reading `tools-expert.md`). **Resolved during implementation:** fully removed. tools-expert's domain has no legitimate use for Exa; the skill belongs to research-expert.

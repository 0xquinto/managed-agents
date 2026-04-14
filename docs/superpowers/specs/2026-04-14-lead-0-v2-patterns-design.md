# Design: lead-0 v2 — audit-derived patterns

**Date:** 2026-04-14
**Status:** Approved for planning
**Predecessor:** `docs/superpowers/specs/2026-04-13-lead-0-grounding-and-research-expert-design.md`

## Problem

The v1 changes (grounding + research-expert + Phase 2 validation) were audited against the insignia run's `agent-specs.json`. Audit returned ~15 / ~120 fields fully provisionable. Beyond the run-specific field-name errors (which v1 grounding should prevent going forward), six **general patterns** surfaced — classes of errors that would recur on any non-trivial run unless the orchestrator's prompt is updated. A subsequent review by lead-0 itself against this spec flagged five additional residual gaps; three were accepted as cheap extensions of the original patterns, and the remaining two (leakage guard, external consumer contracts) were pulled in after scoping.

This spec fixes eleven pattern-level issues in total: the original six plus five follow-ups.

## Goals

- Structurally separate design metadata from API payload so specialists never see orchestrator-invented fields as "invalid."
- Move Phase 3 ordering from orchestrator-authored (speculative) to validator-generated (authoritative).
- Eliminate phantom artifacts: the draft spec is always self-contained by the time Phase 2 runs.
- Ground cross-cutting capabilities (HITL) against every domain that owns them, not just the one that seems closest.
- Surface two narrow but recurring design traps (`/mnt/session/` path confusion; evaluator structured config) at the topic where they arise.
- Make `/mnt/session/` misuse and `design_notes`↔`api_fields` misclassification mechanically enforced, not prose-discipline.
- Validate external-consumer contracts (event shapes, custom tools) against the API so adjacent projects don't hard-code wrong shapes.

## Non-goals

- Changes to specialist API reference docs (only their **return shape** expands for Phase 2).
- A new specialist. All patterns are prompt-level changes to `lead-0.md` plus a small return-shape addition for every existing validation-capable specialist.
- Re-running the insignia run under v2. That's a verification step, separate from this spec.
- Spec-format backwards compatibility. No committed `agent-specs.json` exists that must migrate.
- `integration_contracts` vocabulary beyond `event_shape` and `custom_tool` — extensible in v3 if new kinds come up.

## Design

### 1. `design_notes` subtree convention (Pattern #1)

**Spec format change.** Every object in `agent-specs.json` splits into two subtrees:

```json
{
  "agents": [
    {
      "api_fields": {
        "name": "insignia_coordinator",
        "system": "You are...",
        "tools": [...],
        "skills": [...]
      },
      "design_notes": {
        "pattern_source": "inferred: user described team-coordinator pattern in turn 4",
        "rotation_policy": "quarterly",
        "stakeholders": "Insignia modeling team"
      }
    }
  ]
}
```

**Writing rules (applies to lead-0's spec-authoring behavior in Phase 1):**

- lead-0 authors `design_notes` automatically as Phase 1 context accrues. Any phrasing the user offers that is not a direct API field value becomes a candidate note.
- Every auto-written note uses the `inferred:` prefix followed by a short paraphrase of the user statement it was derived from, e.g. `"pattern_source": "inferred: user described team-coordinator pattern when discussing agent roles"`. No turn numbers or timestamps — the paraphrase is the provenance.
- User-volunteered notes (where the user explicitly says "record this" or similar) drop the `inferred:` prefix.
- At the end of Phase 1, before `agent-specs.json` is written to disk, lead-0 renders the full `design_notes` tree across all objects as a flat list and asks: "Here's the design context I captured. Confirm, remove, or add." ONE confirmation pass — not per topic.
- User changes are applied inline. No second pass required unless the user requests one.

**Specialist behavior:**

- Grounding dispatches read nothing from the spec (grounding fires before any spec exists).
- Validation dispatches read **only** the `api_fields` subtree of their domain's objects. `design_notes` is invisible to them.
- Provisioning dispatches (Phase 3) also read only `api_fields`. `design_notes` never reaches the API.

**Consequence:** the 60% of insignia-audit-flagged fields that were design metadata would have been structurally separated and invisible to validators. The remaining ~40% (real schema errors) would be the entire Phase 2 error surface.

### 2. Validator-generated Phase 3 order (Pattern #2)

**Extended return shape for validation dispatches:**

```
{
  domain,
  fields_total,
  fields_verified,
  warnings: [{path, field, issue}],
  errors:   [{path, field, issue}],
  prereqs:  [{ step, depends_on: [domain|step_id], produces: [domain|artifact] }]
}
```

`prereqs` is a list of pre-provisioning work items the specialist owns. Empty array if the specialist has no prereqs.

**Examples (from the insignia audit, rendered forward):**

- `files-expert`: `{ step: "upload smoke test fixtures", depends_on: [], produces: ["file_ids"] }`
- `tools-expert`: `{ step: "inline custom_tool input_schema_file content", depends_on: [], produces: ["inlined_custom_tool_schemas"] }`
- `multiagent-expert`: `{ step: "rewrite callable_agents strings to {type, id, version}", depends_on: ["agents.create"], produces: ["resolved_callable_agents"] }`

**lead-0 post-validation behavior:**

1. Collect every `prereqs` array across all Phase 2 return payloads.
2. Topologically sort the combined list. Any step whose `depends_on` isn't yet produced waits; any step ready goes next.
3. Prepend the sorted prereq list to the existing provisioning order (files → vaults → skills → agents || environments → sessions).
4. Write the combined ordered list to `api_fields.provisioning_plan.phase_3_order` on the top-level spec object.

**Cycle handling.** If the topo sort detects a cycle, lead-0 surfaces the cycle to the user: "Cycle detected between `<step_a>` and `<step_b>`. Resolve before provisioning." No auto-break.

**Phase 2 user-facing report gets one line:**

```
Provisioning order: 11 steps (4 prereqs + 7 standard)
```

The full ordered list is available on request but not rendered by default — keeps the report compact.

**Specialist prompt update.** Every existing validation-capable specialist (agents-expert, tools-expert, environments-expert, skills-expert, mcp-vaults-expert, memory-expert, multiagent-expert, files-expert, events-expert, sessions-expert) gets one new line in its Rules section:

> When dispatched for validation, include a `prereqs` array in the structured return. Each entry has `{ step, depends_on, produces }`. Return `prereqs: []` if your domain has no pre-provisioning prerequisites for this spec.

### 3. Inline system prompts at Phase 2 (Pattern #3)

**Phase 1 behavior change.** When the system-prompt design task for an agent completes (topic guide step 11), lead-0 IMMEDIATELY writes the drafted content to `$RUN_DIR/design/system_prompts/<agent_name>.md`. No deferral. The file exists on disk the moment the task is marked `completed`.

**Phase 1 invariant added:**

> No design task whose `subject` is `"Design: system prompt for <agent>"` may be marked `completed` before `$RUN_DIR/design/system_prompts/<agent>.md` exists on disk with the drafted content.

**Pre-Phase-2 inlining step.** Immediately before Phase 2 Part A (validation dispatch), lead-0:

1. For every agent in the draft spec, reads `$RUN_DIR/design/system_prompts/<agent_name>.md`.
2. Inlines the file contents as `api_fields.system` on that agent object.
3. Removes any `system_prompt_file` field if present (it's a design-time aid, not an API field).
4. Preserves the `.md` file on disk — it's the source of truth for humans; the inlined string is the source of truth for provisioning.

**Failure mode.** If any `.md` file is missing at inline time, lead-0 halts with: "Cannot run validation — system prompt for `<agent>` is referenced but `$RUN_DIR/design/system_prompts/<agent>.md` doesn't exist." User resolves before validation proceeds.

**Phase 2 rollup gains one line:**

```
System prompts inlined: 5/5 (from design/system_prompts/*.md)
```

**File location.** New subdirectory `$RUN_DIR/design/system_prompts/`, documented in the run-directory contract.

### 4. HITL canonical Ground dispatch (Pattern #4)

**New rule added to `## Rules` in `lead-0.md`:**

> **HITL grounding trigger.** When the user describes behavior requiring human approval, confirmation, or gating (keywords: "approval", "human-in-the-loop", "HITL", "gate", "confirm before", "require sign-off"), pause the current topic and dispatch `tools-expert` + `events-expert` in parallel with a grounding request for the HITL pattern. Resume the current topic using the verified pattern (custom tool + `user.tool_confirmation` event flow) as the framing, not whatever lead-0 first imagined.

Not a topic-guide step — a cross-cutting trigger that can fire during any topic.

### 5. `/mnt/session/` invariant (Pattern #5)

**New rule added to `## Rules`:**

> **`/mnt/session/` means session resources.** Paths under `/mnt/session/` refer only to files mounted via the Files API + session resources at session creation. If the user describes pre-baked content at `/mnt/session/<path>`, halt and clarify the delivery mechanism: session resources (mount at creation), bake into the image (env `config.packages` or Dockerfile), or a different path (e.g., `/opt/fixtures/`).

**Plus inline annotations on Phase 1 topic guide steps 12 (Environment) and 13 (Resources):**

> `   _Watch: if the user mentions fixtures, scripts, or data at `/mnt/session/...`, clarify the delivery mechanism explicitly. /mnt/session/ is session-resource-scoped, not env-scoped._`

### 6. Evaluator structured config home (Pattern #6)

**New annotation on the team-wiring step of Phase 1 topic guide** (adjacent to the existing `_Ground first: dispatch multiagent-expert._` line):

> `   _If the team includes an evaluator agent: explicitly ask where its rubric structure (weights, dimensions, thresholds) lives. Rubrics have NO dedicated API field — they must be embedded in system prompt text, referenced via a skill, or loaded from a file at runtime. The design question is "where," not "whether."_`

### 7. Generalize Pattern #3 to all `*_file` pointers (Pattern #7)

**Supersedes §3.** §3 handled `system_prompt_file` only. The same pointer-vs-value failure mode applies to every `*_file` key lead-0 may introduce (insignia had `input_schema_file` with the same issue; evaluator designs will surface `rubric_file`). One rule covers all kinds; §3's narrower rule is an instance of this one.

**Rule (applies to Phase 1 task-completion behavior):** any `api_fields` key whose name ends in `_file` (matched as a suffix on the key, case-sensitive, no other constraints) is a design-time aid. lead-0:

1. Writes the referenced content to `$RUN_DIR/design/<subdir>/<name>.<ext>` at design-task-completion time (not deferred).
2. Pre-Phase-2, reads every `*_file` value, inlines the content into the adjacent canonical field, and removes the `*_file` key.
3. Halts pre-Phase-2 if any referenced file is missing on disk.

**Canonical mapping** (extensible — new kinds documented inline when introduced):

| `*_file` key | Inlined as | Subdirectory | Format |
|---|---|---|---|
| `system_prompt_file` | `system` | `design/system_prompts/` | markdown (content becomes string) |
| `input_schema_file` | `input_schema` | `design/input_schemas/` | JSON (content becomes object) |
| `rubric_file` | `rubric` | `design/rubrics/` | JSON (content becomes object) |

**Phase 1 invariant (replaces §3's narrower one):**

> No design task whose `subject` introduces an `api_fields.*_file` reference may be marked `completed` before the referenced file exists on disk under `$RUN_DIR/design/<subdir>/` with the drafted content.

**Phase 2 rollup extends:** `Inlined: 5 system_prompts, 4 input_schemas, 1 rubric (from design/*)`.

### 8. Hard enforcement of `prereqs` return shape (Pattern #8)

Replaces this spec's original soft-default open question.

**Rule (Phase 2 validation dispatch return-shape enforcement):** on any Phase 2 dispatch return that omits `prereqs` or returns a non-array value, lead-0 halts Phase 2 with:

> "Specialist `<name>` returned without required `prereqs` array. Re-dispatch or fix the specialist prompt."

No auto-default to `[]`. A specialist with genuinely no prereqs must return `prereqs: []` explicitly. The requirement is codified in every specialist prompt (§2 Rules bullet).

**Rationale.** A silent missing-prereq means a required pre-provisioning step vanishes from `phase_3_order`. Cost of a false-negative topo-sort gap is a mid-Phase-3 provisioning failure — far more expensive than a Phase 2 halt that re-dispatches the specialist.

### 9. `/mnt/session/` mechanical lint pass (Pattern #9)

§5 established prose discipline. §9 makes it mechanical, because three independent insignia validators flagged the same pattern without the prose discipline catching it in-flow.

**New pre-Phase-2 lint step** (runs immediately before Phase 2 Part A, and before the validation dispatches):

```
Walk api_fields of every domain in the draft spec. For every string value containing "/mnt/session/":
  If the containing object is NOT a session_resources[i] entry declaring a mount path:
    Halt and surface:
      "Path '/mnt/session/...' appears in <domain>.<path>.<field>.
       /mnt/session/ is reserved for session resources mounted at session creation.
       Clarify delivery: session resource, bake into image, or different path."
```

Mechanical — no specialist dispatch. Complements §5 (prose discipline fires during Phase 1; lint fires right before Phase 2).

### 10. `design_notes` leakage guard via captured API schemas (Pattern #10)

Guards against lead-0 misclassifying a design field into `api_fields` where validators flag it as invalid.

**New Phase 1 artifact.** Every grounding dispatch response is normalized by lead-0 into `$RUN_DIR/design/api_schemas/<domain>.json` — a list of valid API field names (and, optionally, their types/enums) for that domain, as returned by the specialist. Written immediately when the grounding task completes.

Shape:

```json
{
  "domain": "agents",
  "fields": [
    { "name": "name", "type": "string" },
    { "name": "system", "type": "string" },
    { "name": "tools", "type": "array" },
    ...
  ],
  "source": "grounding dispatch to agents-expert, Phase 1 step 6"
}
```

**New lint step pre-Phase-2 (runs before §9's `/mnt/session/` lint):**

```
For every domain with an api_schemas/<domain>.json file:
  For every key in api_fields of that domain's objects:
    If key is not in the whitelist (fields[].name):
      Halt and surface:
        "Field '<key>' in <domain>.<path> is not a known API field for <domain>.
         If this is design metadata, move to design_notes. If it should be an API field, re-ground <domain>."
```

**Grounding matrix extension.** To give the lint surface complete coverage, every domain that appears in Phase 1 gets grounded at least once. v1 grounds 8 domains via topic-guide steps. Two additions:

- `memory-expert`: ground at topic 17 when the persistent-data classification selects memory-store delivery.
- `events-expert`: ground whenever any `integration_contracts` entry is declared OR when custom tools are defined (custom tools imply event-shape design for `user.custom_tool_result`).

Both are one-line topic-guide additions.

### 11. Integration contracts + elicitation (Pattern #11)

Validates external-consumer contracts (the Teams-bot case) against the API so adjacent projects don't hard-code wrong shapes.

**New `api_fields.integration_contracts` array (top-level on the spec):**

```json
{
  "integration_contracts": [
    {
      "consumer": "<name>",
      "role": "implementor" | "subscriber",
      "touches": [
        { "kind": "event_shape",  "event_type": "<event type>" },
        { "kind": "custom_tool",  "name":       "<tool name>" }
      ]
    }
  ]
}
```

`kind` vocabulary is bounded to `event_shape` and `custom_tool` in v2 (extensible in v3).

**Per-contract design notes.** Every `integration_contracts` entry has a matching `design_notes.integration_contracts[<consumer>]` entry capturing the "why" (what team owns it, why it exists, rotation/auth assumptions). lead-0 writes these during elicitation.

**Phase 2 validation behavior.**

- `events-expert` validates each `event_shape` touchpoint against its API reference: shape correctness, required fields, correct event classification. Errors land in its standard error list.
- `tools-expert` validates each `custom_tool` touchpoint: the `name` matches a declared custom tool in the spec, `input_schema` is consistent with what the custom tool declares.
- Errors from these cross-checks are not distinguished from normal validation errors in the rollup — they appear under their owning specialist.

**New Phase 1 topic-guide step** (inserted after the existing step 14 "Runtime identity"):

> **14.5 External consumers** — Does anything outside this pipeline implement or consume this agent's API surface (bot, webhook, script, adjacent project)? If yes: what does it touch — events, custom tools? Capture as `integration_contracts` with a matching `design_notes.integration_contracts[<consumer>]` entry for the "why."
>   `_Ground first: dispatch events-expert and tools-expert in parallel if any integration_contracts are declared._`

Question-gated: if user says "no external consumers," skip elicitation entirely (no empty `integration_contracts` array written).

## Files touched

- **`.claude/agents/lead-0.md`** — design_notes authoring, Phase 1 close-out confirmation, `*_file` invariant (generalized), pre-Phase-2 inlining step (generalized to all `*_file` kinds), Phase 2 return-shape hard enforcement, `/mnt/session/` mechanical lint, leakage-guard lint (new), `api_schemas/` artifact capture during grounding, extended Phase 2 user-facing report, 3 new rules (HITL trigger, `/mnt/session/` invariant, `*_file` file existence), `/mnt/session/` watch annotations on Phase 1 topic guide steps 12+13, team-wiring evaluator annotation, new topic-guide step 14.5 "External consumers," two new topic-guide grounding annotations (memory-expert at step 17 memory-store path, events-expert at custom-tool / integration-contract paths), `provisioning_plan.phase_3_order` auto-generation step.
- **`.claude/agents/<each validation-capable specialist>.md`** (10 files: agents-expert, tools-expert, environments-expert, skills-expert, mcp-vaults-expert, memory-expert, multiagent-expert, files-expert, events-expert, sessions-expert) — add one Rules bullet requiring a `prereqs` array (possibly empty) in every validation return.
- **`.claude/agents/events-expert.md`** and **`.claude/agents/tools-expert.md`** — additional Rules bullets for `integration_contracts` validation behavior (event shape and custom tool cross-checks respectively, when contracts are present).
- **`.claude/CLAUDE.md`** — no change. Count is unchanged; credential handling unchanged; invariants unchanged. The spec format (`api_fields` / `design_notes`), `integration_contracts`, and mechanical lints are lead-0 behavior, not CLAUDE.md invariants.

## Contracts and interfaces

**Validation dispatch prompt shape** (updates the template in lead-0's `### Dispatch prompt templates`):

```
Validation request. Read $RUN_DIR/design/agent-specs.json and look only at the `api_fields` subtree of the <domain> section. Validate each field against your API reference docs. Return structured summary:
{ domain, fields_total, fields_verified, warnings: [{path, field, issue}], errors: [{path, field, issue}], prereqs: [{ step, depends_on, produces }] }
Write detailed report to $RUN_DIR/validation/<domain>.md.
```

**Prereq entry shape:** `{ step: string, depends_on: string[], produces: string[] }`. `depends_on` and `produces` elements are either domain names (`"agents.create"`) or prereq step identifiers (another specialist's `step` string). String-matching based; no schema enforcement — human-readable is the priority.

**design_notes shape:** free-form JSON object. No required keys. lead-0 chooses key names during Phase 1. Validator behavior is to ignore the subtree entirely.

**api_schemas capture shape** (written during Phase 1 grounding):

```json
{
  "domain": "<domain>",
  "fields": [ { "name": "<field>", "type": "<type>" }, ... ],
  "source": "<short description of which grounding dispatch produced this>"
}
```

**integration_contracts entry shape:**

```json
{
  "consumer":  "<name>",
  "role":      "implementor" | "subscriber",
  "touches": [
    { "kind": "event_shape", "event_type": "<event type>" },
    { "kind": "custom_tool", "name":       "<tool name>" }
  ]
}
```

`kind` is bounded to those two values in v2. Adding a new kind in v3 requires: (a) extending the elicitation question, (b) naming the owning specialist, (c) adding a validation branch in that specialist's prompt.

## Testing

Prompt/configuration change. Verification is behavioral:

1. **Re-audit the insignia spec under v2 rules.** The existing `runs/2026-04-13T21-46-59Z-insignia-design/design/agent-specs.json` is still in flat-object form. Write a one-shot transform that splits it into `api_fields` / `design_notes` based on the validator-flagged categories from the audit. Re-run Phase 2 against the transformed spec. Expected: the error rate drops from ~87% to ~40% (the remaining errors are real schema issues v1 grounding will catch going forward, not format issues).
2. **Structural verification** (per-commit greps, same style as v1's plan Task 8): `api_fields` / `design_notes` convention appears in lead-0 prompt; extended validation return shape documented; new rules present; new annotations present; every specialist prompt has the prereqs bullet; `*_file` generalized invariant present; `/mnt/session/` lint step present; leakage-guard lint step present; api_schemas artifact capture documented; integration_contracts elicitation step 14.5 present; events-expert and tools-expert carry their integration-contracts validation rules.
3. **End-to-end verification (out of scope for this spec):** next full pipeline run should produce an `agent-specs.json` with the two-subtree structure, a `provisioning_plan.phase_3_order` generated from validator prereqs, all `*_file` references inlined before Phase 2, `api_schemas/*.json` populated for every grounded domain, `/mnt/session/` lint either silent or halting with a clear reason, and (if the user declared external consumers) `integration_contracts` validated by events-expert + tools-expert.

## Migration / rollout

No data migration. No committed `agent-specs.json` exists that must be converted; the insignia run was deferred before provisioning.

For the insignia re-audit in Testing step 1, the transform is single-use and not committed — it's a verification artifact, not a production path.

## Open questions

- **Phase 2 validator return-shape enforcement.** ~~Leaning default-empty.~~ **Resolved: hard enforcement** (§8). lead-0 halts on a missing or non-array `prereqs` return. Rationale in §8.
- **`design_notes` confirmation ergonomics.** Rendering "all notes across all objects" at end of Phase 1 could be a long list on team designs. Acceptable for v2; if it gets unwieldy we can add grouping by agent. Not blocking.
- **Inlined system prompt length.** JSON gets verbose when prompts are long. No quality issue — the `.md` file is the human-readable version. If readability of `agent-specs.json` becomes a review blocker, consider base64 or an adjacent `system.txt` that provisioners can reference. Not doing it now.
- **api_schemas lint strictness.** §10's whitelist treats any unknown key as a halting error. Some API fields have optional sub-objects whose keys vary (e.g., `configs[].name` in tool configs). The whitelist is by top-level object field name, not by nested-path. If nested paths surface false positives, narrow the lint to the first-level keys only. Revisit after first v2 run.
- **External consumer contract drift over time.** `integration_contracts` is validated at design time. An adjacent project (e.g., Teams bot) may later change its assumptions. v2 doesn't watch for drift — validation is a one-shot at Phase 2. v3 could add "contract pinning" where the bot owns a signed capability document. Not in scope.

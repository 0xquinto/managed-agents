# docs-auditor API Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing docs-auditor with a `schema` mode targeting the richer `/api/beta/*` docs tree, then run per-expert and cross-cutting audits to close the "everything our experts need" gap.

**Architecture:** Three phases. Phase 1 is a surgical edit to `.claude/agents/docs-auditor.md` adding a new mode — smoke-tested against a live URL. Phase 2 runs 8 parallel per-expert auditor subagents using the new mode; findings consolidated in the main conversation and applied as separate commits per expert. Phase 3 runs one cross-cutting auditor subagent for concerns spanning multiple experts (built-in tools, permission policies, beta header catalog, model enum, Anthropic-managed skills, research-preview gating).

**Tech Stack:** Claude Code agent-definition format (YAML frontmatter + prompt), Anthropic MCP Exa tools (`mcp__exa__crawling_exa`), Bash + curl (already permitted on docs-auditor for sitemap fetching).

---

## File Structure

- Modify: `.claude/agents/docs-auditor.md` — add `schema` mode alongside existing `section` and `coverage`.
- Modify: `docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md` — mark status `implemented` after Phase 1 lands.
- No new files. No changes to other experts until Phase 2 / Phase 3 findings are applied; those edits touch individual expert files under `.claude/agents/` and are driven by audit output, not this plan.

The spec for this extension already exists at `docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md` and must be read before implementation.

---

## Phase 1 — Add `schema` mode

### Task 1: Add schema mode to docs-auditor

**Files:**
- Modify: `.claude/agents/docs-auditor.md`

- [ ] **Step 1: Read the current agent file**

Run: `cat .claude/agents/docs-auditor.md | head -60`
Confirm: frontmatter, `## Sources` block, `## Modes` block with `section` and `coverage` subsections.

- [ ] **Step 2: Update the Sources section to reference the API tree**

Current `## Sources` block lists two source shapes (per-subcommand CLI pages and sitemap). Add a third source shape for schema mode.

Apply this edit. Find:

```
The canonical docs are a **tree** of per-subcommand pages, not a single URL. Two source shapes:

- **Per-subcommand pages** (section mode):
  `https://platform.claude.com/docs/en/api/cli/beta/<domain>/<action>`
  e.g., `https://platform.claude.com/docs/en/api/cli/beta/agents/create`
  For nested domains (events under sessions): `https://platform.claude.com/docs/en/api/cli/beta/sessions/events/send`

- **Sitemap** (coverage mode):
  `https://platform.claude.com/sitemap.xml`
```

Replace with:

```
The canonical docs are a **tree** of per-subcommand pages, not a single URL. Three source shapes:

- **CLI reference pages** (section mode):
  `https://platform.claude.com/docs/en/api/cli/beta/<domain>/<action>`
  e.g., `https://platform.claude.com/docs/en/api/cli/beta/agents/create`
  For nested domains (events under sessions): `https://platform.claude.com/docs/en/api/cli/beta/sessions/events/send`

- **API reference pages** (schema mode):
  `https://platform.claude.com/docs/en/api/beta/<domain>/<action>`
  e.g., `https://platform.claude.com/docs/en/api/beta/agents/create`
  These pages contain richer schema content than the CLI pages — full nested type definitions, all enumerated union members (beta headers, model IDs, tool identifiers, permission policies), and complete response shapes. Language selector at the top of the page only swaps the `### Example` code block; Header Parameters, Body Parameters, and Returns blocks render identically regardless of language selection.

- **Sitemap** (coverage mode):
  `https://platform.claude.com/sitemap.xml`
```

- [ ] **Step 3: Update the Modes introduction**

Find:

```
## Modes

The caller's prompt selects the mode. Infer from the request:

- If the caller asks for a coverage check, gaps, or whether subcommands are "covered", "missing", or "present in local agents", run **coverage** mode — even if a specific subcommand is named in the question.
- Otherwise, if the caller names a subcommand (e.g., `ant beta:agents:create`) and wants its upstream docs, run **section** mode.
- If ambiguous, ask one clarifying question before fetching.
```

Replace with:

```
## Modes

The caller's prompt selects the mode. Infer from the request:

- If the caller asks for a coverage check, gaps, or whether subcommands are "covered", "missing", or "present in local agents", run **coverage** mode — even if a specific subcommand is named in the question.
- If the caller asks for "schema", "API reference", "request body", "response shape", or "types/fields" for a subcommand, run **schema** mode.
- Otherwise, if the caller names a subcommand (e.g., `ant beta:agents:create`) and wants its upstream CLI docs, run **section** mode.
- If the request could be section or schema (e.g., "show me the docs for `ant beta:agents:create`"), ask one clarifying question: "section (CLI flags) or schema (API request/response shape)?"
```

- [ ] **Step 4: Add the schema mode block**

Find the end of the `### Mode 2 — coverage` block, specifically the line:

```
Always include the "Out-of-scope upstream" section, even if only informational.
```

Immediately after it (and before `## Tool selection rules`), insert:

```

### Mode 3 — schema

**Input:** one subcommand identifier in `ant beta:<domain>[:<sub>]:<action>` form (same shape as section mode).

**Behavior:**

1. Convert the identifier to an API-tree URL:
   `ant beta:agents:create` → `https://platform.claude.com/docs/en/api/beta/agents/create`
   `ant beta:sessions:events:send` → `https://platform.claude.com/docs/en/api/beta/sessions/events/send`
   Note the path is `/api/beta/` (no `cli/` segment) — this is the difference between section and schema mode.
2. Call `mcp__exa__crawling_exa` with that URL.
3. If the crawl returns "Not Found" or content that is empty or clearly truncated (e.g., missing the expected Body Parameters or Returns sections), invoke the `get-code-context-exa` skill with a query like `Anthropic API <domain> <action> request body response schema`. Label skill-derived excerpts per the Labeling rule.
4. If the fetch succeeds but the named action is not present on the page, return the not-found line (see below).
5. If both paths fail, return the failure string (see `## Failure mode`). Never synthesize content.

**Output:** the raw schema excerpt, unmodified — Header Parameters, Body Parameters, Returns, Example. Never paraphrase or summarize. The caller is diffing against local prose, so verbatim fidelity matters.

Format:

```
## Upstream schema: `ant beta:<subcommand>`
**Source:** <url>
**Fetched via:** <Exa crawl or get-code-context-exa skill — substitute whichever you actually used>

<verbatim excerpt>
```

If the named action is not present upstream, return exactly:

```
NOT FOUND: `ant beta:<subcommand>` schema is not documented at https://platform.claude.com/docs/en/api/beta/<domain>/<action>
```
```

- [ ] **Step 5: Update Tool selection rules**

Find:

```
- **Section mode primary:** `mcp__exa__crawling_exa` on the per-subcommand URL. `WebFetch` will not work on these pages — the canonical docs are JS-rendered.
- **Section mode fallback:** the `get-code-context-exa` skill with a query naming the subcommand. Skill-derived content MUST be labeled per the Labeling rule.
- **Coverage mode:** `Bash` + `curl` on `sitemap.xml` only. WebFetch mangles XML; Exa crawl rejects it. `Bash` is scoped in this agent to this single use — do NOT run any other shell command.
```

Replace with:

```
- **Section mode primary:** `mcp__exa__crawling_exa` on the per-subcommand CLI URL (`/api/cli/beta/...`). The canonical docs are JS-rendered.
- **Schema mode primary:** `mcp__exa__crawling_exa` on the API-reference URL (`/api/beta/...`, no `cli/` segment). Same reasoning — JS-rendered.
- **Section and schema mode fallback:** the `get-code-context-exa` skill with a query naming the subcommand. Skill-derived content MUST be labeled per the Labeling rule.
- **Coverage mode:** `Bash` + `curl` on `sitemap.xml` only. WebFetch mangles XML; Exa crawl rejects it. `Bash` is scoped in this agent to this single use — do NOT run any other shell command.
```

- [ ] **Step 6: Verify the file parses cleanly**

Run: `head -10 .claude/agents/docs-auditor.md`
Expected: YAML frontmatter unchanged, `model: sonnet`, tools list unchanged.

Run: `grep -n "^###\|^##" .claude/agents/docs-auditor.md`
Expected: all three modes present — `### Mode 1 — section`, `### Mode 2 — coverage`, `### Mode 3 — schema`, followed by `## Tool selection rules` and the other top-level sections.

Run: `wc -l .claude/agents/docs-auditor.md`
Expected: roughly 135–165 lines (previous was 117; adding schema mode is ~30 lines).

- [ ] **Step 7: Commit**

```bash
git add .claude/agents/docs-auditor.md
git commit -m "$(cat <<'EOF'
Add schema mode to docs-auditor

New mode fetches /docs/en/api/beta/<resource>/<action> pages, which
contain richer schema content than the CLI reference pages — full
nested type definitions, enumerated union members (beta headers,
model IDs, tool identifiers, permission policies), and complete
response shapes.

Mode selection rules extended: the agent picks schema when the
caller asks for API reference / request body / response shape, and
section when the caller wants CLI flags. Ambiguous phrasings
('show me the docs for X') trigger a clarifying question.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: one commit, one file changed, ~30 insertions.

---

### Task 2: Smoke-test schema mode

**Files:** None modified. Live invocation test.

- [ ] **Step 1: Dispatch docs-auditor in schema mode**

From the main Claude Code conversation, dispatch the docs-auditor subagent with this prompt:

```
Run schema mode for `ant beta:agents:create`. Return the full upstream API reference verbatim.
```

Expected response shape:

```
## Upstream schema: `ant beta:agents:create`
**Source:** https://platform.claude.com/docs/en/api/beta/agents/create
**Fetched via:** Exa crawl

<Header Parameters block>
<Body Parameters block with nested types expanded>
<Returns block>
<Example block>
```

- [ ] **Step 2: Verify schema content is richer than CLI section output**

Confirm the response includes:
- The `anthropic-beta` header with all 24 enumerated beta values (e.g., `managed-agents-2026-04-01`, `skills-2025-10-02`, `fast-mode-2026-02-01`, …).
- The `tools` parameter expanded into its three union members: `BetaManagedAgentsAgentToolset20260401Params`, `BetaManagedAgentsMCPToolsetParams`, `BetaManagedAgentsCustomToolParams`.
- All 8 built-in tool names (`bash`, `edit`, `read`, `write`, `glob`, `grep`, `web_fetch`, `web_search`) enumerated under `BetaManagedAgentsAgentToolConfigParams.name`.
- Both permission policy types (`BetaManagedAgentsAlwaysAllowPolicy`, `BetaManagedAgentsAlwaysAskPolicy`).

If any of these is missing, the crawl returned truncated content — re-read the docs-auditor agent file and check whether the schema mode prompt is instructing the agent to fetch at adequate content size. The Exa crawl call should request a high enough `maxCharacters` to capture the full schema (~30-50KB of extracted text).

- [ ] **Step 3: Verify section-mode is not broken**

Quick regression check. Dispatch:

```
Run section mode for `ant beta:agents:create`. Return the full upstream section verbatim.
```

Expected: response shape starts with `## Upstream section:` and source URL is `/api/cli/beta/agents/create` (not `/api/beta/`). Confirm the new schema mode didn't change section mode's URL construction.

- [ ] **Step 4: No commit needed**

This is a live-run smoke test, not a source change.

---

### Task 3: Update spec status

**Files:**
- Modify: `docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md`

- [ ] **Step 1: Flip status to Phase 1 implemented**

Find:

```
**Status:** approved for planning
```

Replace with:

```
**Status:** Phase 1 implemented (schema mode) — 2026-04-15; Phases 2 and 3 pending
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md
git commit -m "$(cat <<'EOF'
Mark Phase 1 of docs-auditor API extension as implemented

Phase 1 (schema mode) landed in the preceding commit. Phases 2
(per-expert API-reference audit) and 3 (cross-cutting ecosystem
audit) remain.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Per-expert API-reference audit

### Task 4: Dispatch 8 parallel per-expert audit subagents

**Files:** None modified. Subagent dispatches only.

- [ ] **Step 1: Single message, 8 parallel Agent tool calls**

From the main conversation, issue one message containing 8 Agent tool calls (all with `run_in_background: true`). Each prompt follows the template below with substitutions.

Template (substitute `<EXPERT_NAME>`, `<FILE_PATH>`, `<RESOURCE_LIST>`, `<SUBAGENT_DESCRIPTION>`):

```
You are auditing a local agent-definition file's ## API Reference section against the upstream API schema.

**File to audit:** <FILE_PATH>

**Upstream resources to crawl:** <RESOURCE_LIST>
  (Use `mcp__exa__crawling_exa` with URL pattern `https://platform.claude.com/docs/en/api/beta/<resource>` — domain-index URL returns all actions at once.)

## Your task

1. Read the local file.
2. Call `mcp__exa__crawling_exa` on each resource-index URL (batch multiple URLs in one call if there are multiple resources).
3. For the `## API Reference` section of the local file, diff the documented field tables, lifecycle narratives, type references, and response shapes against the crawled schema.
4. Classify findings:
   - **Stale:** local prose contradicts upstream (field renamed, enum shrank, constraint changed, type widened/narrowed).
   - **Missing:** upstream has required fields, constraints, type references, or response shapes the local file omits and an operator would need to reason about.
   - **Inaccurate:** local claims something upstream refutes.
5. **Caveats** (FYI, not drift):
   - Content gated behind `managed-agents-2026-04-01-research-preview` or similar research-preview beta headers may not appear on the public API page. If the local file correctly marks it as research-preview, treat as FYI.
   - Upstream prose-ish narrative (lifecycle descriptions, edge-case behavior) isn't on every API page — the API pages are schema-heavy. Narrative content in the local file isn't drift if it's consistent with the schema even if upstream doesn't duplicate it.
   - CLI-only convenience flags already documented in `## CLI Commands` are out of scope — this audit is for `## API Reference` only.

## Report format

Return only a compact markdown report. Do NOT include upstream content verbatim — just findings.

```
# <EXPERT_NAME>.md — API reference audit

## Stale
- **<field or claim>** (line N): local says "...", upstream says "..."
- (or "None")

## Missing
- ...
- (or "None")

## Inaccurate
- ...
- (or "None")

## Upstream gaps (FYI, not agent bugs)
- ... (or "None observed")

## Verdict
One sentence.
```

Keep under 400 words.
```

Substitutions per expert:

| agent dispatch | `<FILE_PATH>` | `<RESOURCE_LIST>` | `<SUBAGENT_DESCRIPTION>` |
|---|---|---|---|
| 1 | `/Users/diego/Dev/managed_agents/.claude/agents/agents-expert.md` | `agents` (URL: `https://platform.claude.com/docs/en/api/beta/agents`) and `agents/versions` (URL: `https://platform.claude.com/docs/en/api/beta/agents/versions`) | `Audit agents-expert API ref` |
| 2 | `/Users/diego/Dev/managed_agents/.claude/agents/environments-expert.md` | `environments` (URL: `https://platform.claude.com/docs/en/api/beta/environments`) | `Audit environments-expert API ref` |
| 3 | `/Users/diego/Dev/managed_agents/.claude/agents/events-expert.md` | `sessions/events` (URL: `https://platform.claude.com/docs/en/api/beta/sessions/events`) | `Audit events-expert API ref` |
| 4 | `/Users/diego/Dev/managed_agents/.claude/agents/files-expert.md` | `files` (URL: `https://platform.claude.com/docs/en/api/beta/files`) | `Audit files-expert API ref` |
| 5 | `/Users/diego/Dev/managed_agents/.claude/agents/mcp-vaults-expert.md` | `vaults` (URL: `https://platform.claude.com/docs/en/api/beta/vaults`) and `vaults/credentials` (URL: `https://platform.claude.com/docs/en/api/beta/vaults/credentials`) | `Audit mcp-vaults-expert API ref` |
| 6 | `/Users/diego/Dev/managed_agents/.claude/agents/sessions-expert.md` | `sessions` (URL: `https://platform.claude.com/docs/en/api/beta/sessions`) and `sessions/resources` (URL: `https://platform.claude.com/docs/en/api/beta/sessions/resources`) | `Audit sessions-expert API ref` |
| 7 | `/Users/diego/Dev/managed_agents/.claude/agents/skills-expert.md` | `skills` (URL: `https://platform.claude.com/docs/en/api/beta/skills`) and `skills/versions` (URL: `https://platform.claude.com/docs/en/api/beta/skills/versions`) | `Audit skills-expert API ref` |
| 8 | `/Users/diego/Dev/managed_agents/.claude/agents/memory-expert.md` | memory is not documented in the public API beta tree at `/api/beta/memory*`. The subagent MUST first verify this by attempting `mcp__exa__crawling_exa` on `https://platform.claude.com/docs/en/api/beta/memory_stores` and `https://platform.claude.com/docs/en/api/beta/memory`. If both return Not Found / empty shell, report the situation under "Upstream gaps" and treat the local file's REST-API-only claims as correct. Do NOT use `get-code-context-exa` to search for memory docs — the expert's own note ("does not yet exist") is authoritative. | `Audit memory-expert` |

Note: subagent 8 (`memory-expert`) is a special case — the prompt text for that one explicitly tells the subagent to handle the "no upstream public API page" case rather than treating empty fetches as failures.

- [ ] **Step 2: Wait for all 8 completion notifications**

Each subagent emits a `<task-notification>` event on completion. The calling conversation collects and reads the reports.

- [ ] **Step 3: No commit yet**

Reports are findings, not commits.

---

### Task 5: Consolidate and present Phase 2 findings

**Files:** None modified. Conversation output only.

- [ ] **Step 1: Aggregate findings into one summary**

When all 8 reports are in, synthesize them into a single message in the main conversation, grouped as:

```
# Phase 2 API-reference audit — consolidated findings

## Clean (no edits needed)
- <expert>: (brief verdict)

## Minor drift (list per expert)
- <expert>: (itemized findings)

## Real bugs
- <expert>: (specific fix)

## Upstream gaps (FYI only)
- <expert>: (observation)
```

- [ ] **Step 2: Ask the user for fix prioritization**

Message the user: "Phase 2 complete — here's the consolidated report. Fix order?" and list real bugs first, then minor drift clusters grouped by expert. Wait for user response before editing any expert files.

- [ ] **Step 3: No commit yet**

---

### Task 6: Apply Phase 2 fixes

**Files:**
- Modify: one or more files under `.claude/agents/*.md` based on findings. Exact files and edits cannot be fully specified in advance — they depend on audit output.

- [ ] **Step 1: For each expert with real bugs, apply fixes**

Open the expert file, apply the specific edit described in the Phase 2 report, and commit. One commit per expert — same pattern used during the CLI audit:

```bash
git add .claude/agents/<expert>.md
git commit -m "$(cat <<'EOF'
Tighten <expert> API reference per upstream audit

<short description of the edits referencing the findings>

Surfaced by docs-auditor schema mode audit of <expert>.md against
https://platform.claude.com/docs/en/api/beta/<resource>.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Verify each commit with git log**

Run: `git log --oneline -<N>` where N is the number of fix commits. Confirm each commit message references the expert file name and cites the audit.

- [ ] **Step 3: For experts with "Upstream gaps (FYI only)" and no local drift, do not edit**

Record the observation in the conversation (user-visible) but do not modify the expert file. These are upstream incompleteness, not local bugs.

---

## Phase 3 — Cross-cutting ecosystem audit

### Task 7: Dispatch the cross-cutting audit subagent

**Files:** None modified. Single subagent dispatch.

- [ ] **Step 1: Dispatch with the cross-cutting audit prompt**

Issue one Agent tool call (`run_in_background: true`) with this prompt:

```
You are running a cross-cutting ecosystem audit against the managed-agents expert system at /Users/diego/Dev/managed_agents/.claude/agents/.

Several concepts span multiple experts or don't have a single domain owner. Your job is to verify the expert system collectively documents each concept somewhere, and to identify which expert should own any gap.

## Source crawls (all one batched call if possible)

Call `mcp__exa__crawling_exa` on these URLs:

1. `https://platform.claude.com/docs/en/api/beta/agents/create` — canonical page with the full tools/skills/permission/beta-headers schema.
2. `https://platform.claude.com/docs/en/api/beta/agents/update` — to confirm the same schema applies on update.
3. `https://platform.claude.com/docs/en/api/beta/sessions/create` — for resource types and gating beta headers.

Together these pages contain the full cross-cutting schema material.

## Checks to perform

For each check, (a) extract the relevant upstream content, (b) grep the local experts for current coverage, (c) classify as "covered / gap / partial", and (d) if gap or partial, name the responsible expert.

1. **Built-in agent toolset**
   - Upstream enumerates 8 built-in tool names under `BetaManagedAgentsAgentToolConfigParams.name`: `bash`, `edit`, `read`, `write`, `glob`, `grep`, `web_fetch`, `web_search`.
   - Verify `tools-expert.md` documents all 8 names.
   - Verify `tools-expert.md` documents both the per-tool `configs` shape and the `default_config` shape.

2. **Permission policies**
   - Upstream defines two types: `BetaManagedAgentsAlwaysAllowPolicy` (type `always_allow`) and `BetaManagedAgentsAlwaysAskPolicy` (type `always_ask`).
   - Verify `tools-expert.md` documents both with correct type strings.

3. **Custom tool schema**
   - Upstream `BetaManagedAgentsCustomToolParams` requires `name` (1-128 chars, `[a-zA-Z0-9_-]`), `description` (1-1024 chars), `input_schema` (JSON Schema with `properties`, `required`, `type: "object"`).
   - Verify `tools-expert.md` documents this shape.
   - Verify the local description of the `agent.custom_tool_use` event loop (agent emits event, session goes idle, client replies with `user.custom_tool_result`) matches the upstream description. This touches `tools-expert` and `events-expert` — note which one owns it and whether both are consistent.

4. **MCP toolset wiring**
   - Upstream `BetaManagedAgentsMCPToolsetParams` requires `mcp_server_name` (must match a server name in `mcp_servers`), `type: "mcp_toolset"`, plus `configs` and `default_config` mirroring the agent-toolset shape.
   - Verify `mcp-vaults-expert.md` (or `tools-expert.md`, whichever owns it locally) documents this shape and the join against `mcp_servers`.

5. **Beta headers catalog (24 values)**
   - Upstream `anthropic-beta` header enumerates all 24 beta values. Extract the full list from the crawl.
   - For each beta value, grep local experts for references and check: (a) that research-preview values are only referenced where the expert documents research-preview-gated features, and (b) that no local references use stale beta values.
   - List any beta value the schema enumerates that is referenced by zero local experts.

6. **Model enum**
   - Upstream `BetaManagedAgentsModel` enumerates all supported model IDs.
   - Verify `agents-expert.md`'s supported-models list matches exactly. Any stale IDs (listed locally but absent upstream) are `Stale`. Any upstream IDs not in local are `Missing`.

7. **Anthropic-managed skills**
   - Upstream `BetaManagedAgentsAnthropicSkillParams.skill_id` references skills by ID (e.g., `xlsx`) with no inline catalog on the create page.
   - Verify `skills-expert.md` either (a) links to a published catalog, or (b) documents that the catalog is unpublished and users must discover skills elsewhere. If neither, flag as a gap.

8. **Research-preview feature gating**
   - Find every `managed-agents-2026-04-01-research-preview` (or similar research-preview header) reference in local experts.
   - Verify each reference gates a specific feature (memory stores in memory-expert, outcome evaluations in sessions-expert, define-outcome events in events-expert, etc.) and that the gating is consistent with upstream.

## Report format

Return a single consolidated report:

```
# Cross-cutting ecosystem audit

## Check 1: Built-in agent toolset
- Status: covered | partial | gap
- Responsible expert: <name>
- Findings: ...

## Check 2: Permission policies
- Status: ...
- ...

## ... (all 8 checks)

## Summary
- Covered: N / 8
- Partial: N / 8
- Gap: N / 8
- Recommended fix order: ...
```

Keep the full report under 800 words — concrete findings, no upstream-content dumps.
```

- [ ] **Step 2: Wait for the completion notification**

The subagent emits a single task-notification when done.

- [ ] **Step 3: No commit yet**

---

### Task 8: Apply Phase 3 fixes

**Files:**
- Modify: one or more files under `.claude/agents/*.md` based on findings. Cannot be fully specified in advance.

- [ ] **Step 1: Review the cross-cutting report with the user**

Present the consolidated report in the main conversation. Ask the user for fix prioritization.

- [ ] **Step 2: For each gap or partial finding with a clear responsible expert, apply fixes**

Pattern per fix: open the target expert file, apply the minimal edit that closes the gap, commit with a message that cites the cross-cutting audit:

```bash
git add .claude/agents/<expert>.md
git commit -m "$(cat <<'EOF'
Close <gap-name> in <expert> per cross-cutting audit

<description of the edit and which cross-cutting check surfaced it>

Surfaced by docs-auditor cross-cutting ecosystem audit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Verify the final expert system state**

Run: `git log --oneline --since "2026-04-15 00:00"` — confirm all audit fixes are present and described accurately. Report to the user a brief summary of Phases 2 + 3 outcomes.

---

### Task 9: Finalize spec

**Files:**
- Modify: `docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md`

- [ ] **Step 1: Mark the spec as fully implemented**

Find:

```
**Status:** Phase 1 implemented (schema mode) — 2026-04-15; Phases 2 and 3 pending
```

Replace with:

```
**Status:** implemented — 2026-04-15
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-15-docs-auditor-api-extension-design.md
git commit -m "$(cat <<'EOF'
Mark docs-auditor API extension spec as fully implemented

All three phases complete:
- Phase 1: schema mode added to docs-auditor
- Phase 2: per-expert API-reference audit + fixes
- Phase 3: cross-cutting ecosystem audit + fixes

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Spec coverage check

- **Phase 1 schema mode** → Task 1 (implementation), Task 2 (smoke test), Task 3 (spec status flip).
- **Phase 2 per-expert audit (8 experts in scope)** → Task 4 (dispatch), Task 5 (consolidation), Task 6 (fix application).
- **Phase 2 memory-expert special case** → Task 4 substitutions table, row 8, explicit prompt handling.
- **Phase 3 cross-cutting audit (8 checks)** → Task 7 (dispatch prompt enumerates all 8 checks), Task 8 (fix application).
- **No run-directory convention** → Task 5 + Task 8 present findings inline in the conversation; no `runs/` writes.
- **Upstream gap caveat** → Task 4 audit-prompt caveats section explicitly carries it over; Task 6 Step 3 codifies "don't edit for upstream gaps."
- **Reuse existing docs-auditor fallback chain** → Task 1 Step 4 schema-mode behavior mirrors section-mode fallback chain (Exa crawl → get-code-context-exa skill → failure string).

No uncovered requirements.

# lead-0 Grounding + research-expert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `lead-0` to ground design drafts against specialist API schemas and validate the draft spec before Phase 2 approval; add a narrow-scope `research-expert` specialist and strip Exa tools from `tools-expert`.

**Architecture:** Edit-only change to the `.claude/agents/` prompt files plus `.claude/CLAUDE.md`. One new agent file, three modified files. No code, no unit tests — behavioral verification is a downstream pipeline run.

**Tech Stack:** Markdown-with-YAML-frontmatter agent prompt files. Verification uses `grep` and `wc -l` against the edited files.

**Spec:** `docs/superpowers/specs/2026-04-13-lead-0-grounding-and-research-expert-design.md`

---

## File Structure

- **Create:** `.claude/agents/research-expert.md` — new specialist for external web research via Exa, with bibliography + dedup behavior.
- **Modify:** `.claude/agents/tools-expert.md` — remove Exa tools from frontmatter, remove any Exa references in body; restores the agent to pure tool-configuration scope.
- **Modify:** `.claude/agents/lead-0.md` — add `Dispatch defaults` section, add `research-expert` to the specialist table, rewrite Phase 2, annotate Phase 1 topic guide with grounding notes, amend the "one design task at a time" invariant, add two rules.
- **Modify:** `.claude/CLAUDE.md` — update specialist count.

---

### Task 1: Create `research-expert.md`

**Files:**
- Create: `.claude/agents/research-expert.md`

- [ ] **Step 1: Verify file does not already exist**

Run: `ls /Users/diego/Dev/managed_agents/.claude/agents/research-expert.md 2>&1`
Expected: `ls: ...research-expert.md: No such file or directory`

- [ ] **Step 2: Write the file**

Create `.claude/agents/research-expert.md` with the following exact content:

```markdown
---
name: research-expert
description: External web research via Exa. Returns structured findings with source, date, and confidence labels.
tools: Read, Write, mcp__exa__web_search_exa, mcp__exa__web_search_advanced_exa, mcp__exa__crawling_exa, mcp__exa__get_code_context_exa
skills: get-code-context-exa
model: sonnet
---

# Research Expert

You are the research-expert subagent. You own external web research for the pipeline. You query the open web via Exa MCP tools, synthesize findings with source attribution, and write structured results into the run directory. You do NOT answer Anthropic API schema questions — those belong to the domain specialists.

## Scope

You are called when lead-0 needs external information: market patterns, benchmark data, competitor designs, open-source templates, code snippets from the wider ecosystem, academic or regulatory background, or anything NOT documented in an Anthropic API reference.

**You refuse these requests and redirect to the right specialist:**

- Anthropic API schemas (agents, environments, sessions, events, files, skills, vaults, memory) → the corresponding `<domain>-expert`.
- Agent tool configuration, built-in toolsets, permission policies → `tools-expert`.
- Multi-agent dispatch semantics, `callable_agents` shape → `multiagent-expert`.

If lead-0 sends a scope-violation request, return a 1-sentence refusal naming the correct specialist.

## Tools

- `mcp__exa__web_search_exa` — general web search
- `mcp__exa__web_search_advanced_exa` — advanced filters (date, domain, text)
- `mcp__exa__crawling_exa` — fetch full page content from a URL
- `mcp__exa__get_code_context_exa` — code snippets and docs from GitHub, Stack Overflow, technical docs

## Output contract

For every research dispatch:

1. Write full findings to `$RUN_DIR/research/<topic>.md` where `<topic>` is a short kebab-case slug of the research question. Each finding has this shape:

   ```markdown
   ## <claim>

   - **Source:** <url>
   - **Date accessed:** <YYYY-MM-DD>
   - **Confidence:** verified | likely | speculative

   <supporting detail or quoted excerpt>
   ```

   Confidence labels:
   - `verified` — primary source (official docs, authoritative publications, code from the library's own repo)
   - `likely` — credible secondary source, multiple corroborating results, or well-regarded third-party content
   - `speculative` — single source, unclear provenance, or inferred

2. Append one line to `$RUN_DIR/research/bibliography.md` for every URL consulted, in the format:

   ```
   YYYY-MM-DD | <topic> | <url>
   ```

   One line per source, not per finding.

3. Return a 1-2 sentence summary to lead-0 referencing the output file path.

## Dedup rule

Before issuing a new Exa query, read `$RUN_DIR/research/bibliography.md`. If an equivalent query or URL was consulted earlier in this run, reference the existing `research/<topic>.md` file in your return summary instead of re-querying. Dedup is best-effort — do not block a legitimate follow-up query that needs different facets.

## Rules

- Return 1-2 sentence summaries to lead-0
- Write verbose output to $RUN_DIR/research/<topic>.md and append to $RUN_DIR/research/bibliography.md
- Refuse scope violations (Anthropic API schema questions) and name the correct specialist
- Every finding has source URL, date accessed, and confidence label
- Never call CLI commands or touch other run directories (design/, provisioned/, validation/)
```

- [ ] **Step 3: Verify file was created with correct frontmatter**

Run: `head -7 /Users/diego/Dev/managed_agents/.claude/agents/research-expert.md`
Expected: YAML frontmatter showing `name: research-expert`, `model: sonnet`, and the four `mcp__exa__*` tools listed.

- [ ] **Step 4: Verify structure matches other specialists**

Run: `grep -c "^## " /Users/diego/Dev/managed_agents/.claude/agents/research-expert.md`
Expected: `5` (Scope, Tools, Output contract, Dedup rule, Rules)

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/research-expert.md
git commit -m "$(cat <<'EOF'
Add research-expert specialist for external web research

Narrow-scope Exa wrapper. Writes structured findings with source,
date, and confidence labels to $RUN_DIR/research/<topic>.md.
Maintains a shared bibliography.md for dedup across dispatches.
Refuses Anthropic API schema questions (redirects to domain
specialists).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Remove Exa tools from `tools-expert.md`

**Files:**
- Modify: `.claude/agents/tools-expert.md` frontmatter (lines 4-5)

- [ ] **Step 1: Verify current state**

Run: `head -7 /Users/diego/Dev/managed_agents/.claude/agents/tools-expert.md`
Expected: shows `tools: Read, Write, Bash, mcp__exa__web_search_exa, mcp__exa__web_search_advanced_exa, mcp__exa__crawling_exa, mcp__exa__get_code_context_exa` and `skills: get-code-context-exa`.

- [ ] **Step 2: Edit frontmatter**

Replace the `tools:` line:
```
tools: Read, Write, Bash, mcp__exa__web_search_exa, mcp__exa__web_search_advanced_exa, mcp__exa__crawling_exa, mcp__exa__get_code_context_exa
```
with:
```
tools: Read, Write, Bash
```

Delete the `skills: get-code-context-exa` line entirely.

- [ ] **Step 3: Verify no Exa references remain anywhere in the file body**

Run: `grep -ni "exa" /Users/diego/Dev/managed_agents/.claude/agents/tools-expert.md`
Expected: empty output (no matches). If any matches appear, remove those references as well.

- [ ] **Step 4: Verify the file still parses (head check)**

Run: `head -10 /Users/diego/Dev/managed_agents/.claude/agents/tools-expert.md`
Expected: valid frontmatter with `tools: Read, Write, Bash`, no `skills:` line, `model: sonnet`, followed by the `---` delimiter and the `# Tools & Permission Policies Expert` heading.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/tools-expert.md
git commit -m "$(cat <<'EOF'
Remove Exa tools from tools-expert

Exa research now lives in the new research-expert specialist.
tools-expert returns to its original scope: agent tool
configuration, permission policies, and MCP toolset references.
Reverts the toolset portion of d33e82b.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: lead-0.md — add `research-expert` to roster and add two new rules

**Files:**
- Modify: `.claude/agents/lead-0.md` (specialist table around line 27, Rules section around line 152)

- [ ] **Step 1: Verify current state of the specialist table**

Run: `grep -n "files-expert" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: shows the `files-expert` row exists (should be the last row of the specialist table at line 27).

- [ ] **Step 2: Add research-expert row after files-expert**

Insert this row immediately after the `files-expert` line in the specialist table:

```
| `research-expert` | External web research via Exa | Looking up external patterns, benchmarks, templates, or code examples not covered by an Anthropic API |
```

- [ ] **Step 3: Add two new bullets to the Rules section at the bottom**

At the end of the `## Rules` section (after the existing last bullet `You do NOT carry API reference docs...`), append these two bullets:

```
- Ground before drafting. For schema-heavy topics (tools, skills, env, vaults, resources, team wiring, persistent data), dispatch the owning specialist to confirm field names before framing follow-up questions to the user. Grounding is a lead-0 internal step, invisible to the user.
- All external web research goes through `research-expert`. Never call Exa tools directly from lead-0. Never dispatch domain specialists for web research.
```

- [ ] **Step 4: Verify both edits landed**

Run: `grep -n "research-expert" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: two matches — one in the specialist table, one in the Rules section.

- [ ] **Step 5: Verify specialist table row count**

Run: `awk '/^\| \`/{c++} END{print c}' /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: `11` (10 existing specialist rows + 1 new `research-expert` row).

- [ ] **Step 6: Commit**

```bash
git add .claude/agents/lead-0.md
git commit -m "$(cat <<'EOF'
Add research-expert to lead-0 roster; add grounding + research rules

Roster row directs external web research to the new specialist.
Two new rules codify the grounding-before-drafting behavior and
the sole-path-for-web-research constraint.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: lead-0.md — add Dispatch defaults section

**Files:**
- Modify: `.claude/agents/lead-0.md` (insert new section immediately before `## Phase 0 — Readiness check`)

- [ ] **Step 1: Locate the insertion point**

Run: `grep -n "^## Phase 0" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: a single match showing the line number of `## Phase 0 — Readiness check`.

- [ ] **Step 2: Insert the Dispatch defaults section**

Immediately before the `## Phase 0 — Readiness check` heading, insert:

```
## Dispatch defaults

- **Parallel by default.** Independent specialist dispatches go in a single message with multiple Agent tool uses. Sequential dispatch is opt-in and requires a data dependency between calls.
- **Grounding dispatches are invisible to the user.** No approval gate, no user-facing design task. Internal `Ground: <domain>` tasks only. Grounding tasks are NOT counted against the "one design task at a time" invariant.
- **Validation dispatches (Phase 2) are parallel.** One message, all relevant specialists, structured return shape (see Phase 2).
- **Specialists return 1-2 sentence summaries.** Verbose output goes to `$RUN_DIR/{research,validation,provisioned}/`.

### Dispatch prompt templates

**Grounding dispatch.** Use this shape when asking a specialist to return its domain schema before framing user questions:

```
Grounding request for topic "<topic>". I am about to ask the user detailed questions about <topic>. Return the verified API schema for the fields the user will need to answer (field names, types, enum values). Do not answer anything the user has not been asked yet. Summary only; no provisioning.
```

**Validation dispatch.** Use this shape at Phase 2, dispatched to every relevant specialist in a single message:

```
Validation request. Read $RUN_DIR/design/agent-specs.json. Validate only the <domain> section against your API reference docs. Return structured summary:
{ domain, fields_total, fields_verified, warnings: [{path, field, issue}], errors: [{path, field, issue}] }
Write detailed report to $RUN_DIR/validation/<domain>.md.
```

**Research dispatch.** Delegate normally — research-expert handles bibliography and dedup internally. Pass the research question and (optionally) the target `$RUN_DIR/research/<topic>.md` filename.

```

- [ ] **Step 3: Verify the section landed above Phase 0**

Run: `grep -B 1 -A 1 "^## Dispatch defaults" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: shows the heading, with the preceding line being blank (or the Phases block).

Run: `grep -n "^## " /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: `## Dispatch defaults` appears immediately before `## Phase 0 — Readiness check` in the section order.

Run: `grep -c "^### Dispatch prompt templates\|Grounding request for topic\|Validation request.*agent-specs" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: `3` (one for the subsection heading, one for the grounding template marker, one for the validation template marker).

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/lead-0.md
git commit -m "$(cat <<'EOF'
Add Dispatch defaults section to lead-0

Codifies parallel-by-default dispatch, invisible grounding tasks,
parallel Phase 2 validation, and the summary-only return contract.
These were implicit before; the retrospective showed they need to
be explicit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: lead-0.md — Phase 1 grounding annotations + task invariant amendment

**Files:**
- Modify: `.claude/agents/lead-0.md` (Phase 1 Task protocol invariant around line 68, Topic guide annotations around lines 72–110)

- [ ] **Step 1: Amend the task invariant**

Find the line:
```
**Invariant:** At most one design task may be `pending` or `in_progress` at a time.
```

Replace with:
```
**Invariant:** At most one task whose `subject` starts with `Design:` may be `pending` or `in_progress` at a time. Grounding tasks (`subject` starting `Ground:`) are not counted against this limit.
```

- [ ] **Step 2: Add grounding annotations to the topic guide**

For each of the following topic guide steps, insert a new italicized line immediately after the bold step heading (before the rest of the step's content). The exact insertion rule: the step currently looks like `N. **Topic** — description...`; after it, on its own new line, add `   _Ground first: dispatch <specialist>._` (note the 3-space indent to align with list continuation).

Steps to annotate:

- Step 6 (Tools): `   _Ground first: dispatch tools-expert and agents-expert in parallel._`
- Step 7 (Permission policies): `   _Ground first: dispatch tools-expert._` (skip if Step 6's grounding already covered this in the same run — lead-0 decides at dispatch time)
- Step 8 (MCP servers): `   _Ground first: dispatch mcp-vaults-expert._`
- Step 9 (Skills): `   _Ground first: dispatch skills-expert._`
- Step 12 (Environment): `   _Ground first: dispatch environments-expert._`
- Step 13 (Resources): `   _Ground first: dispatch files-expert and environments-expert in parallel._`
- Step 15 (Vaults): `   _Ground first: dispatch mcp-vaults-expert._`
- Step 17 (Persistent data): `   _Ground first: dispatch files-expert for file mounts or memory-expert for memory stores, depending on the classification._`

- [ ] **Step 3: Add grounding to the team wiring step**

Find the paragraph that begins `For teams: repeat agent-level questions for each agent...`. Immediately before the `**Caller → callee map**` bullet list, add:

```
_Ground first: dispatch multiagent-expert to confirm callable_agents shape and dispatch-mode enum values before opening the wiring task._

```

- [ ] **Step 4: Verify all grounding annotations landed**

Run: `grep -c "_Ground first:" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: `9` (8 topic-guide steps + 1 team wiring step).

- [ ] **Step 5: Verify the invariant was updated**

Run: `grep -n "Grounding tasks" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: one match in the Invariant paragraph.

- [ ] **Step 6: Commit**

```bash
git add .claude/agents/lead-0.md
git commit -m "$(cat <<'EOF'
Integrate grounding into Phase 1 topic guide

Annotate every schema-heavy topic with a Ground first directive
naming the owning specialist. Amend the single-task invariant to
scope it to Design: tasks, so Ground: tasks can run alongside.
Team wiring gets its own grounding line via multiagent-expert.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: lead-0.md — Phase 2 rewrite

**Files:**
- Modify: `.claude/agents/lead-0.md` (replace the existing Phase 2 section)

- [ ] **Step 1: Locate Phase 2 bounds**

Run: `grep -n "^## Phase " /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: shows the line numbers of Phase 0, Phase 1, Phase 2, Phase 3, Phase 4, Phase 5. Note the line ranges of Phase 2 (from `## Phase 2 — Human approval gate` to the line before `## Phase 3 — Provisioning`).

- [ ] **Step 2: Replace Phase 2 content**

Replace the entire Phase 2 section with:

```
## Phase 2 — Human approval gate

Two-part gate. Do NOT render the spec as prose alone — the user approves against a validation signal, not narrative trust.

### Part A — Validation dispatch (parallel)

Dispatch every specialist whose domain appears in `$RUN_DIR/design/agent-specs.json` in a single message. Each specialist:

1. Reads only its own domain's section(s) of the spec.
2. Validates each field against its API reference docs.
3. Writes a detailed per-field report to `$RUN_DIR/validation/<domain>.md`.
4. Returns a structured summary with this shape:

   ```
   { domain, fields_total, fields_verified, warnings: [{path, field, issue}], errors: [{path, field, issue}] }
   ```

   Plus the usual 1-2 sentence prose summary.

### Part B — User-facing report

Render:

```
Spec validation: <sum_verified>/<sum_total> fields verified against live API schemas
 ✓ agents (12/12)
 ✓ environments (8/8)
 ⚠ vaults (6/7) — 1 warning: <issue>
 ✗ multiagent (3/4) — 1 error: <issue>

Human summary:
<markdown table of the spec>

Approve, or request changes?
```

### Blocking rule

If any specialist reports `errors > 0`:
1. Re-ground the offending field(s) via the owning specialist.
2. Redraft the spec.
3. Re-run validation.
4. Present to the user only after all errors are resolved, or after the second failure on the same field — in which case escalate the raw error to the user and let them decide.

Do not silently loop.

### Updates (existing agent)

For updates, validation also dispatches `agents-expert` with both the current version (fetched from the API) and the proposed changes. The user-facing report gets a "N fields changed" line above the per-domain rollup.

Wait for `approved` or change requests. If changes requested, update inline and re-run Part A.
```

- [ ] **Step 3: Verify Phase 2 contains the key structural markers**

Run: `grep -n "Part A\|Part B\|Blocking rule" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: three matches (Part A, Part B, Blocking rule headings).

Run: `grep -n "fields_verified" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: one match (in the structured return shape).

- [ ] **Step 4: Verify phase order is preserved**

Run: `grep -n "^## Phase " /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md`
Expected: Phase 0, 1, 2, 3, 4, 5 in order with no duplicates.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/lead-0.md
git commit -m "$(cat <<'EOF'
Rewrite Phase 2 as schema-only dry-run validation gate

Replaces the narrative markdown table with a two-part gate:
parallel specialist validation producing structured summaries,
then a user-facing N/M-verified report. Errors block and get
re-grounded; validation bounded to 2 attempts per field before
escalating to the user. Updates include a diff line.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Update `.claude/CLAUDE.md` specialist count

**Files:**
- Modify: `.claude/CLAUDE.md` (Architecture bullet)

- [ ] **Step 1: Verify current state**

Run: `grep -n "domain specialists" /Users/diego/Dev/managed_agents/.claude/CLAUDE.md`
Expected: one match showing `- 9 domain specialists (Sonnet), each carrying full API reference docs for their domain`.

- [ ] **Step 2: Replace the line**

Replace:
```
- 9 domain specialists (Sonnet), each carrying full API reference docs for their domain
```
with:
```
- 10 domain specialists (Sonnet) carrying full API reference docs for their domain, plus 1 research specialist (`research-expert`) for external web research via Exa
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "research-expert" /Users/diego/Dev/managed_agents/.claude/CLAUDE.md`
Expected: one match in the Architecture bullet.

Run: `grep -n "9 domain specialists" /Users/diego/Dev/managed_agents/.claude/CLAUDE.md`
Expected: empty (no matches).

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "$(cat <<'EOF'
Update CLAUDE.md specialist count for research-expert

10 domain specialists + 1 research specialist. Reflects the new
research-expert added to split external web research away from
tools-expert.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: End-to-end structural verification

**Files:** none (read-only checks)

- [ ] **Step 1: All agent files parse (frontmatter present)**

Run:
```bash
for f in /Users/diego/Dev/managed_agents/.claude/agents/*.md; do
  head -1 "$f" | grep -q "^---$" && echo "OK: $f" || echo "MISSING FRONTMATTER: $f"
done
```
Expected: every file prints `OK:`.

- [ ] **Step 2: research-expert exists and is referenced by lead-0**

Run:
```bash
test -f /Users/diego/Dev/managed_agents/.claude/agents/research-expert.md && echo "research-expert file exists"
grep -q "research-expert" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "lead-0 references research-expert"
grep -q "research-expert" /Users/diego/Dev/managed_agents/.claude/CLAUDE.md && echo "CLAUDE.md references research-expert"
```
Expected: all three lines print.

- [ ] **Step 3: tools-expert is fully de-Exa'd**

Run: `grep -ni "exa" /Users/diego/Dev/managed_agents/.claude/agents/tools-expert.md`
Expected: empty output.

- [ ] **Step 4: lead-0 Phase 2 has the new structural markers**

Run:
```bash
grep -q "Part A — Validation dispatch" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "Phase 2 Part A present"
grep -q "Part B — User-facing report" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "Phase 2 Part B present"
grep -q "fields_verified" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "Phase 2 structured shape present"
```
Expected: all three lines print.

- [ ] **Step 5: Dispatch defaults and grounding annotations present**

Run:
```bash
grep -q "^## Dispatch defaults" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "Dispatch defaults section present"
echo -n "Grounding annotations count: "
grep -c "_Ground first:" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md
```
Expected: `Dispatch defaults section present` and `Grounding annotations count: 9`.

- [ ] **Step 6: Invariant was amended**

Run: `grep -q "Grounding tasks.*not counted" /Users/diego/Dev/managed_agents/.claude/agents/lead-0.md && echo "Invariant amended"`
Expected: `Invariant amended`.

- [ ] **Step 7: Git history is clean**

Run: `git log --oneline -10`
Expected: the last 7 commits are the ones created by Tasks 1–7, in order, each with a clear message.

- [ ] **Step 8: No verification commit needed**

If any of Steps 1–7 failed, fix inline and re-run. No commit is created for this task — it's a verification-only task.

---

## Notes for executors

- **No unit tests.** This is a prompt/configuration change. Verification is structural (grep, head, wc) at each task, plus a downstream behavioral test (running the pipeline end-to-end) which is OUT OF SCOPE for this plan.
- **Order matters for Tasks 3–6** — all touch `lead-0.md`. Executing in order keeps commits focused. Merging them into fewer commits is acceptable if an executor prefers, but keep the grep-verification steps.
- **Do not run the pipeline as part of this plan.** Pipeline-run verification is a separate follow-up described in the spec's Testing section.
- **The spec is the source of truth** for intent. If a step is ambiguous, consult `docs/superpowers/specs/2026-04-13-lead-0-grounding-and-research-expert-design.md`.

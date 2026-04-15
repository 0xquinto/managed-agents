# docs-auditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `.claude/agents/docs-auditor.md`, a Sonnet helper agent that returns verbatim sections of `https://platform.claude.com/docs/en/api/cli/beta` for use during manual reviews of the 11 expert agents.

**Architecture:** Single agent-definition file with YAML frontmatter (name, description, tools, skills, model) and a system prompt specifying two modes — `section` (extract one subcommand's upstream docs verbatim) and `coverage` (list upstream subcommands not present in any local agent). Tools: `WebFetch`, `Read`, `Grep`, `mcp__exa__crawling_exa` (fallback), `mcp__exa__web_search_exa`, `mcp__exa__get_code_context_exa`. Skill: `get-code-context-exa`.

**Tech Stack:** Claude Code agent definition format, Anthropic WebFetch tool, Exa MCP tools.

---

## File Structure

- Create: `.claude/agents/docs-auditor.md` — the entire agent definition (frontmatter + system prompt).
- No modifications to other files. The agent is invoked ad-hoc from the main Claude Code conversation; no wiring through `lead-0`, no changes to existing experts, no scripts.

The agent file is written as one cohesive prompt. Fragmenting prompt authoring across multiple commits doesn't help review — the file is reviewed as a whole artifact.

---

### Task 1: Write the docs-auditor agent file

**Files:**
- Create: `.claude/agents/docs-auditor.md`

- [ ] **Step 1: Create the agent file with full contents**

Write the following to `.claude/agents/docs-auditor.md`:

```markdown
---
name: docs-auditor
description: Returns verbatim excerpts from the Anthropic CLI beta docs page so callers can diff local expert-agent files against the live source. Two modes — section (one subcommand) and coverage (list upstream subcommands not covered locally). Dev tooling, not part of the production pipeline.
tools: WebFetch, Read, Grep, mcp__exa__crawling_exa, mcp__exa__web_search_exa, mcp__exa__get_code_context_exa
skills: get-code-context-exa
model: sonnet
---

# Docs Auditor

You are the docs-auditor subagent. You own docs-freshness lookups against the canonical Anthropic CLI beta page. You are dev tooling — the main Claude Code conversation calls you during a manual review of `.claude/agents/*.md` to diff embedded CLI docs against the live source. You do NOT perform the review yourself; you return raw material.

## Source

The single canonical source is:

```
https://platform.claude.com/docs/en/api/cli/beta
```

Never substitute another URL. If the caller asks about a different docs page, refuse with a 1-sentence note.

## Modes

The caller's prompt selects the mode. Infer from the request:

- If the caller names a subcommand (e.g., `ant beta:sessions create`), run **section** mode.
- If the caller asks for a coverage check, gaps, or "which upstream subcommands aren't covered", run **coverage** mode.
- If ambiguous, ask one clarifying question before fetching.

### Mode 1 — section

**Input:** one subcommand identifier (e.g., `ant beta:sessions create`).

**Behavior:**

1. `WebFetch` the canonical URL with a prompt that extracts the named section verbatim — flags, positional args, examples, notes, and any linked `beta:*` variants.
2. If `WebFetch` fails or returns degraded/empty content, fall back to `mcp__exa__crawling_exa` on the same URL.
3. If both fail, return an explicit failure message. Never synthesize content.

**Output:** the raw excerpt, unmodified, plus the section anchor URL. Never paraphrase, never summarize, never reorder. The caller is doing a line-level diff — fidelity is the entire point.

Format:

```
## Upstream section: `ant beta:<subcommand>`
**Source:** <anchor URL>
**Fetched via:** WebFetch | Exa crawl

<verbatim excerpt>
```

### Mode 2 — coverage

**Input:** none, or an explicit "run coverage" trigger.

**Behavior:**

1. `WebFetch` the canonical URL and extract the full list of `ant beta:*` subcommands present upstream.
2. `Grep` `.claude/agents/*.md` for the literal string `ant beta:` to determine which subcommands the local agents already cover.
3. Diff the two sets.

**Output:** a list of upstream subcommands not present in any local agent file, each with a one-line description from upstream and the anchor URL.

Format:

```
## Upstream coverage gaps
**Source:** https://platform.claude.com/docs/en/api/cli/beta
**Fetched via:** WebFetch | Exa crawl

- `ant beta:<subcommand>` — <one-line upstream description> — <anchor URL>
- ...
```

If every upstream subcommand is covered, return a single line: `No gaps — every upstream subcommand appears in at least one local agent file.`

## Tool selection rules

- **Primary:** `WebFetch` on the canonical URL. Use first for both modes.
- **Fallback:** `mcp__exa__crawling_exa` on the same URL if `WebFetch` fails or returns degraded content.
- **Augmentation (explicit only):** `mcp__exa__web_search_exa` and `mcp__exa__get_code_context_exa` are allowed ONLY when the caller explicitly asks for real-world usage examples or when upstream semantics are ambiguous and a working example would clarify intent. Never use these as a substitute for the canonical source.
- Use `Read` and `Grep` only in coverage mode to inspect `.claude/agents/*.md`.

## Verbatim rule

Excerpts from the canonical page are returned **unparaphrased**. Do not rewrite for clarity, do not reorder flags, do not collapse examples. If upstream is ugly, the excerpt is ugly.

## Labeling rule

Content pulled from Exa search or code-context (not from the canonical URL or its Exa crawl) MUST be clearly labeled `external example, not authoritative` in your response. The caller must never confuse augmentation with the canonical source.

## Failure mode

If both `WebFetch` and `mcp__exa__crawling_exa` fail against the canonical URL, return:

```
FAILED to fetch https://platform.claude.com/docs/en/api/cli/beta via WebFetch and Exa crawl. No content returned.
```

Never synthesize content from memory or training data when fetch fails.

## Rules

- Return the formatted output shown above, nothing else — no preamble, no summary, no editorial judgment.
- Never paraphrase the canonical page.
- Never call `ant` CLI commands or touch `runs/` — you are read-only against local files and the upstream URL.
- Refuse requests for any docs URL other than the canonical one, in 1 sentence.
- If the caller asks you to audit an agent or write the report, refuse — that is the caller's job. You only supply raw material.
```

- [ ] **Step 2: Verify the file was written correctly**

Run: `head -10 .claude/agents/docs-auditor.md`
Expected: shows the YAML frontmatter with `name: docs-auditor`, `tools:` line including `WebFetch` and Exa tools, `skills: get-code-context-exa`, `model: sonnet`.

Run: `wc -l .claude/agents/docs-auditor.md`
Expected: roughly 90-110 lines.

---

### Task 2: Smoke test — section mode

**Files:**
- No file changes. This is a live invocation test.

- [ ] **Step 1: Invoke docs-auditor in section mode for a known subcommand**

From the main Claude Code conversation, dispatch the docs-auditor subagent with this prompt:

```
Run section mode for `ant beta:agents create`. Return the full upstream section verbatim.
```

Expected response shape:

```
## Upstream section: `ant beta:agents create`
**Source:** https://platform.claude.com/docs/en/api/cli/beta#<anchor>
**Fetched via:** WebFetch

<verbatim excerpt including flags, args, examples>
```

- [ ] **Step 2: Verify verbatim fidelity**

Manually compare a short passage (e.g., a flag description) from the agent's response against what you see when visiting the URL in a browser. The text should match character-for-character — no paraphrasing, no reordering, no summarization.

If the agent paraphrased, the agent prompt's **Verbatim rule** is not being followed. Tighten the prompt wording and re-run.

- [ ] **Step 3: Verify fallback works (optional, if reachable)**

Dispatch the same agent with a prompt that forces the Exa path (e.g., by asking it to "use the Exa crawl fallback for this request"). Confirm the `Fetched via:` line reads `Exa crawl` and the output shape is otherwise identical.

---

### Task 3: Smoke test — coverage mode

**Files:**
- No file changes. Live invocation test.

- [ ] **Step 1: Invoke docs-auditor in coverage mode**

From the main Claude Code conversation, dispatch the docs-auditor subagent with this prompt:

```
Run coverage mode. List upstream `ant beta:*` subcommands not present in any local agent file under .claude/agents/.
```

Expected response shape:

```
## Upstream coverage gaps
**Source:** https://platform.claude.com/docs/en/api/cli/beta
**Fetched via:** WebFetch

- `ant beta:<subcommand>` — <one-line upstream description> — <anchor URL>
- ...
```

Or, if nothing is missing:

```
No gaps — every upstream subcommand appears in at least one local agent file.
```

- [ ] **Step 2: Spot-check one gap or one non-gap**

Pick one entry from the agent's output (or, if it reports no gaps, pick one upstream subcommand you know is covered). Verify:
- If listed as a gap: `grep -r "ant beta:<subcommand>" .claude/agents/` returns nothing.
- If reported as covered: the same grep returns at least one match.

If the agent misclassified, the grep logic in the prompt needs tightening — re-read the **coverage** section of the agent prompt and clarify the exact grep pattern the agent should use.

---

### Task 4: Commit

**Files:**
- `.claude/agents/docs-auditor.md`

- [ ] **Step 1: Stage and commit**

Run:

```bash
git add .claude/agents/docs-auditor.md
git commit -m "$(cat <<'EOF'
Add docs-auditor helper agent

On-demand lookup specialist that returns verbatim excerpts from the
Anthropic CLI beta docs page. Used during manual reviews of the 11
expert agents to diff embedded CLI docs against the live source.
Two modes — section (one subcommand, verbatim) and coverage (list
upstream subcommands not present in any local agent file).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: single commit, one file changed, ~100 insertions.

- [ ] **Step 2: Verify git state**

Run: `git status`
Expected: working tree clean (or only unrelated pre-existing modifications).

Run: `git log -1 --stat`
Expected: commit message as above, `.claude/agents/docs-auditor.md` listed as the new file.

---

## Spec coverage check

- **Role (docs-freshness auditor, verbatim source)** → Task 1, `# Docs Auditor` + `## Verbatim rule`.
- **Source URL (single canonical)** → Task 1, `## Source`.
- **Mode 1 `section`** → Task 1, `### Mode 1 — section`. Smoke-tested in Task 2.
- **Mode 2 `coverage`** → Task 1, `### Mode 2 — coverage`. Smoke-tested in Task 3.
- **Tool list (WebFetch, Read, Grep, Exa crawl, Exa search, Exa code-context)** → Task 1, frontmatter + `## Tool selection rules`.
- **Skill access (get-code-context-exa)** → Task 1, frontmatter `skills:` field.
- **WebFetch-first, Exa-crawl fallback, explicit-only augmentation** → Task 1, `## Tool selection rules`.
- **Verbatim rule** → Task 1, `## Verbatim rule`.
- **Labeling rule for Exa augmentation** → Task 1, `## Labeling rule`.
- **Failure mode (explicit failure, no synthesis)** → Task 1, `## Failure mode`.
- **Not wired through lead-0, not part of production pipeline** → Task 1, role paragraph + `description` in frontmatter ("Dev tooling, not part of the production pipeline").
- **Out of scope: no auto-editing, no caching, no scheduling, no other URLs** → Task 1, `## Rules` + URL refusal clause.

No uncovered requirements.

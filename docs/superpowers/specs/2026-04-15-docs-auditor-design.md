# docs-auditor — design

**Date:** 2026-04-15
**Status:** approved for planning

## Goal

Provide an on-demand helper agent that the main Claude Code conversation calls during a manual review of the 11 expert agents under `.claude/agents/`. The helper fetches authoritative upstream sections from `https://platform.claude.com/docs/en/api/cli/beta` so the reviewer can diff each expert's embedded CLI/API docs against the live source and produce per-agent freshness reports.

The helper does **not** audit on its own. The reviewer drives the loop and makes editorial calls; the helper is a docs-lookup specialist.

## Non-goals

- No auto-editing of agent files.
- No background scheduling, cron, git hooks, or CI integration.
- No persistent cache across review sessions.
- No coverage of docs outside `https://platform.claude.com/docs/en/api/cli/beta`.

## Architecture

A new Sonnet specialist at `.claude/agents/docs-auditor.md`, invoked from the main Claude Code conversation. It is **not** wired through `lead-0` — this is dev tooling, not part of the production managed-agent provisioning pipeline, so the "only lead-0 spawns subagents" invariant does not apply.

### Tools

- `WebFetch` — primary source for the canonical CLI beta page.
- `Read`, `Grep` — for cross-referencing local agent files in `coverage` mode.
- `mcp__exa__crawling_exa` — fallback when `WebFetch` fails or returns poorly rendered HTML.
- `mcp__exa__web_search_exa`, `mcp__exa__get_code_context_exa` — augmentation when the reviewer asks for real-world usage examples of a flag or when upstream semantics are ambiguous.

### Skills

- `get-code-context-exa` — for fetching code snippets demonstrating CLI usage when explicitly requested.

## Modes

The caller's prompt selects the mode. The agent prompt specifies the input shape and output shape for each.

### Mode 1 — `section`

**Input:** a subcommand identifier (e.g., `ant beta:sessions create`).

**Behavior:** `WebFetch` the canonical URL with a prompt to extract the named section verbatim — including all flags, positional args, examples, notes, and any related `beta:*` variants linked from that section.

**Output:** the raw excerpt, unmodified, plus the URL anchor. Never paraphrase, never summarize, never reorder. The caller is performing a line-level diff against the agent file's embedded docs, so fidelity matters.

If `WebFetch` fails or returns degraded content, fall back to `mcp__exa__crawling_exa` on the same URL. If both fail, return an explicit failure message — do not synthesize content.

### Mode 2 — `coverage`

**Input:** none (or an explicit "run coverage" trigger).

**Behavior:**
1. Fetch the canonical URL.
2. Extract the full list of `ant beta:*` subcommands present upstream.
3. `Grep` `.claude/agents/*.md` for `ant beta:` references to determine which subcommands the local agents already cover.
4. Diff the two sets.

**Output:** a list of upstream subcommands not present in any local agent file, each with a one-line description from upstream and the anchor URL.

### Augmentation (cross-cutting)

When the reviewer's question goes beyond "show me section X" — for example, "what does flag `--foo` actually do in practice?" — the agent may use `get-code-context-exa` or `mcp__exa__web_search_exa` to find real-world examples. These results MUST be clearly labeled in the response as "external example, not authoritative" so the reviewer does not confuse them with the canonical source.

## Review flow (driven from main conversation)

The reviewer drives this loop manually; the helper is invoked per step.

1. `mkdir -p runs/$RUN_ID/agent-audits`
2. For each of the 11 experts:
   - Read the agent file.
   - Identify which `ant beta:*` subcommands it owns.
   - Dispatch `docs-auditor` in `section` mode for each owned subcommand. These dispatches can run in parallel since each is independent.
   - Diff upstream excerpt vs. embedded docs.
   - Write `runs/$RUN_ID/agent-audits/<agent>.md` with three buckets:
     - **Stale** — agent text contradicts current upstream (e.g., flag renamed, default changed).
     - **Missing** — upstream has flags, args, notes, or examples the agent file lacks.
     - **Inaccurate** — agent makes a claim upstream refutes.
   - Each entry quotes both sides and includes line refs into the agent file.
3. One final `docs-auditor` call in `coverage` mode → `runs/$RUN_ID/agent-audits/_coverage.md` listing uncovered upstream subcommands.

## Output format

Per-agent report (`runs/$RUN_ID/agent-audits/<agent>.md`):

```markdown
# <agent-name> — docs freshness audit
**Reviewed:** YYYY-MM-DD
**Subcommands covered:** ant beta:foo, ant beta:bar
**Source:** https://platform.claude.com/docs/en/api/cli/beta

## Stale
- **`ant beta:foo --bar`** (agent line 42)
  - Agent says: "..."
  - Upstream says: "..."
  - Suggested edit: ...

## Missing
- ...

## Inaccurate
- ...
```

Coverage report (`runs/$RUN_ID/agent-audits/_coverage.md`):

```markdown
# Upstream coverage gaps
**Reviewed:** YYYY-MM-DD
**Source:** https://platform.claude.com/docs/en/api/cli/beta

- **`ant beta:newthing`** — <one-line upstream description> — no local agent covers this.
- ...
```

## Agent prompt structure

`.claude/agents/docs-auditor.md` contains:

1. **Role** — "Docs freshness auditor for Anthropic CLI beta. Returns verbatim upstream excerpts so the caller can diff against local agent files."
2. **Source URL** — the single canonical URL.
3. **Mode contract** — input/output shape for `section` and `coverage`.
4. **Tool selection rules** — `WebFetch` first, Exa crawl fallback, Exa search/code-context only on explicit augmentation request.
5. **Verbatim rule** — never paraphrase or summarize the canonical page.
6. **Labeling rule** — Exa-derived content must be flagged as "external example, not authoritative."
7. **Failure mode** — if both `WebFetch` and `mcp__exa__crawling_exa` fail, return an explicit failure; never synthesize.

## Out of scope

- Auto-applying suggested edits to agent files.
- Caching across review sessions.
- Scheduling / background execution.
- Auditing docs sources other than the canonical CLI beta page.
- Validating non-CLI portions of expert agents (e.g., the operational rules sections).

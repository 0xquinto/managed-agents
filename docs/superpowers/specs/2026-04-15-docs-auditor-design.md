# docs-auditor — design

**Date:** 2026-04-15 (revised after smoke-test findings)
**Status:** approved for planning

## Goal

Provide an on-demand helper agent that the main Claude Code conversation calls during a manual review of the 11 expert agents under `.claude/agents/`. The helper fetches authoritative upstream content from the Anthropic CLI beta docs at `https://platform.claude.com/docs/en/api/cli/beta/*` so the reviewer can diff each expert's embedded CLI/API docs against the live source and produce per-agent freshness reports.

The helper does **not** audit on its own. The reviewer drives the loop and makes editorial calls; the helper is a docs-lookup specialist.

## Non-goals

- No auto-editing of agent files.
- No background scheduling, cron, git hooks, or CI integration.
- No persistent cache across review sessions.
- No coverage of docs outside the `https://platform.claude.com/docs/en/api/cli/beta/*` tree.

## Architecture

A new Sonnet specialist at `.claude/agents/docs-auditor.md`, invoked from the main Claude Code conversation. It is **not** wired through `lead-0` — this is dev tooling, not part of the production managed-agent provisioning pipeline, so the "only lead-0 spawns subagents" invariant does not apply.

### Source structure (discovered at smoke test)

The canonical docs are a **tree** of per-subcommand pages, not a single URL:

- Per-subcommand content: `https://platform.claude.com/docs/en/api/cli/beta/<domain>/<action>` (e.g., `/cli/beta/agents/create`). Nested domains use additional path segments (`/cli/beta/sessions/events/send`).
- Sitemap: `https://platform.claude.com/sitemap.xml` lists every path exhaustively.

**JS-rendering caveat:** per-subcommand pages are Next.js SPAs whose raw HTML contains only "Loading…" placeholders. `WebFetch` and plain HTTP fetches return empty shells. Content is only extractable via `mcp__exa__crawling_exa` (which handles JS rendering) or the `get-code-context-exa` skill (semantic search + retrieval).

**Sitemap caveat (discovered at second smoke test):** the sitemap is plain XML. `mcp__exa__crawling_exa` rejects it with `CRAWL_UNEXPECTED_CONTENT_TYPE`. `WebFetch` mangles it through HTML-to-markdown conversion and reports zero matches for `/cli/beta/` entries that are demonstrably present when fetched with `curl`. The only reliable fetcher is plain HTTP via `Bash` + `curl`.

### Tools

- `Bash` — sitemap fetch only (`curl -s https://platform.claude.com/sitemap.xml`). Scoped in the agent prompt to this single use; no other shell commands permitted.
- `Read`, `Grep` — for cross-referencing local agent files in coverage mode.
- `mcp__exa__crawling_exa` — primary fetcher for per-subcommand pages.
- `mcp__exa__web_search_exa` — augmentation only, default OFF, requires explicit caller request.
- `mcp__exa__get_code_context_exa` — listed for tool permission, but the agent invokes it via the skill (below), not directly.

### Skills

- `get-code-context-exa` — section-mode fallback. Used when `mcp__exa__crawling_exa` returns "Not Found" or truncated content. The skill wraps query-construction and result-interpretation guidance around the underlying `mcp__exa__get_code_context_exa` tool.

## Modes

The caller's prompt selects the mode. The agent prompt specifies the input shape and output shape for each.

### Mode 1 — section

**Input:** one subcommand identifier in `ant beta:<domain>[:<sub>]:<action>` form (e.g., `ant beta:agents:create`).

**Behavior:**

1. Convert the identifier to a URL under `https://platform.claude.com/docs/en/api/cli/beta/<domain>/<action>`.
2. Call `mcp__exa__crawling_exa` with that URL.
3. If the crawl returns "Not Found" or content that is empty/truncated, fall back to the `get-code-context-exa` skill with a query naming the subcommand.
4. If both fail, return the failure string. Never synthesize content.

**Output:** the raw excerpt, unmodified, plus the URL. Never paraphrase, summarize, or reorder — the caller is performing a line-level diff.

If the named subcommand is not present upstream (crawl "Not Found" AND skill returns nothing authoritative), return:
`NOT FOUND: \`ant beta:<subcommand>\` is not documented at <url>`

### Mode 2 — coverage

**Input:** none, or an explicit "run coverage" trigger.

**Behavior:**

1. Fetch the sitemap via `Bash`: `curl -s https://platform.claude.com/sitemap.xml` (the only sanctioned shell command).
2. Extract `<loc>` entries matching `/docs/en/api/cli/beta/<path>`. Keep only **leaf** URLs (drop domain-index URLs whose children are also present).
3. Convert each URL path to a subcommand token: `/cli/beta/agents/create` → `ant beta:agents:create`; `/cli/beta/sessions/events/send` → `ant beta:sessions:events:send`.
4. Partition the upstream set by an **in-scope whitelist** of top-level domains our pipeline owns:
   `agents, environments, files, sessions, skills, vaults`.
   Everything else (e.g., `messages`, `models`) is out-of-scope — these are standard API CLI subcommands, not managed-agents concerns.
5. `Grep` `.claude/agents/*.md` with regex `ant beta:[a-z0-9:_-]+` (case-sensitive) to collect locally-referenced tokens. Exclude negation-context matches (prohibitions / refuse directives) by scanning the surrounding line.
6. Diff: (in-scope upstream) minus (local) = **in-scope gaps**. Out-of-scope upstream is reported as FYI regardless of local presence.

**Output:** two sections grouped under a single report — `### In-scope gaps (need fixing)` and `### Out-of-scope upstream (FYI)`. The FYI section is always present, even if empty of meaningful action.

### Augmentation (cross-cutting)

When the reviewer explicitly asks for real-world usage examples (not just "show me section X"), the agent may use `mcp__exa__web_search_exa`. Skill-derived and augmentation content MUST be labeled `augmentation, not canonical crawl` in the response so the reviewer never confuses it with a direct canonical-source fetch.

## Review flow (driven from main conversation)

The reviewer drives this loop manually; the helper is invoked per step.

1. `mkdir -p runs/$RUN_ID/agent-audits`
2. For each of the 11 experts:
   - Read the agent file.
   - Identify which `ant beta:*` subcommands it owns.
   - Dispatch `docs-auditor` in `section` mode for each owned subcommand. Dispatches can run in parallel.
   - Diff upstream excerpt vs. embedded docs.
   - Write `runs/$RUN_ID/agent-audits/<agent>.md` with three buckets: **Stale**, **Missing**, **Inaccurate**. Each entry quotes both sides and includes line refs into the agent file.
3. One final `docs-auditor` call in `coverage` mode → `runs/$RUN_ID/agent-audits/_coverage.md` listing uncovered upstream subcommands (grouped in-scope / out-of-scope).

## Output format

Per-agent report (`runs/$RUN_ID/agent-audits/<agent>.md`):

```markdown
# <agent-name> — docs freshness audit
**Reviewed:** YYYY-MM-DD
**Subcommands covered:** ant beta:foo, ant beta:bar
**Source tree:** https://platform.claude.com/docs/en/api/cli/beta/*

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
**Source:** https://platform.claude.com/sitemap.xml

## In-scope gaps (need fixing)
- **`ant beta:<subcommand>`** — <one-line upstream description> — <url>
- ...

## Out-of-scope upstream (FYI)
- **`ant beta:messages:create`** — <one-line upstream description> — <url>
- ...
```

## Agent prompt structure

`.claude/agents/docs-auditor.md` contains:

1. **Role** — "Docs freshness auditor for Anthropic CLI beta. Returns verbatim upstream excerpts so the caller can diff against local agent files."
2. **Sources** — per-subcommand URL pattern + sitemap URL; JS-rendering caveat.
3. **Mode contract** — input/output shape for `section` and `coverage`.
4. **Tool selection rules** — Exa crawl primary for section, skill fallback, Bash+curl for sitemap only.
5. **Verbatim rule** — never paraphrase canonical content.
6. **Labeling rule** — skill/search-derived content must be flagged `augmentation, not canonical crawl`.
7. **Failure mode** — explicit failure string, never synthesize.

## Out of scope

- Auto-applying suggested edits to agent files.
- Caching across review sessions.
- Scheduling / background execution.
- Auditing docs sources other than the `cli/beta/*` tree.
- Validating non-CLI portions of expert agents (e.g., API reference bodies, operational rules sections).

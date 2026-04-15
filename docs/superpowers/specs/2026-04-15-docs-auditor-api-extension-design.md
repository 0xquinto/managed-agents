# docs-auditor API extension — design

**Date:** 2026-04-15
**Status:** approved for planning
**Supersedes partially:** 2026-04-15-docs-auditor-design.md (extends, does not replace)

## Goal

Extend docs-auditor and run a follow-up audit so the 11 expert agents in `.claude/agents/` have everything they need to design and provision Managed Agents correctly — CLI flags, API schema, and the surrounding ecosystem (built-in tools, permission policies, beta headers, Anthropic-managed skills, research-preview features).

The existing CLI audit already confirmed correctness of `## CLI Commands` blocks. This extension closes the remaining gaps: the `## API Reference` prose in each expert, and cross-cutting concepts that aren't CLI-shaped.

## Non-goals

- No changes to the existing `section` or `coverage` modes of docs-auditor.
- No docs-quality rewriting based on taste (we only fix things that contradict or omit upstream).
- No auto-editing of expert files. The caller applies fixes manually after reviewing findings.
- No coverage of docs outside `platform.claude.com/docs/en/api/beta/*` and a short list of high-level managed-agents docs pages enumerated in Phase 3.

## Discovered upstream shape

The non-CLI API reference tree `https://platform.claude.com/docs/en/api/beta/<resource>/<action>` mirrors the CLI tree 1:1 at the resource/action level. Key observations from probing:

1. **Schema content is language-agnostic.** The docs site renders a language selector (cURL / CLI / TypeScript / Python / Java / Go / Ruby / C#) that swaps only the `### Example` code block at the bottom. Header Parameters, Body Parameters, and Returns blocks render identically regardless of selection. `mcp__exa__crawling_exa` captures all of this in one call.
2. **API pages are strictly richer than CLI pages** for the same endpoint. They include full nested type definitions, enumeration of all union members (beta headers, model IDs, tool identifiers, permission policies), and response shapes with every field.
3. **The sitemap enumerates the API tree exhaustively** — same format as the CLI tree, already reachable via the existing coverage-mode pipeline.

## Architecture

Three phases. Each produces artifact(s) and is independently reviewable.

### Phase 1 — Add `schema` mode to docs-auditor

A new mode in `.claude/agents/docs-auditor.md` that pairs with existing `section` and `coverage`.

**Input:** a resource-action identifier in `ant beta:<domain>[:<sub>]:<action>` form — same shape as section mode.

**Behavior:**
1. Convert the identifier to a URL under `https://platform.claude.com/docs/en/api/beta/<domain>/<action>` (note the tree is `/api/beta/` without `cli/`).
2. Call `mcp__exa__crawling_exa` with that URL.
3. Fallbacks mirror the existing section mode: `get-code-context-exa` skill, then explicit failure string.

**Output:** the verbatim API schema excerpt (Header Parameters, Body Parameters, Returns, Example), plus the URL. Same verbatim rule as section mode — no paraphrasing.

**Mode selection rules update:** the caller says "schema mode" or "API reference" or passes the mode explicitly. If the caller says only "the docs for X", prefer `schema` mode when the caller's intent is to verify request/response shape, and `section` when they want to verify CLI flags. If ambiguous, ask one clarifying question.

### Phase 2 — Per-expert API-reference audit

Run an audit pass identical in shape to the CLI audit we just completed, but targeting the `## API Reference` section of each of the 7 CLI-owning experts plus `memory-expert`.

For each expert, a subagent:
1. Reads the expert file.
2. Calls `mcp__exa__crawling_exa` on the API-tree resource-index URL (e.g., `https://platform.claude.com/docs/en/api/beta/agents`) to get all actions for that resource in one crawl, plus the `/api/beta/<resource>/<action>` pages as needed for detail.
3. Compares the expert's `## API Reference` body against the crawled schema.
4. Classifies findings into:
   - **Stale:** local prose contradicts upstream schema (e.g., field renamed, constraint changed, enum shrank).
   - **Missing:** upstream has required fields, constraints, or response shapes the expert doesn't document but would need to reason about.
   - **Inaccurate:** local claims something upstream refutes.
5. Applies the same **upstream gap** caveat we used in the CLI audit — content in the expert that isn't on the upstream API page is NOT drift if it's a documented research-preview feature (e.g., `memory_store` resource type, `outcome_evaluations`) or a CLI-only convenience.
6. Returns a compact report (under 400 words) with the same bucket shape as the CLI audit.

Experts in scope for Phase 2:
- `agents-expert` (resource: `agents`, plus `agents/versions`)
- `environments-expert` (`environments`)
- `events-expert` (`sessions/events`)
- `files-expert` (`files`)
- `mcp-vaults-expert` (`vaults`, `vaults/credentials`)
- `sessions-expert` (`sessions`, `sessions/resources`)
- `skills-expert` (`skills`, `skills/versions`)
- `memory-expert` — special case: no public API page confirmed; audit result may be "upstream not published" (document the gap, don't invent content).

### Phase 3 — Cross-cutting ecosystem audit

Phase 2 audits experts against their own domain. Phase 3 audits the whole expert system against concepts that span multiple experts or don't have a single domain owner.

A single subagent runs the following checks against a carefully scoped set of upstream pages:

1. **Built-in agent toolset** — crawl `/api/beta/agents/create`; extract the full `BetaManagedAgentsAgentToolset20260401Params` union. Verify `tools-expert` documents all 8 built-in tool names (`bash, edit, read, write, glob, grep, web_fetch, web_search`), both permission policy types (`always_allow`, `always_ask`), and the per-tool/default-config shape.
2. **Custom tool schema** — from the same crawl, verify `tools-expert` documents the `BetaManagedAgentsCustomToolParams` shape (name, description, input_schema with properties/required/type).
3. **MCP toolset wiring** — verify `mcp-vaults-expert` OR `tools-expert` (whichever owns it) documents the `BetaManagedAgentsMCPToolsetParams` shape and its relationship to `mcp_servers` configured on the agent.
4. **Beta headers catalog** — extract the 24 enumerated beta header values from the schema. Verify any expert that conditionally gates behavior on a beta header (e.g., research-preview features in sessions-expert) references the correct header value.
5. **Model enum** — verify `agents-expert` lists all currently-supported model IDs per upstream, with no stale IDs.
6. **Anthropic-managed skills catalog** — the schema references Anthropic-managed skills by `skill_id` (e.g., `xlsx`). There may or may not be a public catalog page listing available skill IDs. If one exists, verify `skills-expert` references it; if not, note that the ecosystem catalog is unpublished (not our bug to fix).
7. **Research-preview feature gating** — cross-reference any `managed-agents-2026-04-01-research-preview` references in experts against upstream; ensure the gating note is present wherever the feature is documented.

Output: a single consolidated report grouped by check, with findings routed to the responsible expert when applicable.

## Tools used

- `mcp__exa__crawling_exa` for all content fetches.
- `Read`, `Grep` for local file inspection.
- `get-code-context-exa` skill as fallback (inherited from docs-auditor).
- No new tools required. No changes to the agent's tool list from the existing design.

## Review flow

Driven from the main Claude Code conversation after Phase 1 lands:

1. Phase 1: single commit adding `schema` mode, plus spec update. Smoke-test by invoking `schema` mode for `ant beta:agents:create` and verifying verbatim output.
2. Phase 2: 8 parallel per-expert auditor subagents. Consolidate findings into a single summary message, discuss with user, apply fixes as commits.
3. Phase 3: 1 subagent for the cross-cutting audit. Apply fixes as commits.

No run directories — findings reported inline (same convention adopted during the CLI audit).

## Findings presentation

Per-expert and cross-cutting reports follow the same format established in the CLI audit:

```
# <expert>.md — API reference audit

## Stale
- ...

## Missing
- ...

## Inaccurate
- ...

## Upstream gaps (FYI, not agent bugs)
- ...

## Verdict
One sentence.
```

Cross-cutting report is grouped by check rather than by expert, with an explicit "responsible expert" per finding.

## Out of scope

- Auto-applying fixes to expert files.
- Extending to non-managed-agents docs (Messages API, Models API — these are covered by the CLI audit's out-of-scope tagging and remain out of scope here).
- Auditing docs quality / prose style where semantics are correct.
- Building a permanent skill/tool catalog browser — the audit surfaces the current enumeration; ongoing freshness is the whole point of having docs-auditor.
- A `completeness` mode that crawls outside the `/api/beta/*` tree (e.g., conceptual guides). Deferred — if Phase 3 finds that conceptual docs are load-bearing, a follow-up spec can tackle them.

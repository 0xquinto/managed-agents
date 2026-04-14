# Managed Agent Orchestrator

## Project

A Claude Code agent pipeline that guides a developer through designing, provisioning, and smoke-testing Claude Managed Agents via the Anthropic API. Terminal-driven, no web UI.

## Architecture

- `lead-0` (Opus) is the ONLY agent that spawns subagents
- 10 domain specialists (Sonnet) carrying full API reference docs for their domain, plus 1 research specialist (`research-expert`) for external web research via Exa
- Specialists return 1-2 sentence summaries; verbose output goes to `$RUN_DIR/`

## Credential handling

The API key is invisible to the agent layer. The `ant` CLI is the only auth boundary.

```
  Environment ($ANTHROPIC_API_KEY)
           |
           v
      +---------+
      | ant CLI  |  <-- only thing that touches the key
      +---------+
           |
           v
    Anthropic API
```

- The `ant` CLI reads `$ANTHROPIC_API_KEY` from the environment automatically
- Agents use the CLI exclusively for all API calls — no curl with auth headers
- Phase 0 validates the key with a real API call (`ant beta:agents list --limit 1`), not echo
- The API key is NEVER printed to stdout, written to files, or passed as a command argument
- OAuth tokens, access tokens, refresh tokens, and client secrets are NEVER written to files
- MCP credentials flow through the Vaults API server-side; only vault IDs appear locally

## Invariants

- Never provision agents without user approval (Phase 2 gate is mandatory)
- Never write to `runs/` root — always write under `runs/$RUN_ID/`
- Never start Phase 4 (smoke test) before Phase 3 (provisioning) completes
- Provisioning respects dependency order: files -> vaults -> skills -> agents || environments -> sessions
- For teams: design all agents before provisioning any
- Each specialist only calls CLI commands within its own domain
- All API requests require the `managed-agents-2026-04-01` beta header

## Run directory

All run output goes under `runs/$RUN_ID/` where RUN_ID is ISO 8601 with colons replaced by dashes. The `runs/latest` symlink points to the most recent run.

## Agent files

System prompts live in `.claude/agents/`. Each specialist's prompt contains:
1. Role description
2. Full CLI `--help` output for its commands
3. Full API reference docs for its domain
4. Operational rules

# Managed Agent Orchestrator

## Project

A Claude Code agent pipeline that guides a developer through designing, provisioning, and smoke-testing Claude Managed Agents via the Anthropic API. Terminal-driven, no web UI.

## Commands

```bash
# Lint all actor prompts (CI runs this on every PR touching prompts)
python lint/prompt_lint.py
python lint/prompt_lint.py --no-default-excludes  # include frozen v1 + runs/

# Score an eval case from a captured run dir (single trial, smoke-grade)
python evals/score.py ingestion/tafi_2025 --run runs/latest/smoke/

# Multi-trial aggregate scoring (measurement-grade, Wilson 95% CIs)
python evals/score.py ingestion/tafi_2025 --trials evals/runs/<ts>-<case>-<agent>/trials/

# Live trial loop (uploads files → creates session → fires kickoff → captures outputs)
python evals/runner.py ingestion/tafi_2025 --help

# Coverage matrix between behavior-auditor probes and citing lint rules
python lint/audit_coverage.py

# Convert a behavior-auditor drift report into rule scaffolds under lint/proposed/
python lint/from_audit.py runs/behavior-drift/<ISO>.md
```

## Repository layout

- `.claude/agents/` — orchestrator subagent prompts (lead-0, 11 expert specialists, 2 dev-tooling auditors).
- `agents/<role>/v*_system_prompt.md` — versioned managed-agent system prompts. Committed for diffing + paired A/B tests; the deployed agent's `system` field on the platform is the source of truth.
- `evals/<role>/<case>/` — eval slices per agent role (`spec.md`, `factsheet.md`, `expected.json`, `resources.json`, `kickoff_v*.json`). Run via `evals/runner.py` + `evals/score.py`.
- `lint/` — prompt lint (R001–R006), schema (`lint/schema.md`), and the behavior-auditor → lint pipeline (`audit_coverage.py`, `from_audit.py`). Run on every PR via `.github/workflows/lint.yml`.
- `runs/$RUN_ID/` — orchestrator run artifacts (gitignored). `runs/behavior-drift/<ISO>.md` is the weekly remote-routine output.
- `docs/` — Anthropic API reference docs that specialists pull from.

## Architecture

- `lead-0` (Opus) is the ONLY agent that spawns subagents.
- 11 specialists (Sonnet): 10 platform-domain experts (agents, environments, events, files, mcp-vaults, memory, multiagent, sessions, skills, tools) carrying full CLI/API reference docs for their domain, plus 1 research specialist (`research-expert`) using Exa.
- 2 dev-tooling agents (NOT part of the production pipeline): `docs-auditor` (prompts↔upstream-docs drift), `behavior-auditor` (prompts↔platform-reality drift via live API probes). Both run as scheduled remote routines.
- Specialists return 1-2 sentence summaries; verbose output goes to `$RUN_DIR/`.

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

## Drift prevention loop

`behavior-auditor` weekly probes find platform↔prompt drift; `lint/from_audit.py` converts drift findings into proposed lint rules; `lint/audit_coverage.py` verifies every probe has at least one citing rule. See `lint/README.md` for the full diagram.

## Conventions (recurring gotchas)

- `agents/insignia_ingestion/v1_system_prompt.md` and `runs/` are frozen baselines — lint errors there are intentional; do NOT "fix" them (would invalidate the v1↔v2 paired-McNemar A/B). See `lint/DEFAULT_EXCLUDES` in `lint/prompt_lint.py`.
- Branch + PR + squash-merge for every change. Do NOT push directly to `main`.
- Production-resource mutations (`ant beta:agents create|update`, `ant beta:environments create|delete`, `ant beta:vaults *`, etc.) need explicit action-naming authorization — generic "proceed" or "yes" is treated as too broad by the harness.
- `agents/<role>/CHANGELOG.md` is the local diffable artifact for prompt versions; the deployed `system` field on the platform is the source of truth — read both when investigating prompt behavior.
- Always `git add <specific paths>`. Never `git add .` or `-A` — adjacent untracked files include `.DS_Store`, `docs/api-reference/`, and pitch decks.

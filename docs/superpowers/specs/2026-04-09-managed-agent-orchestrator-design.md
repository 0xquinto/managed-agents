# Managed Agent Orchestrator — Design Spec
*Date: 2026-04-09*

## Purpose

A Claude Code agent pipeline that guides a developer through designing, provisioning, and smoke-testing Claude Managed Agents via the Anthropic API. Entirely terminal-driven; no web UI. Same structural patterns as the job-research pipeline (lead + subagents, run-scoped directories, summary-only returns, CLAUDE.md contract), with **one specialist agent per documentation domain** so each agent carries the full API reference for its area.

---

## Architecture

### Agents

| # | Agent | Model | Domain | Docs source |
|---|---|---|---|---|
| 0 | `lead-0` | Opus | Design dialogue + orchestration | Routing table only |
| 1 | `agents-expert` | Sonnet | Agent definitions CRUD, versioning, model config, system prompts, callable_agents | [agent-setup](https://platform.claude.com/docs/en/managed-agents/agent-setup) |
| 2 | `environments-expert` | Sonnet | Container config, packages, networking, lifecycle | [environments](https://platform.claude.com/docs/en/managed-agents/environments) |
| 3 | `sessions-expert` | Sonnet | Session lifecycle, resource mounting, metadata, vault references | [sessions](https://platform.claude.com/docs/en/managed-agents/sessions) |
| 4 | `events-expert` | Sonnet | SSE streaming, all event types, interrupts, custom tool handling, stop reasons | [events-and-streaming](https://platform.claude.com/docs/en/managed-agents/events-and-streaming) |
| 5 | `tools-expert` | Sonnet | Built-in toolset config, custom tools, permission policies | [tools](https://platform.claude.com/docs/en/managed-agents/tools), [permission-policies](https://platform.claude.com/docs/en/managed-agents/permission-policies) |
| 6 | `multiagent-expert` | Sonnet | callable_agents, session threads, coordinator pattern, thread events | [multi-agent](https://platform.claude.com/docs/en/managed-agents/multi-agent) |
| 7 | `skills-expert` | Sonnet | Skill CRUD, versioning, Anthropic vs custom skills | [skills](https://platform.claude.com/docs/en/managed-agents/skills) |
| 8 | `mcp-vaults-expert` | Sonnet | MCP server declaration, vault CRUD, credential management, OAuth flows | [mcp-connector](https://platform.claude.com/docs/en/managed-agents/mcp-connector), [vaults](https://platform.claude.com/docs/en/managed-agents/vaults) |
| 9 | `files-expert` | Sonnet | File upload, download, metadata, lifecycle | CLI: `ant beta:files` |

`lead-0` is the only agent that spawns subagents. No nested spawning. Subagents return 1–2 sentence summaries; all verbose output goes to `$RUN_DIR/`.

### CLI commands per specialist

| Specialist | CLI commands |
|---|---|
| `agents-expert` | `ant beta:agents {create,retrieve,update,list,archive}`, `ant beta:agents:versions list` |
| `environments-expert` | `ant beta:environments {create,retrieve,update,list,delete,archive}` |
| `sessions-expert` | `ant beta:sessions {create,retrieve,update,list,delete,archive}`, `ant beta:sessions:resources {add,retrieve,update,list,delete}` |
| `events-expert` | `ant beta:sessions:events {send,list,stream}` |
| `tools-expert` | (configured on agents via `--tool` flag, no standalone CLI resource) |
| `multiagent-expert` | (configured on agents via `callable_agents`, threads via sessions API) |
| `skills-expert` | `ant beta:skills {create,retrieve,list,delete}`, `ant beta:skills:versions {create,retrieve,list,delete}` |
| `mcp-vaults-expert` | `ant beta:vaults {create,retrieve,update,list,delete,archive}`, `ant beta:vaults:credentials {create,retrieve,update,list,delete,archive}` |
| `files-expert` | `ant beta:files {upload,download,retrieve-metadata,list,delete}` |

### System prompt structure

Each specialist's system prompt follows this template:

```
You are the [domain] specialist for the Managed Agents orchestrator.

## Your role
[1-2 sentences about what you do]

## CLI commands you own
[exact `ant beta:*` commands with all flags from `--help`]

## API reference
[full docs content for your domain — endpoints, schemas, fields, examples]
[CLI examples only — no curl with auth headers]

## Rules
- Return 1-2 sentence summaries to lead-0
- Write verbose output (API responses, full specs) to $RUN_DIR/
- Never call endpoints outside your domain
- All requests require the managed-agents-2026-04-01 beta header
```

Credential rules are centralized in CLAUDE.md, not repeated per specialist.

The docs content fetched from the live pages is what goes into each system prompt — the actual reference, not a summary.

### lead-0 system prompt

`lead-0` does NOT carry full API reference docs. It carries a **routing table**:

```
## Available specialists

| Specialist | Owns | Call when |
|---|---|---|
| agents-expert | beta:agents, beta:agents:versions | Creating/updating agent definitions |
| environments-expert | beta:environments | Setting up containers, packages, networking |
| sessions-expert | beta:sessions, beta:sessions:resources | Starting sessions, mounting repos/files |
| events-expert | beta:sessions:events | Sending messages, streaming, handling responses |
| tools-expert | (agent tool config) | Configuring built-in/custom/MCP tools |
| multiagent-expert | (callable_agents, threads) | Setting up agent teams |
| skills-expert | beta:skills, beta:skills:versions | Attaching domain skills |
| mcp-vaults-expert | beta:vaults, beta:vaults:credentials | MCP server auth, credential management |
| files-expert | beta:files | Uploading/downloading files |
```

This keeps lead-0's context window free for multi-turn design dialogue and orchestration decisions.

---

## Pipeline Phases

```
Phase 0   Readiness check (lead-0)
Phase 1   Design dialogue (lead-0, direct with user)
Phase 2   Human approval gate
Phase 3   Provisioning (lead-0 dispatches specialists as needed)
Phase 4   Smoke test (lead-0 dispatches events-expert)
Phase 5   Summary (lead-0)
```

### Phase 0 — Readiness check

`lead-0` runs these checks before any work:

1. `ant --version` — CLI installed
2. `ant beta:agents list --limit 1` — validates API key exists, is valid, and has managed agents access

On any failure: print a clear error message with fix instructions, abort.

### Phase 1 — Design dialogue

`lead-0` interviews the user one question at a time. Questions cover:

1. **Name** — what to call the agent
2. **Purpose** — one-sentence description of what it does
3. **Single agent or team?** — if team, how many and what roles
4. **Model** — Opus / Sonnet / Haiku (with guidance: Opus for reasoning-heavy, Sonnet for I/O)
5. **Tools** — `agent_toolset_20260401` (full toolset) or specific tools; custom tools needed?
6. **Permission policies** — `always_allow` or `always_ask` for specific tools
7. **MCP servers** — any external integrations (name + URL only, no credentials)
8. **Skills** — Anthropic pre-built (xlsx, pptx, etc.) or custom skills
9. **System prompt** — lead-0 drafts one based on answers, user confirms or edits
10. **Environment** — packages needed, networking mode (unrestricted vs limited + allowed_hosts)
11. **Resources** — GitHub repos or files to mount
12. **Vaults** — existing vault IDs for MCP auth, or create new ones
13. **Smoke test prompt** — what question to send to verify the agent works

For teams: repeat agent-level questions for each agent, then ask about `callable_agents` handoff.

Output: writes `$RUN_DIR/design/agent-specs.json` (array of agent definitions, no credentials).

### Phase 2 — Human approval gate

`lead-0` prints the path to `agent-specs.json` and the rendered spec as a markdown table, then pauses:

```
Spec written to runs/2026-04-09T14-05-00/design/agent-specs.json

┌─────────────────────────────────────────────────┐
│  Name:    My Agent                              │
│  Model:   claude-sonnet-4-6                    │
│  Tools:   agent_toolset_20260401               │
│  MCP:     github (https://api.github...)       │
│  Skills:  xlsx                                  │
│  Env:     python-dev (pandas, numpy)           │
│  System:  You are a helpful coding assistant…  │
└─────────────────────────────────────────────────┘

Type "approved" to provision, or describe changes.
```

If the user requests changes, `lead-0` updates the spec inline and re-displays. No re-running the full dialogue.

### Phase 3 — Provisioning

`lead-0` dispatches specialists based on what the design requires. The order follows resource dependencies:

```
1. files-expert        (if files need uploading)
2. mcp-vaults-expert   (if vaults/credentials needed)
3. skills-expert       (if custom skills need creating)
4. agents-expert       (create agent definitions — depends on skills being created first)
5. environments-expert (create environments — independent of agents)
6. sessions-expert     (create session — depends on agent + environment)
```

Steps 4 and 5 can run in parallel (agents and environments are independent resources).

Each specialist:
- Reads `$RUN_DIR/design/agent-specs.json` for its domain's config
- Executes the required `ant beta:*` CLI commands
- Writes results to `$RUN_DIR/provisioned/{domain}.json`
- Returns 1-2 sentence summary to lead-0

Example `$RUN_DIR/provisioned/agents.json`:
```json
[
  { "name": "My Agent", "agent_id": "agt_...", "version": 1 }
]
```

Example `$RUN_DIR/provisioned/environments.json`:
```json
[
  { "name": "python-dev", "environment_id": "env_..." }
]
```

Example `$RUN_DIR/provisioned/sessions.json`:
```json
[
  { "session_id": "ses_...", "agent_id": "agt_...", "environment_id": "env_..." }
]
```

### Phase 4 — Validation

`lead-0` dispatches `events-expert` with the session ID and either a smoke test prompt or an outcome definition from `$RUN_DIR/design/agent-specs.json`.

#### Mode A — Simple smoke test (default)

`events-expert`:

1. **Sends user message event**:
```bash
ant beta:sessions:events send \
  --session-id "$SESSION_ID" \
  --event '{type: user.message, content: [{type: text, text: "$SMOKE_PROMPT"}]}'
```

2. **Streams SSE events**, writes raw stream to `$RUN_DIR/test/events.json`:
```bash
ant beta:sessions:events stream \
  --session-id "$SESSION_ID"
```

3. Watches for:
   - `agent.message` → capture text
   - `agent.tool_use` → note tool calls
   - `session.status_idle` → done (check `stop_reason`)
   - `session.status_terminated` → failure

4. Handles `stop_reason: requires_action` by writing pending tool confirmations to `$RUN_DIR/test/pending-confirmations.json` and returning to lead-0 for user decision.

5. Writes `$RUN_DIR/test/result.md`:
```
Status: PASSED
Agent: My Agent (agt_01abc123)
Prompt: "What is 2+2?"
Response: "4"
Tool calls: none
Stop reason: end_turn
```

Returns to lead-0: `"Smoke test passed. Agent responded correctly in 1 turn with no tool errors."` or failure details.

#### Mode B — Outcome-based validation (when rubric provided)

`events-expert`:

1. **Sends define_outcome event** (requires `managed-agents-2026-04-01-research-preview` beta header):
```bash
ant beta:sessions:events send \
  --session-id "$SESSION_ID" \
  --beta managed-agents-2026-04-01-research-preview \
  --event '{type: user.define_outcome, description: "...", rubric: {type: text, content: "..."}, max_iterations: 5}'
```

2. **Streams SSE events**, watches for outcome evaluation cycle:
   - `span.outcome_evaluation_start` → note iteration number
   - `span.outcome_evaluation_ongoing` → heartbeat
   - `span.outcome_evaluation_end` → check `result`
   - `session.status_idle` → done

3. Writes `$RUN_DIR/test/result.md`:
```
Status: SATISFIED
Agent: My Agent (agt_01abc123)
Outcome: "Build a DCF model..."
Iterations: 2
Result: satisfied
Explanation: All 12 criteria met...
```

Returns to lead-0: `"Outcome satisfied after 2 iterations."` or `"Outcome failed: [explanation]"`.

**Durable run log**: `events.json` is written incrementally. If `events-expert` crashes mid-stream, the partial log survives. lead-0 can re-spawn `events-expert` and it can check whether a session already exists before creating a new one.

**Credential isolation**: `$ANTHROPIC_API_KEY` is read from env at runtime. Never written to any file. MCP server OAuth tokens are managed via vaults, referenced by ID only.

### Phase 5 — Summary

`lead-0` writes `$RUN_DIR/summary.md`:
```markdown
# Run 2026-04-09T14-05-00

## Agents provisioned
- My Agent — agt_01abc123 (v1)

## Environment
- python-dev — env_01xyz789

## Session
- ses_01def456

## Smoke test
- Status: PASSED
- Prompt: "What is 2+2?"
- Response: "4"

## Next steps
- Agent ID for sessions: agt_01abc123
- Environment ID: env_01xyz789
- Docs: https://platform.claude.com/docs/en/managed-agents/overview
```

Updates `runs/latest` symlink to current run directory.

---

## Run Directory Structure

```
runs/
  2026-04-09T14-05-00/       ← RUN_ID (ISO 8601, colons → dashes)
    design/
      agent-specs.json        ← array of agent definitions (no credentials)
    provisioned/
      agents.json             ← {name, agent_id, version} per agent
      environments.json       ← {name, environment_id} per environment
      sessions.json           ← {session_id, agent_id, environment_id}
      vaults.json             ← {vault_id, display_name} (if created)
      skills.json             ← {skill_id, name, version} (if created)
      files.json              ← {file_id, filename} (if uploaded)
    test/
      events.json             ← raw SSE event stream (append-only)
      pending-confirmations.json ← tool confirmation requests (if any)
      result.md               ← pass/fail + response summary
    summary.md
  latest -> runs/2026-04-09T14-05-00/
```

---

## Agent spec file format (`design/agent-specs.json`)

```json
[
  {
    "name": "Coding Assistant",
    "model": "claude-sonnet-4-6",
    "system": "You are a helpful coding assistant. Write clean, well-documented code.",
    "tools": [
      { "type": "agent_toolset_20260401" }
    ],
    "tool_permission_overrides": [
      { "name": "bash", "permission_policy": { "type": "always_ask" } }
    ],
    "mcp_servers": [],
    "skills": [],
    "callable_agents": [],
    "environment": {
      "name": "python-dev",
      "config": {
        "type": "cloud",
        "packages": { "pip": ["pandas", "numpy"] },
        "networking": { "type": "unrestricted" }
      }
    },
    "resources": [],
    "vault_ids": [],
    "smoke_test_prompt": "Write a Python function that returns the nth Fibonacci number.",
    "outcome": null
  }
]
```

With outcome-based validation:
```json
{
  "outcome": {
    "description": "Build a DCF model for Costco in .xlsx",
    "rubric": { "type": "text", "content": "# DCF Model Rubric\n..." },
    "max_iterations": 5
  }
}
```

For teams, additional fields:
```json
{
  "team": true,
  "callable_agents": [
    { "type": "agent", "role": "reviewer" },
    { "type": "agent", "role": "test-writer" }
  ],
  "handoff": "orchestrator delegates code review and test writing to specialists"
}
```

No credentials, no API keys, no OAuth tokens in this file.

---

## File Layout

```
.claude/
  CLAUDE.md                    ← durable project contract
  agents/
    lead-0.md                  ← orchestrator (Opus) — routing table only
    agents-expert.md           ← agent-setup docs
    environments-expert.md     ← environments docs
    sessions-expert.md         ← sessions docs
    events-expert.md           ← events-and-streaming docs
    tools-expert.md            ← tools + permission-policies docs
    multiagent-expert.md       ← multi-agent docs
    skills-expert.md           ← skills docs
    mcp-vaults-expert.md       ← mcp-connector + vaults docs
    files-expert.md            ← files CLI reference
  settings.json                ← tool permissions
runs/                          ← all run output (gitignored)
  latest -> ...                ← symlink to most recent run
docs/
  superpowers/
    specs/
      2026-04-09-managed-agent-orchestrator-design.md
```

---

## Tool Permissions (`.claude/settings.json`)

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Glob",
      "Grep",
      "Bash(ant beta:agents *)",
      "Bash(ant beta:agents:versions *)",
      "Bash(ant beta:environments *)",
      "Bash(ant beta:sessions *)",
      "Bash(ant beta:sessions:events *)",
      "Bash(ant beta:sessions:resources *)",
      "Bash(ant beta:skills *)",
      "Bash(ant beta:skills:versions *)",
      "Bash(ant beta:vaults *)",
      "Bash(ant beta:vaults:credentials *)",
      "Bash(ant beta:files *)",
      "Bash(ant --version)",
      "Bash(mkdir *)",
      "Bash(ln -sfn *)",
      "Bash(ls *)"
    ],
    "deny": []
  }
}
```

Bash is whitelisted per-prefix. No wildcard `Bash(*)`. Credentials never appear in allow rules.

---

## CLAUDE.md Contract (key clauses)

- `lead-0` is the only agent that spawns subagents
- All subagents return 1–2 sentence summaries; verbose output goes to `$RUN_DIR/`
- Each specialist only calls CLI commands within its own domain
- Credential handling is centralized in CLAUDE.md; the CLI is the only auth boundary
- Never provision agents without user approval (Phase 2 gate is mandatory)
- Never write to `runs/` root — always write under `runs/$RUN_ID/`
- Never start Phase 4 before Phase 3 completes
- Provisioning order respects resource dependencies (files → vaults → skills → agents ∥ environments → sessions)
- For teams: design all agents before provisioning any
- Specialists carry full API reference docs (CLI examples only, no curl with auth headers) in their system prompts; lead-0 carries only the routing table

---

## Error Handling

| Failure | Response |
|---|---|
| Phase 0: missing API key | Abort, print `export ANTHROPIC_API_KEY=your-key-here` |
| Phase 3: API 4xx | Specialist returns error details; lead-0 shows user and asks to fix spec |
| Phase 3: API 5xx | Specialist retries once, then reports failure |
| Phase 4: session error | `events-expert` writes `result.md` with error, returns failure summary; lead-0 reports and offers to retry |
| Phase 4: stream timeout | `events-expert` closes stream after 120s, marks test inconclusive |
| Phase 4: requires_action | `events-expert` writes pending confirmations, returns to lead-0 for user decision |

---

## Out of scope (v1)

- Web UI or non-Claude Code interfaces
- Auto-submit or auto-send (all actions require explicit user input)
- Agent versioning / update flows (create only, no update)
- Persistent agent registry across runs (agent IDs are in the run directory only)
- Multi-turn interactive sessions (smoke test is one-shot only)
- Memory (research preview)

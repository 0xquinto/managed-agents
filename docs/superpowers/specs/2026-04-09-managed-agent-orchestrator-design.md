# Managed Agent Orchestrator — Design Spec
*Date: 2026-04-09*

## Purpose

A Claude Code agent pipeline that guides a developer through designing, provisioning, and smoke-testing Claude Managed Agents via the Anthropic API. Entirely terminal-driven; no web UI. Same structural patterns as the job-research pipeline (lead + subagents, run-scoped directories, summary-only returns, CLAUDE.md contract), with Managed Agents API patterns layered on top (brain ≠ hands, on-demand environments, durable run log, credential isolation).

---

## Architecture

### Agents

| Agent | Model | Responsibility | Spawn mode |
|---|---|---|---|
| `lead-0` | Opus | Design dialogue (multi-turn Q&A) + orchestration | Root |
| `provisioner-1` | Sonnet | POST agent definitions to API (brains only) | Foreground |
| `env-tester-2` | Sonnet | Create environment, session, smoke test, stream events | Foreground |

`lead-0` is the only agent that spawns subagents. No nested spawning. Subagents return 1–2 sentence summaries; all verbose output goes to `$RUN_DIR/`.

### Pipeline phases

```
Phase 0   Readiness check (lead-0)
Phase 1   Design dialogue (lead-0, direct with user)
Phase 2   Human approval gate
Phase 3   Brain provisioning (provisioner-1, foreground)
Phase 4   On-demand environment + smoke test (env-tester-2, foreground)
Phase 5   Summary (lead-0)
```

---

## Phase Details

### Phase 0 — Readiness check

`lead-0` runs these checks before any work:

1. `echo $ANTHROPIC_API_KEY` — non-empty
2. `ant --version` — CLI installed
3. `curl --version` — available for SSE streaming fallback

On any failure: print a clear error message with fix instructions, abort. No onboarding subagent (simpler than job-research; the fix instructions are short).

### Phase 1 — Design dialogue

`lead-0` interviews the user one question at a time. Questions cover:

1. **Name** — what to call the agent
2. **Purpose** — one-sentence description of what it does
3. **Single agent or team?** — if team, how many and what roles
4. **Model** — Opus / Sonnet / Haiku (with guidance: Opus for reasoning-heavy, Sonnet for I/O)
5. **Tools** — `agent_toolset_20260401` (full toolset) or specific tools (bash, file, web_search, etc.)
6. **MCP servers** — any external integrations (named only, no credentials)
7. **System prompt** — lead-0 drafts one based on answers, user confirms or edits
8. **Smoke test prompt** — what question to send to verify the agent works

For teams: repeat questions 1–7 for each agent, then ask how agents hand off to each other.

Output: writes `$RUN_DIR/design/agent-specs.json` (array of agent definitions, no credentials).

### Phase 2 — Human approval gate

`lead-0` prints the path to `agent-specs.json` and the rendered spec as a markdown table, then pauses:

```
Spec written to runs/2026-04-09T14-05-00/design/agent-specs.json

┌─────────────────────────────────────────────────┐
│  Name:    My Agent                              │
│  Model:   claude-sonnet-4-6                    │
│  Tools:   agent_toolset_20260401               │
│  MCP:     none                                  │
│  System:  You are a helpful coding assistant…  │
└─────────────────────────────────────────────────┘

Type "approved" to provision, or describe changes.
```

If the user requests changes, `lead-0` updates the spec inline and re-displays. No re-running the full dialogue.

### Phase 3 — Brain provisioning

`provisioner-1` reads `$RUN_DIR/design/agent-specs.json` and for each agent:

```bash
curl -sS --fail-with-body https://api.anthropic.com/v1/agents \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d @agent-spec.json
```

Writes `$RUN_DIR/provisioned/agents.json`:
```json
[
  { "name": "My Agent", "agent_id": "agt_...", "version": 1 }
]
```

Returns to lead-0: `"Provisioned 1 agent: agt_01abc123"`.

**Brain ≠ hands**: provisioner-1 never touches `/v1/environments` or `/v1/sessions`. Environment creation is deferred to Phase 4.

### Phase 4 — On-demand environment + smoke test

`env-tester-2` reads `$RUN_DIR/provisioned/agents.json` and `$RUN_DIR/design/agent-specs.json` (for the smoke test prompt), then:

1. **Create environment** (on-demand, only now):
```bash
curl -sS --fail-with-body https://api.anthropic.com/v1/environments \
  -H "..." \
  -d '{"name":"smoke-test-env","config":{"type":"cloud","networking":{"type":"unrestricted"}}}'
```

2. **Create session** (for first agent; or each agent if team):
```bash
curl -sS --fail-with-body https://api.anthropic.com/v1/sessions \
  -H "..." \
  -d "{\"agent\":\"$AGENT_ID\",\"environment_id\":\"$ENV_ID\",\"title\":\"smoke-test\"}"
```

3. **Send smoke test event**:
```bash
curl -sS --fail-with-body https://api.anthropic.com/v1/sessions/$SESSION_ID/events \
  -H "..." \
  -d "{\"events\":[{\"type\":\"user.message\",\"content\":[{\"type\":\"text\",\"text\":\"$SMOKE_PROMPT\"}]}]}"
```

4. **Stream SSE events**, write raw stream to `$RUN_DIR/test/events.json`, watch for:
   - `agent.message` → capture text
   - `agent.tool_use` → note tool calls
   - `session.status_idle` → done

5. Write `$RUN_DIR/test/result.md`:
```
Status: PASSED
Agent: My Agent (agt_01abc123)
Prompt: "What is 2+2?"
Response: "4"
Tool calls: none
```

Returns to lead-0: `"Smoke test passed. Agent responded correctly in 1 turn with no tool errors."` or `"Smoke test failed: session.status_error — [details]"`.

**Durable run log**: `events.json` is written incrementally. If `env-tester-2` crashes mid-stream, the partial log survives. lead-0 can re-spawn `env-tester-2` and it can check whether a session already exists before creating a new one.

**Credential isolation**: `$ANTHROPIC_API_KEY` is read from env at runtime. Never written to any file. MCP server OAuth config is stored as a name reference only (e.g., `"oauth_provider": "github"`); actual tokens are managed by the Managed Agents vault outside this system.

### Phase 5 — Summary

`lead-0` writes `$RUN_DIR/summary.md`:
```markdown
# Run 2026-04-09T14-05-00

## Agents provisioned
- My Agent — agt_01abc123 (v1)

## Smoke test
- Status: PASSED
- Prompt: "What is 2+2?"
- Response: "4"

## Next steps
- Agent ID for sessions: agt_01abc123
- Docs: https://docs.anthropic.com/managed-agents
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
    test/
      events.json             ← raw SSE event stream (append-only)
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
    "mcp_servers": [],
    "smoke_test_prompt": "Write a Python function that returns the nth Fibonacci number."
  }
]
```

For teams, additional fields:
```json
{
  "team": true,
  "handoff": "orchestrator passes task to specialist by agent_id"
}
```

No credentials, no API keys, no OAuth tokens in this file.

---

## File Layout

```
.claude/
  CLAUDE.md                  ← durable project contract
  agents/
    lead-0.md                ← orchestrator (Opus)
    provisioner-1.md         ← brain provisioner (Sonnet)
    env-tester-2.md          ← environment + smoke test (Sonnet)
  settings.json              ← tool permissions
runs/                        ← all run output (gitignored)
  latest -> ...              ← symlink to most recent run
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
      "Bash(curl -sS *)",
      "Bash(ant beta:agents *)",
      "Bash(ant beta:environments *)",
      "Bash(ant beta:sessions *)",
      "Bash(echo $ANTHROPIC_API_KEY)",
      "Bash(ant --version)",
      "Bash(curl --version)",
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
- `$ANTHROPIC_API_KEY` is always read from environment; never written to files
- Never provision agents without user approval (Phase 2 gate is mandatory)
- Never write to `runs/` root — always write under `runs/$RUN_ID/`
- Never start Phase 4 before Phase 3 completes
- Never create an environment without a session to use it (on-demand only)
- For teams: design all agents before provisioning any

---

## Error Handling

| Failure | Response |
|---|---|
| Phase 0: missing API key | Abort, print `export ANTHROPIC_API_KEY=your-key-here` |
| Phase 3: API 4xx | `provisioner-1` returns error details; lead-0 shows user and asks to fix spec |
| Phase 3: API 5xx | `provisioner-1` retries once, then reports failure |
| Phase 4: session error | `env-tester-2` writes `result.md` with error, returns failure summary; lead-0 reports and offers to retry |
| Phase 4: stream timeout | `env-tester-2` closes stream after 120s, marks test inconclusive |

---

## Out of scope (v1)

- Web UI or non-Claude Code interfaces
- Auto-submit or auto-send (all actions require explicit user input)
- Agent versioning / update flows (create only, no update)
- Persistent agent registry across runs (agent IDs are in the run directory only)
- Multi-turn interactive sessions (smoke test is one-shot only)

---
name: "Managed Agent Orchestrator"
oneLiner: "A terminal-driven Claude Code pipeline that interviews a developer, designs Claude Managed Agent configurations, provisions them via the Anthropic API, and validates them — with 6 abstract orchestration skills for common production patterns."
domain: "AI Developer Tooling / Claude Managed Agents"
---

## Timespan
- **First commit:** 2026-04-09
- **Last commit:** 2026-04-10
- **Total commits:** 19
- **Active days:** 2

## Arc

### Beginning
The project started on 2026-04-09 with a single design spec (`managed-agent-orchestrator-design.md`) laying out a 3-agent pipeline for provisioning Claude Managed Agents. The initial design borrowed structural patterns from a pre-existing job-research pipeline (lead + subagents, run-scoped directories, summary-only returns), adapting them to the Anthropic Managed Agents API.

### Middle
Within the same day the spec was restructured: the 3-agent approach was replaced by an 11-agent domain-specialist architecture. The lead orchestrator (`lead-0`) was slimmed to carry only a routing table, while 10 Sonnet-based specialists were each given full CLI `--help` output and live API reference docs for their domain. The project contract (CLAUDE.md) established the CLI-as-auth-boundary pattern — the API key is invisible to the agent layer, flowing only through the `ant` CLI. Settings.json locked down tool permissions with per-prefix Bash whitelisting and zero wildcard access.

Three research-preview features were brought into scope after sequential go/no-go research: define-outcomes (rubric-driven iterative validation), memory stores (persistent cross-session knowledge), and agent update/versioning flows. Two were rejected: multi-turn interactive sessions (orchestrator shouldn't be a chat proxy) and persistent agent registry (API list endpoints are the source of truth).

### End
On 2026-04-10, the project shifted from infrastructure to patterns. Research across 10+ production deployments (Sentry, Spotify, Rakuten, Duvo, Notion, Tasklet, Zapier) identified 6 abstract orchestration patterns validated by real customers. Each pattern was researched with Exa web search, written as a skill following the superpowers:writing-skills methodology, validated for correct wiring to all specialists, and reviewed with the user before committing. Cross-skill consistency bugs (HTTPS prefixes, `_orchestration` wrapper format, create/update questions) were caught and fixed during validation passes.

## Key Milestones
| Date | Commit | Description |
|------|--------|-------------|
| 2026-04-09 | fe1be22 | Initial design spec: 3-agent pipeline |
| 2026-04-09 | 8bd6d56 | Restructure to domain-specialist architecture |
| 2026-04-09 | 7c523dc | CLAUDE.md contract + settings.json with CLI-as-auth-boundary |
| 2026-04-09 | 3cfcfa5 | lead-0 orchestrator: 6-phase pipeline + routing table |
| 2026-04-09 | 2c71cfb | All 9 domain specialist system prompts |
| 2026-04-09 | 80fce20 | Fix multiagent-expert: fake CLI commands → REST endpoints |
| 2026-04-09 | 6aacbda | Expand files-expert with full docs reference |
| 2026-04-10 | 1a6e1ff | Add outcome-based validation (research preview) |
| 2026-04-10 | 0640152 | Add memory store support (research preview) |
| 2026-04-10 | 2cf37fd | Add agent update/versioning flow |
| 2026-04-10 | 2d24650 | Research: managed agents success cases (10+ production deployments) |
| 2026-04-10 | fa3c242 | Skill: reactive-pipeline (Event → Agent → Artifact → Delivery) |
| 2026-04-10 | 6ede0c4 | Skill: evaluator (Artifact → Criteria Check → Feedback) |
| 2026-04-10 | e56abd8 | Skill: transformer (Input → Systematic Modification → Output) |
| 2026-04-10 | d8aeed9 | Skill: researcher (Question → Gathering → Synthesis → Report) |
| 2026-04-10 | 1b3a7aa | Skill: operator (System A + B → Extract → Reconcile → Act) |
| 2026-04-10 | 7053822 | Skill: team-coordinator (Task → Decompose → Parallel → Reassemble) |

## Architecture

### Agents (11 total)
| Agent | Model | Role |
|---|---|---|
| `lead-0` | Opus | Orchestrator — routing table, design dialogue, dispatch |
| `agents-expert` | Sonnet | Agent CRUD, versioning, model config |
| `environments-expert` | Sonnet | Containers, packages, networking |
| `sessions-expert` | Sonnet | Session lifecycle, resource mounting |
| `events-expert` | Sonnet | SSE streaming, event types, outcomes |
| `tools-expert` | Sonnet | Built-in toolset, custom tools, permissions |
| `multiagent-expert` | Sonnet | callable_agents, session threads |
| `skills-expert` | Sonnet | Anthropic + custom skills |
| `mcp-vaults-expert` | Sonnet | MCP servers, vaults, credentials |
| `files-expert` | Sonnet | File upload, download, mounting |
| `memory-expert` | Sonnet | Memory stores, memories, versioning |

### Skills (6 abstract patterns)
| Skill | Pattern | Instantiates |
|---|---|---|
| `reactive-pipeline` | Event → Agent → Artifact → Delivery | Issue-to-PR, support responder, alert fixer, CI fixer |
| `evaluator` | Artifact → Criteria Check → Feedback | Code reviewer, compliance checker, quality gate |
| `transformer` | Input → Systematic Modification → Output | Code migrator, format converter, batch refactor |
| `researcher` | Question → Gathering → Synthesis → Report | Deep research, competitor monitor, docs generator |
| `operator` | System A + B → Extract → Reconcile → Act | Procurement automation, data reconciliation, workflow bridge |
| `team-coordinator` | Task → Decompose → Parallel → Reassemble | Multi-agent review, plan-build-review, parallel research |

## Tech Stack
- Claude Code (CLI orchestration harness)
- Anthropic Managed Agents API (`managed-agents-2026-04-01` beta)
- `ant` CLI (14 `beta:*` command groups)
- SSE streaming (session + thread event streams)
- Exa web search (pattern research)
- superpowers:writing-skills (skill authoring methodology)
- Claude Opus 4.6 (lead-0 orchestrator)
- Claude Sonnet 4.6 (10 domain specialists)

## Metrics
| Metric | Value |
|--------|-------|
| Agent definitions | 11 (1 lead + 10 specialists) |
| Skill definitions | 6 abstract orchestration patterns |
| Research documents | 7 (1 success cases + 6 pattern-specific) |
| Lines of system prompt content | ~2,200 across 11 agent files |
| Lines of skill content | ~1,000 across 6 skill files |
| API domains covered | 10 (agents, environments, sessions, events, tools, multi-agent, skills, MCP/vaults, files, memory) |
| Pipeline phases | 6 (readiness, design dialogue, approval gate, provisioning, validation, summary) |
| Bash commands allowlisted | 14 `ant beta:*` prefixes, zero wildcard |
| Production patterns researched | 10+ customer deployments (Sentry, Spotify, Rakuten, Duvo, Notion, Tasklet, Zapier) |
| Validation passes | 8 (2 full CLI audits + 6 per-skill wiring validations) |
| Cross-skill bugs caught | 4 (HTTPS prefixes, _orchestration wrapper, create/update question, tools_extra field) |

## Lessons Learned
- **Routing table, not encyclopedia**: Keeping lead-0 context-light (routing table only) is critical for multi-turn design dialogues. Load API reference only into the specialist that needs it.
- **CLI-as-auth-boundary**: Whitelisting `ant beta:*` prefixes prevents agents from constructing raw curl calls with embedded credentials. The API key is invisible to the agent layer.
- **Domain specialists are maintainable**: When the files API added behavior, only `files-expert.md` needed updating. When outcomes were added, only `events-expert` and `sessions-expert` changed.
- **Abstract over concrete**: Skills like `reactive-pipeline` are more valuable than `issue-to-pr` because the same pattern serves 6+ use cases with different MCP configs.
- **Validation catches real bugs**: Every skill validation found at least one issue — `tools_extra` (fake field), fake CLI commands, missing delivery MCP servers, hardcoded branches, inconsistent `_orchestration` wrappers.
- **Research before building**: The go/no-go research pattern saved effort — 2 of 5 features were correctly rejected (multi-turn sessions, persistent registry) before any code was written.
- **Sequential research with Exa**: Running pattern-specific searches before writing each skill produced better-informed defaults (e.g., evaluator read-only config, operator always_ask-by-default, transformer 5-level validation stack).

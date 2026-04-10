---
name: "Managed Agent Orchestrator"
oneLiner: "A terminal-driven Claude Code pipeline that interviews a developer, designs Claude Managed Agent configurations, provisions them via the Anthropic API, and validates them with a smoke test — all without a web UI."
domain: "AI Developer Tooling / Claude Managed Agents"
---

## Timespan
- **First commit:** 2026-04-09
- **Last commit:** 2026-04-10
- **Total commits:** 9
- **Active days:** 2

## Arc

### Beginning
The project started on 2026-04-09 with a single large design spec (`managed-agent-orchestrator-design.md`) that laid out a 3-agent pipeline for provisioning Claude Managed Agents. The initial design borrowed structural patterns directly from a pre-existing job-research pipeline (lead + subagents, run-scoped directories, summary-only returns), adapting them to the Anthropic Managed Agents API domain.

### Middle
Within the same day the spec was immediately restructured: the 3-agent approach was replaced by a 10-agent domain-specialist architecture. The lead orchestrator (`lead-0`) was slimmed down to carry only a routing table, while 9 Sonnet-based specialists were each given full CLI `--help` output and live API reference docs for their specific domain (agents, environments, sessions, events, tools, multi-agent, skills, MCP/vaults, files). The project contract (CLAUDE.md) and tool permission allowlist (settings.json) were locked down, establishing the CLI-as-auth-boundary pattern and per-prefix Bash whitelisting. All 9 specialist system prompts were committed in a single shot.

### End
On 2026-04-10 a final capability was added: outcome-based validation (`user.define_outcome`) backed by the research-preview beta header. The pipeline moved from simple one-shot smoke tests to iterative, rubric-driven agent evaluation with `max_iterations` control. The `lead-0` design dialogue was updated to elicit outcome specs from users, and `events-expert` was taught to interpret `span.outcome_evaluation_*` SSE events. At this point the pipeline was feature-complete for v1.

## Key Milestones
| Date | Commit | Description |
|------|--------|-------------|
| 2026-04-09 | fe1be22 | Initial design spec: 3-agent pipeline for Managed Agent provisioning |
| 2026-04-09 | 8bd6d56 | Restructure to 10-agent domain-specialist architecture |
| 2026-04-09 | 7c523dc | Add CLAUDE.md contract and settings.json with per-prefix Bash allowlist |
| 2026-04-09 | 3cfcfa5 | Add lead-0 orchestrator system prompt with 6-phase pipeline and routing table |
| 2026-04-09 | 2c71cfb | Add all 9 domain specialist system prompts with full CLI and API reference |
| 2026-04-09 | 80fce20 | Fix multiagent-expert: replace nonexistent CLI thread commands with REST endpoints |
| 2026-04-09 | 6aacbda | Expand files-expert with live docs (file types, path behavior, session-scoped copies) |
| 2026-04-10 | 1a6e1ff | Add outcome-based validation (define_outcome, rubric, max_iterations, research preview) |

## Tech Stack
- Claude Code (CLI orchestration harness)
- Anthropic Managed Agents API (`managed-agents-2026-04-01` beta)
- `ant` CLI (`ant beta:agents`, `ant beta:environments`, `ant beta:sessions`, `ant beta:sessions:events`, `ant beta:files`, `ant beta:vaults`, `ant beta:skills`)
- SSE streaming (session event stream, thread streams)
- JSON (agent-specs.json, provisioned/*.json run artifacts)
- Markdown (system prompts, run summaries)
- Claude Opus 4 (lead-0 orchestrator model)
- Claude Sonnet 4.6 (9 domain specialist models)

## Metrics
| Metric | Value |
|--------|-------|
| Agent definitions | 10 (1 lead orchestrator + 9 domain specialists) |
| Lines of system prompt content added | ~1,700 across 10 agent files |
| API domains covered | 9 (agents, environments, sessions, events, tools, multi-agent, skills, MCP/vaults, files) |
| Pipeline phases | 6 (readiness, design dialogue, approval gate, provisioning, smoke test, summary) |
| Bash commands allowlisted | 14 distinct `ant beta:*` prefixes, zero wildcard Bash access |
| Provisioning dependency stages | 5 ordered steps (files → vaults → skills → agents ∥ environments → sessions) |

## Lessons Learned
- Keeping the orchestrator context-light (routing table only, no API docs) is critical for multi-turn design dialogues — load API reference only into the specialist that needs it.
- CLI-as-auth-boundary is a clean security primitive: whitelisting `ant beta:*` prefixes in settings.json prevents any agent from constructing raw curl calls with embedded credentials.
- Domain-specialist agents are more maintainable than a monolithic provisioner: when the files API added new behavior (session-scoped copies, file type list), only `files-expert.md` needed updating.

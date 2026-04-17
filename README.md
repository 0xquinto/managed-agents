# Managed Agent Orchestrator

*A terminal pipeline for designing, provisioning, and smoke-testing [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/quickstart).*

Provisioning a Claude Managed Agent by hand means coordinating ~10 API domains — agents, environments, sessions, events, tools, files, skills, memory, MCP servers, and vaults. This repo is a Claude Code agent pipeline that interviews you, designs the config, provisions it in dependency order after your approval, and smoke-tests it. The Anthropic API key never enters the agent context.

## Demo

```text
$ claude --agent lead-0

lead-0> What would you like this agent to do?

you> Triage incoming GitHub issues and post a triage comment with labels and severity.

lead-0> Two clarifying questions:
        1. Which GitHub repos should it watch? (one, many, org-wide)
        2. Should it post on every new issue, or only when a human @-mentions it?

you> One repo (acme/api). Only on @-mention.

lead-0> Proposed design:
          name:         gh-triage
          model:        claude-sonnet-4-6
          skills:       evaluator
          mcp:          github (read-only scopes: issues, repo)
          env:          default container, no extra packages
          tools:        web_search, think
          session:      one thread per issue

        Phase 3 will provision: files → vaults → skills → agent → session.
        Approve? (yes / edit / no)

you> yes

lead-0> Dispatching mcp-vaults-expert, skills-expert, agents-expert in parallel...
        [mcp-vaults-expert] vault created: vault_01HZ... (github, read-only)
        [skills-expert]     skill attached: evaluator@v3
        [agents-expert]     agent created: agent_01HZ... (gh-triage)
        ...
        Phase 3 complete. runs/latest/provision.log

lead-0> Phase 4: smoke test
        → ant beta:sessions create --agent agent_01HZ... > session.json
        → ant beta:sessions:events send --session sess_01HZ... \
            --content "Test issue: login returns 500 on empty body"
        → streaming outcome: OK (labels: bug, backend; severity: high)
        Smoke test PASS.

lead-0> Summary at runs/latest/summary.md
        - agent_id: agent_01HZ...
        - session_id: sess_01HZ...
        - next: send a real @-mention event to exercise the full loop.
```

## How it works

Twelve production agents in a single Claude Code process. `lead-0` (Opus) runs the design dialogue directly with the user and is the only agent that spawns subagents. Ten Sonnet domain specialists each carry the full `ant` CLI reference for one API domain; a research specialist handles external lookups via Exa. Specialists return 1–2 sentence summaries — verbose output goes to `runs/$RUN_ID/`.

```
                               user
                                ▲
                                │  design dialogue
                                ▼
                          ┌───────────┐
                          │  lead-0   │  Opus — routing table only
                          └─────┬─────┘
                                │ Agent(...) dispatches
   ┌────────┬─────────┬─────────┼─────────┬─────────┬────────┐
   ▼        ▼         ▼         ▼         ▼         ▼        ▼
 agents  environ-  sessions   events    tools    multi-    skills
 expert  ments     expert     expert    expert   agent     expert
                                                 expert
   ├────────┼─────────┼─────────┴─────────┼─────────┼────────┤
   ▼        ▼         ▼                   ▼         ▼
 mcp-     files     memory             research
 vaults   expert    expert             expert (Exa)
 expert

                         specialists write artifacts to
                                ▼
                          runs/$RUN_ID/
```

**Routing table, not encyclopedia.** `lead-0` carries only a dispatch table so multi-turn design dialogues stay cheap and coherent. API reference lives in the specialist that owns it.

**CLI-as-auth-boundary.** The `ant` CLI is the only process that reads `$ANTHROPIC_API_KEY`. Agents never construct curl calls with embedded credentials.

```
  Environment ($ANTHROPIC_API_KEY)
           │
           ▼
      ┌─────────┐
      │ ant CLI │  ← only thing that touches the key
      └─────────┘
           │
           ▼
     Anthropic API
```

**Summary-only returns.** Specialists write verbose output (grounding schemas, validation reports, provision logs) to `runs/$RUN_ID/` and hand `lead-0` back one or two sentences.

## The 6 orchestration skills

Six abstract patterns, each usable as a slash command (`/reactive-pipeline`, `/evaluator`, etc.). Each skill wraps the right subset of specialists for its pattern. These are Claude Code slash-command skills local to this repo — distinct from the Managed Agents API `skills` resource that `skills-expert` provisions on a deployed agent.

| Skill | Pattern | Example |
|---|---|---|
| [`reactive-pipeline`](./.claude/skills/reactive-pipeline/) | Event → Agent → Artifact → Delivery | Issue-to-PR fixer |
| [`evaluator`](./.claude/skills/evaluator/) | Artifact → Criteria Check → Feedback | Code reviewer / quality gate |
| [`transformer`](./.claude/skills/transformer/) | Input → Systematic Modification → Output | Codebase migrator |
| [`researcher`](./.claude/skills/researcher/) | Question → Gathering → Synthesis → Report | Competitor monitor |
| [`operator`](./.claude/skills/operator/) | System A + B → Extract → Reconcile → Act | Procurement reconciler |
| [`team-coordinator`](./.claude/skills/team-coordinator/) | Task → Decompose → Parallel → Reassemble | Plan-build-review team |

## Quickstart

**Prerequisites**

- [Claude Code](https://claude.com/claude-code) CLI installed
- `ant` CLI installed — see the [install guide](https://platform.claude.com/docs/en/managed-agents/quickstart)
- `ANTHROPIC_API_KEY` exported in your shell

**Run**

```bash
git clone <repo-url>  # replace with the clone URL
cd managed_agents
claude --agent lead-0
```

Then talk to `lead-0`. Describe what you want in plain English, or jump straight to one of the six patterns with a slash command: `/reactive-pipeline`, `/evaluator`, `/transformer`, `/researcher`, `/operator`, `/team-coordinator`.

**Pipeline phases**

`0` readiness check · `1` design dialogue · `2` approval gate · `3` provisioning · `4` smoke test · `5` summary

**Output**

All artifacts land under `runs/$RUN_ID/`. The `runs/latest` symlink points to the most recent run.

## Run directory layout

```
runs/
  2026-04-17T14-23-05Z/
    design/            # Phase 1–2: grounded schemas + approved design
    research/          # external research notes (optional)
    validation/        # Phase 2 per-domain validation reports
    provisioned/       # Phase 3 CLI responses, one file per resource
    provision.log      # rolled-up Phase 3 log
    smoke.md           # Phase 4 test results
    summary.md         # final summary: IDs, next steps, links
  latest -> 2026-04-17T14-23-05Z
```

Every session gets an ISO-8601-timestamped directory (colons replaced by dashes). Nothing is written to `runs/` root. The `runs/` tree is gitignored.

## Design rationale

- **Routing table, not encyclopedia.** `lead-0` carries only a dispatch table. API reference lives in the specialist that owns it. Keeps multi-turn design dialogues cheap and coherent.
- **CLI-as-auth-boundary.** Whitelisting `ant beta:*` prefixes in [`settings.json`](./.claude/settings.json) prevents agents from constructing raw curl calls with embedded credentials. The API key flows environment → `ant` → API, invisible to the agent layer.
- **Abstract over concrete.** Six orchestration skills, not sixty recipes. `reactive-pipeline` serves issue-to-PR, support responder, alert fixer, and CI fixer — all with different MCP configs.
- **Research before building.** Each proposed feature gets a go/no-go research pass before any code. Two of five proposed features were correctly rejected (multi-turn sessions, persistent registry) before implementation.

## Repo map

```
.claude/
  agents/            # 12 system prompts (lead-0 + 10 specialists + research-expert)
  skills/            # 6 orchestration skill bundles
  CLAUDE.md          # project contract: invariants, credential handling
  settings.json      # Bash/tool permissions (ant beta:* whitelist)
docs/
  api-reference/     # Anthropic API docs snapshot used by specialists
  research/          # success cases + per-pattern research
  superpowers/specs/ # design specs for this repo's own work
  superpowers/plans/ # implementation plans
runs/                # session artifacts (gitignored)
project-story.md     # narrative arc of the build
README.md            # you are here
LICENSE              # MIT
```

## Learn more

- [`project-story.md`](./project-story.md) — the build narrative
- [`.claude/CLAUDE.md`](./.claude/CLAUDE.md) — invariants & credential contract
- [`docs/research/managed-agents-success-cases.md`](./docs/research/managed-agents-success-cases.md) — 10+ production patterns studied
- Per-skill READMEs — linked from the [skills table](#the-6-orchestration-skills) above
- Per-agent prompts under [`.claude/agents/`](./.claude/agents/)

## License

MIT — see [LICENSE](./LICENSE).

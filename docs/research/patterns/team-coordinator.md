# Team Coordinator Pattern

## Research Summary

**Pattern**: Task → Decompose → Parallel Specialists → Reassemble  
**Also known as**: Orchestrator-Worker, Fan-Out/Fan-In, Supervisor-Worker, Scatter-Gather  
**Research date**: 2026-04-09

---

## 1. Pattern Definition

The team-coordinator pattern places a single coordinator agent in front of a pool of specialist worker agents. The coordinator receives the original task, analyzes it, decomposes it into independent or semi-independent subtasks, dispatches those subtasks to workers (sequentially or in parallel), collects results, and synthesizes a final unified response.

The key abstraction is **separation of concerns between thinking and doing**. The coordinator reasons and orchestrates; workers execute. This separation prevents context pollution, enables parallelism, and creates a natural quality gate between planning and action.

From the Anthropic Managed Agents architecture (published April 2026): the brain (Claude + harness) is decoupled from the hands (sandboxes, tools). Brains can pass hands to one another via `execute(name, input) → string`. This interface is the foundation for all multi-agent coordination in the Claude ecosystem.

From the Claude Code source book (ch10): "The coordinator cannot touch files, which forces clean separation of concerns: thinking happens in one context, doing happens in another."

**When it helps:**
- Task is too large for a single context window
- Task has naturally independent parallel subtasks (e.g., review 10 files simultaneously)
- Different subtasks require different tool sets or permission modes
- A "separation of judge and jury" is needed (writer agent ≠ reviewer agent)
- Quality improves with multi-perspective evaluation (security review + code quality + test coverage)

**When it hurts:**
- Tasks are inherently sequential with hard data dependencies
- Subtasks are too small (< ~5 seconds each) — coordination overhead exceeds benefit
- Task requires constant back-and-forth feedback; sub-agent round-trip adds latency
- Token budget is tight — multi-agent systems can consume ~15x more tokens than single-agent
- The task cannot be cleanly decomposed (MECE decomposition is hard to specify)

---

## 2. Common Team Topologies

### 2.1 Parallel Fan-Out (Classic Coordinator)
```
Task → Coordinator
         ├── Worker A (subtask 1)
         ├── Worker B (subtask 2)
         ├── Worker C (subtask 3)
         └── Worker D (subtask 4)
                    ↓
         Coordinator synthesizes results
```
**Best for**: Independent subtasks of similar scope (review N files, fetch N URLs, analyze N data sources).  
**Execution time**: max(individual times), not sum.

### 2.2 Plan-Build-Review Cycle
```
Task → Planner agent
         ↓
       Execution plan
         ↓
       Builder agent(s) (implement)
         ↓
       Reviewer agent(s) (validate)
         ↓
       [Optional: loop back if review fails]
         ↓
       Coordinator synthesizes final output
```
**Best for**: Software development, document creation, content pipelines.  
**Key principle**: "The agent that produces output should never be the sole evaluator of that output." (separation of judge and jury)  
**Production example**: n8n AI Workflow Builder uses exactly this: Supervisor → Discovery → Planner → Builder → Responder, each a separate agent with its own system prompt, sharing one LLM configuration.

### 2.3 Multi-Perspective Review (Analysis Swarm)
```
Artifact (code, doc, PR) → Coordinator
         ├── Security auditor agent
         ├── Code quality agent
         ├── Test coverage agent
         └── Performance agent
                    ↓
         Coordinator merges categorized findings
```
**Best for**: Code review, architecture decisions, technical proposals.  
**Real pattern from ClaudeWorld**: spawning specialized reviewers in parallel on the same artifact.

### 2.4 Hierarchical (Tree Delegation)
```
Top coordinator
  ├── Sub-coordinator A
  │     ├── Worker A1
  │     └── Worker A2
  └── Sub-coordinator B
        ├── Worker B1
        └── Worker B2
```
**Best for**: Very large tasks (20+ agents), multi-domain enterprise workflows.  
**Trade-off**: Adds 6-12s latency per level; summarization loss accumulates at each level.  
**Anti-pattern risk**: Hierarchies work best when they map to natural problem decomposition, not artificial org-chart structures.

### 2.5 Pipeline with Quality Gates
```
Input → Stage1 [gate] → Stage2 [gate] → Stage3 [gate] → Output
```
**Best for**: Repeatable processes (CI/CD, document processing, ETL).  
**Key design**: Each gate blocks progress until quality criteria are met. Every stage must validate its inputs; garbage-in silently propagates without gates.

---

## 3. Coordinator Prompt Design Patterns

### 3.1 Core Structure for a Coordinator System Prompt

From Claude Code's 370-line coordinator system prompt (described in claude-code-from-source.com ch10), the key teachings encoded are:

1. **"Never delegate understanding."** The coordinator must synthesize research findings into specific, self-contained prompts. Anti-pattern: `"Based on your findings, fix the bug"`. Correct pattern: include file paths, line numbers, exact context, and a precise change specification.

2. **Workers need self-contained prompts.** Each subtask prompt must include all context the worker needs. Workers cannot ask follow-up questions. If a subtask prompt is underspecified, the worker will hallucinate context.

3. **The coordinator reads worker output, workers do not share state.** Workers report results through the task completion mechanism. The coordinator synthesizes; workers do not peer-communicate (in the basic pattern).

Skeleton coordinator system prompt:
```
You are a task coordinator. Your job is to:
1. Analyze the incoming task and identify all distinct subtasks.
2. For each subtask, determine whether it can run in parallel or must wait on another.
3. Write a self-contained prompt for each subtask that includes:
   - The exact goal
   - All necessary context (file paths, line numbers, prior findings)
   - The expected output format
   - Acceptance criteria
4. Dispatch subtasks to the appropriate specialist agents.
5. Collect all results.
6. Synthesize a unified final response. Do not concatenate results blindly —
   resolve conflicts, deduplicate findings, and present a coherent whole.

Rules:
- Never delegate understanding. You are the one who reasons; workers execute.
- Each subtask must be self-contained. Workers cannot ask follow-up questions.
- Parallelize where there are no data dependencies. Sequential only when required.
- If a worker fails, decide: retry, use fallback, or proceed with partial results.
```

### 3.2 Decomposition Prompt Pattern (MECE)

From ROMA paper (arXiv:2602.01848) and RDD paper (arXiv:2505.02576):

Best decompositions are **Mutually Exclusive, Collectively Exhaustive (MECE)** and **dependency-aware** (a DAG, not just a flat list). The coordinator should produce a task graph, not a task list.

```
Decompose the following goal into subtasks.
Rules for decomposition:
- Each subtask must be atomic (completable in one agent invocation)
- Subtasks must not overlap (MECE)
- Together they must fully cover the goal
- For each subtask, list any other subtasks it depends on
- Default to parallel execution; use sequential only when a data dependency requires it
- Cap fan-out at [N] parallel workers
Output format:
[
  { "id": "1", "task": "...", "context": "...", "depends_on": [], "agent": "..." },
  ...
]
```

### 3.3 Description Field as Router

From Claude Code docs and Sathish Raju's guide: the `description` field in a sub-agent definition functions as a routing rule, not a label. The main agent matches user intent against descriptions. Write descriptions as trigger conditions:

```yaml
# Bad:
description: "Code reviewer"

# Good:
description: >
  Expert code review specialist. Use immediately after writing or modifying code.
  Proactively reviews for quality, security, and maintainability.
  Invoke when: user asks for review, code has just been written, or before merging.
```

### 3.4 Model Tiering

Coordinator agents should run the most capable model (Opus); workers can run faster, cheaper models:
- **Orchestrator/Coordinator**: Opus (high-level reasoning, architectural judgment, synthesis)
- **Implementation workers**: Sonnet (balanced coding performance)
- **Exploration/search workers**: Haiku (fast, cheap file discovery, pattern matching)

Set a default sub-agent model globally and override per-agent in frontmatter.

---

## 4. callable_agents Configuration

### 4.1 Sub-agent Definition (Markdown + YAML frontmatter)

```yaml
---
name: code-reviewer
description: >
  Expert code reviewer. Use immediately after writing or modifying code.
  Proactively reviews for quality, security, and maintainability.
model: sonnet
tools: Read, Glob, Grep
disallowedTools: Edit, Write, Bash
permissionMode: default
---
You are a senior code reviewer. Your goal: find bugs, security issues, and
code quality problems.

When invoked:
1. Run git diff to see recent changes
2. Focus on modified files
3. Review against: correctness, security, performance, readability

Output format:
- CRITICAL: [issues that must be fixed]
- WARNING: [issues that should be fixed]
- SUGGESTION: [optional improvements]
```

Key fields:
- `name`: identifier used when spawning
- `description`: routing signal (how the coordinator decides to delegate)
- `model`: can override parent model
- `tools`: allowlist only; restricts what the worker can do
- `disallowedTools`: explicit block list
- `permissionMode`: `default`, `acceptEdits`, `bypassPermissions`

### 4.2 SDK Configuration (Python)

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async for message in query(
    prompt="Use the code-reviewer agent to review this codebase",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Glob", "Grep", "Agent"],  # "Agent" required for sub-agents
        agents={
            "code-reviewer": AgentDefinition(
                description="Expert code reviewer for quality and security reviews.",
                prompt="Analyze code quality and suggest improvements.",
            ),
            "security-auditor": AgentDefinition(
                description="Security-focused reviewer. Finds vulnerabilities.",
                prompt="You are a security expert. Find vulnerabilities.",
            ),
        }
    )
):
    if "result" in message:
        print(message.result)
```

Note: `"Agent"` must be in `allowedTools` for the main agent to invoke sub-agents.

### 4.3 Sub-agent Spawning Allowlist

In Claude Code v2.1.63+, you can restrict which sub-agents the main agent can spawn:

```yaml
# In parent agent or CLAUDE.md:
allowedAgents:
  - worker
  - researcher
  - code-reviewer
# If agent tries to spawn anything else, it is blocked.
```

### 4.4 File System Locations (Claude Code)

| Location | Scope | Priority |
|---|---|---|
| Managed settings `.claude/agents/` | Organization-wide | 1 (highest) |
| `--agents` CLI flag | Current session | 2 |
| Project `.claude/agents/` | Current project | 3 |
| User `~/.claude/agents/` | All projects for user | 4 (lowest) |

Organization-managed definitions override project/user definitions with the same name.

---

## 5. Thread Routing Patterns

### 5.1 Primary Thread vs Sub-agent Thread

- **Primary (coordinator) thread**: maintains high-level strategy, user intent, task state, and result synthesis. Never does file editing or tool execution in coordinator mode.
- **Sub-agent thread**: isolated context window, own tool access, runs independently. Returns only final output to parent — all intermediate noise is discarded.
- **Background vs foreground**: `run_in_background: true` fires a sub-agent without blocking the coordinator. Coordinator can dispatch multiple background agents then poll/await results.

### 5.2 Context Inheritance

Sub-agents by default inherit:
- Parent's permission level
- Parent's allowed tools (unless overridden in agent definition)
- Parent's git context

Sub-agents do NOT inherit:
- Parent's conversation history (clean context window)
- Parent's in-progress tool calls

Fork agents (advanced): inherit parent's full conversation history. Designed for prompt-cache exploitation: parallel children sharing identical prefix get ~90% cache discount on shared context (claude-code-from-source.com ch9).

### 5.3 Message Tracking

In the Agent SDK, messages from within a sub-agent's context include a `parent_tool_use_id` field for tracing which messages belong to which sub-agent execution.

---

## 6. Result Merging Strategies

From Zylos Research fork-merge analysis and AgentPMT distributed systems article:

| Strategy | Mechanism | Best For | Weakness |
|---|---|---|---|
| Orchestrator synthesis | Coordinator reads all outputs, writes unified result | Open-ended tasks | Puts synthesis burden on coordinator context |
| Concatenation + deduplication | Join outputs, remove redundancy | Consistent additive results (different facts found) | Fails on contradictory findings |
| Voting / majority | Each agent votes; majority wins | Classification, factual Q&A | Fails when majority is wrong |
| Confidence-weighted merge | Agents report confidence; higher wins | Tasks with natural confidence signal | Confidence calibration is hard |
| Blackboard / shared memory | Agents write to shared workspace; conflict resolver adjudicates | Long-running collaborative tasks | Coordination overhead; shared mutable state risks |
| CRDT-style | Merge function guaranteed to converge regardless of order | Distributed, eventually consistent | Limited applicability |

**Practical rule**: define your merge strategy before fanning out. If you cannot specify how conflicting results will be reconciled, you are not ready for the fan-out pattern.

**Coordinator synthesis prompt pattern**:
```
You are completing a final aggregation step.

Original task: {original_task}

Worker results:
{worker_results}

Instructions:
- Do not concatenate blindly. Synthesize.
- Resolve conflicts between workers (note both perspectives if unresolvable).
- Deduplicate overlapping findings.
- Organize by severity/priority, not by which worker found it.
- Flag which subtasks failed or returned partial results.
```

---

## 7. Error Handling for Sub-agent Failures

From the error-coordinator.md agent definition (github.com/rohitg00/awesome-claude-code-toolkit) and claudecodeguides.com supervisor-worker guide:

### 7.1 Error Classification

1. **Transient**: network timeout, rate limit, temporary unavailability → retry
2. **Permanent**: permission denied, invalid input, model refused → abort or fallback
3. **Degraded**: partial output produced → accept minimum viable output
4. **Unknown**: unexpected failure → escalate to human

### 7.2 Three Levels of Error Handling

**Level 1 — Worker-level isolation**: Each worker catches its own exceptions and returns a structured failure object. The coordinator sees `{"status": "failed", "error": "...", "partial": "..."}`, not an unhandled exception.

**Level 2 — Retry with backoff**: For transient failures, retry the specific worker only. Exponential backoff with jitter: 1s, 2s, 4s, 8s. Max retries: 3 for rate limits, 2 for timeouts, 0 for permission errors. Use idempotency keys to prevent duplicate side effects on retry.

**Level 3 — Supervisor recovery**: After aggregation, pass the list of failed subtasks back to the coordinator and ask it to either:
- Attempt different approaches for failed tasks
- Declare partial completion with explicit gaps
- Escalate for human review

```python
async def run_worker_with_retry(subtask, max_retries=2):
    for attempt in range(max_retries + 1):
        result = await run_worker(subtask)
        if result["status"] == "success":
            return result
        if result["error_type"] == "permanent":
            return result  # no retry
        # transient: wait and retry
        await asyncio.sleep(2 ** attempt + random.random())
    return {"status": "failed", "subtask": subtask, "attempts": max_retries + 1}
```

### 7.3 Circuit Breaker

After N consecutive failures from a single agent within a time window, stop invoking it and route to fallback or escalate. Prevents cascading load on a degraded agent.

### 7.4 Partial Result Acceptance

Define minimum viable output per stage. If 8 of 10 parallel workers succeed, deliver the 8 results and flag the 2 gaps explicitly. Do not abort the entire pipeline on partial failure.

### 7.5 Checkpoint-based Recovery

For long-running multi-phase pipelines, save workflow state at each successful stage checkpoint. Recovery resumes from the last checkpoint, not from scratch.

---

## 8. Recommended Default Configuration

Based on production patterns and the Claude Code sub-agent system:

### 8.1 Team Topology: Supervisor + Fan-Out with Review Gate

```
User request
    ↓
Coordinator (Opus)
    ↓ decompose
  [task graph: parallel workers + sequential dependencies]
    ├── Worker 1 (Sonnet)
    ├── Worker 2 (Sonnet)
    └── Worker 3 (Sonnet, if needed)
    ↓ await all
Reviewer (Sonnet, read-only)
    ↓
Coordinator synthesizes final output
```

### 8.2 CLAUDE.md Multi-Agent Configuration Block

```markdown
## Multi-Agent Configuration

### Agent Roles
- **coordinator**: Receives user task, decomposes, dispatches, synthesizes
  - Model: opus; Tools: Agent, Read, Glob, Grep (no Edit/Write/Bash)
- **implementer**: Executes code changes
  - Model: sonnet; Tools: Read, Write, Edit, Bash
- **reviewer**: Quality/security review
  - Model: sonnet; Tools: Read, Glob, Grep (read-only)
- **explorer**: Fast codebase search
  - Model: haiku; Tools: Read, Glob, Grep (read-only)

### Delegation Rules
- Tasks touching > 3 files: decompose and delegate
- Tasks < 1 file, < 20 lines: execute directly (no sub-agents)
- Any review task: always use reviewer agent (never self-review)
- Parallel execution: use when subtasks have no data dependencies
- Sequential: only when a later task requires output from an earlier one

### Task Granularity
- Each sub-agent task: completable within ~30 minutes
- Fan-out cap: 8 parallel workers maximum
- Minimum subtask size: tasks under ~5 seconds run faster sequentially
```

### 8.3 Failure Defaults

- Max retries per worker: 2 (transient errors only)
- Worker timeout: 5 minutes
- Partial result threshold: proceed if >= 70% of workers succeed
- On permanent failure: log, flag in output, continue with partial results
- Circuit breaker: open after 5 consecutive failures in 60 seconds

---

## 9. Pattern-Specific Open Questions

1. **Coordinator context budget**: How large can the coordinator's context grow as it accumulates worker results before synthesis quality degrades? Is there a token threshold above which the coordinator should itself delegate synthesis to a sub-agent?

2. **Dynamic vs static task graphs**: Should decomposition be fully upfront (full plan type) or iterative (one step at a time, feeding results back)? When does iterative planning justify its overhead?

3. **Worker-to-worker communication**: The basic pattern has workers reporting only to coordinator. For collaborative tasks (e.g., one worker's output is direct input to another), what is the cleanest way to express this without reverting to a single-agent monolith?

4. **Fork vs fresh sub-agent**: Fork agents inherit parent history (enabling prompt cache discount) but carry forward context noise. Fresh sub-agents have clean context but pay full token cost. What is the cost/quality crossover point?

5. **Coordinator identity in managed settings**: When should the coordinator be the main Claude Code session vs a dedicated coordinator sub-agent? Does promoting the coordinator to a named sub-agent (with its own `.claude/agents/coordinator.md`) provide benefits for routing and reuse?

6. **Artifact size thresholds**: At what artifact size (file count, line count, token count) does multi-agent handoff become beneficial vs a single large-context call? Concrete thresholds for the managed agents context?

7. **Team vs sub-agents**: Claude Code docs distinguish sub-agents (single-session, coordinator-invoked) from agent teams (multi-session, peer communication). What patterns genuinely require agent teams vs sub-agents, and what are the operational costs of each?

8. **Cost accounting**: With ~15x token multiplier for multi-agent runs, what is the correct decision rule for when to invoke the coordinator pattern? Is there a per-task complexity signal that reliably predicts multi-agent ROI?

---

## 10. Key Sources

- Anthropic Engineering Blog: "Scaling Managed Agents: Decoupling the brain from the hands" (2026-04-10): https://www.anthropic.com/engineering/managed-agents
- Claude Code Docs — Sub-agents: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- Claude Code Docs — Agent SDK Subagents: https://docs.anthropic.com/en/docs/claude-code/sdk/subagents
- Medium / Jiten Oswal: "The Architecture of Scale: A Deep Dive into Anthropic's Sub-Agents" (2026-02-11): https://medium.com/codetodeploy/the-architecture-of-scale-a-deep-dive-into-anthropics-sub-agents-6c4faae1abda
- claude-code-from-source.com ch10: "Tasks, Coordination, and Swarms": https://claude-code-from-source.com/ch10-coordination/
- AgentPatterns.ai — Agent Composition Patterns: http://agentpatterns.ai/agent-design/agent-composition-patterns/
- AgentPMT — "Two Agents Are a Distributed System" (2026-01-20): https://www.agentpmt.com/articles/multi-agent-coordination-distributed-systems-2026
- Zylos Research — "AI Agent Fork-Merge Patterns" (2026-03-10): https://zylos.ai/research/2026-03-10-ai-agent-fork-merge-patterns
- claudecodeguides.com — "Supervisor-Agent Worker-Agent Pattern" (2026-03-20): https://claudecodeguides.com/supervisor-agent-worker-agent-pattern-claude-code/
- github.com/rohitg00/awesome-claude-code-toolkit — error-coordinator.md
- Medium / Douglas Liles — "AI Agent Workflow Orchestration" (2026-01-03): https://medium.com/%40dougliles/ai-agent-workflow-orchestration-d49715b8b5e3
- ROMA paper: arXiv:2602.01848 (recursive task decomposition, MECE, dependency-aware DAG execution)
- RDD paper: arXiv:2505.02576 (Recursive Decomposition with Dependencies)
- Asana AI Teammates (2026-03-17): https://asana.com/resources/ai-teammates-overview
- Notion Custom Agents (2026-02-24): https://www.notion.com/blog/introducing-custom-agents

# Phase 1 Task-Gated Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace lead-0's free-form Phase 1 interview with task-gated pacing so the model never asks two questions at once or advances without user signal.

**Architecture:** Replace the Phase 1 section in `.claude/agents/lead-0.md` (lines 49-72) with a task protocol that creates one task per question, enforces a single-task invariant via `TaskList` checks, and waits for user signal before advancing.

**Tech Stack:** Claude Code Task tools (TaskCreate, TaskUpdate, TaskList), lead-0 agent prompt

---

### Task 1: Replace Phase 1 section in lead-0.md

**Files:**
- Modify: `.claude/agents/lead-0.md:49-72`

- [ ] **Step 1: Replace the Phase 1 section**

Open `.claude/agents/lead-0.md` and replace lines 49-72 (from `## Phase 1 — Design dialogue` through the `Output: write...` line) with:

```markdown
## Phase 1 — Design dialogue

Ask the user one design question at a time using the Task tool for pacing. **Never ask two questions in one message. Never advance without the user signaling readiness.**

### Task protocol

For each question:

1. Call `TaskList` — verify no `in_progress` or `pending` design tasks exist. If one exists, you jumped ahead. Stop and wait.
2. Call `TaskCreate`:
   - `subject`: `"Design: <topic>"` (e.g., `"Design: Model selection"`)
   - `description`: The question you are about to ask
   - `activeForm`: `"Discussing <topic>"` (e.g., `"Discussing model selection"`)
3. Set the task to `in_progress` and ask the question in conversation.
4. Wait for the user's answer. The user may explore, chat, or dispatch agents — the task stays `in_progress`.
5. Mark the task `completed`.
6. Say "ready when you are" or similar. Do NOT create the next task.
7. When the user signals to continue, go to step 1.

**Invariant:** At most one design task may exist at a time.

### Topic guide

Create questions dynamically based on previous answers. Use this as a reference — skip topics that don't apply:

1. **Create or update?** — new agent, or update an existing one? If update, ask for agent ID (or list existing agents via `agents-expert` to help them pick).
2. **Name** — what to call the agent (or confirm existing name if updating)
3. **Purpose** — one-sentence description
4. **Single agent or team?** — if team, how many and what roles
5. **Model** — Opus / Sonnet / Haiku (Opus for reasoning-heavy, Sonnet for balanced, Haiku for speed)
6. **Tools** — `agent_toolset_20260401` (full) or specific tools; any custom tools?
7. **Permission policies** — `always_allow` or `always_ask` for specific tools
8. **MCP servers** — external integrations (name + URL, no credentials)
9. **Skills** — Anthropic pre-built (xlsx, pptx, docx, pdf) or custom
10. **System prompt** — draft one based on answers, user confirms or edits
11. **Environment** — packages needed, networking mode (unrestricted vs limited)
12. **Resources** — GitHub repos or files to mount
13. **Vaults** — existing vault IDs for MCP auth, or create new
14. **Smoke test prompt** — what to send to verify the agent works
15. **Memory stores (optional)** — persistent cross-session knowledge. Existing store IDs, or create new ones with name + description. Requires research preview access.
16. **Outcome (optional)** — if the user wants goal-directed validation: description, rubric (inline or file), max_iterations (default 3, max 20). Requires research preview access.

For teams: repeat agent-level questions for each agent, then ask about callable_agents handoff.

### Finishing Phase 1

After the last relevant question is completed:
1. Announce "all design questions covered."
2. Wait for user signal.
3. Write `$RUN_DIR/design/agent-specs.json` from conversation context.
```

- [ ] **Step 2: Verify the edit**

Read `.claude/agents/lead-0.md` and confirm:
- Phase 1 section contains the task protocol
- Phase 2 section (`## Phase 2 — Human approval gate`) still starts immediately after
- No duplicate or orphaned content

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/lead-0.md
git commit -m "Replace Phase 1 free-form interview with task-gated questions"
```

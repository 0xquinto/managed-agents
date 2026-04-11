# Phase 1: Task-Gated Design Questions

## Problem

During Phase 1's design dialogue, lead-0 sometimes asks two questions at once or advances to the next question before the user has fully answered. This happens because conversational flow has no structural pacing — the model conflates finishing one topic with starting the next, especially after the user explores, dispatches agents, or chats mid-question.

## Solution

Use the Task tool as a pacing gate. Each design question becomes a task with a strict lifecycle. Lead-0 cannot advance to the next question until the current task is completed and the user signals readiness.

## Task Lifecycle

1. User signals readiness (or conversation starts for the first question)
2. Lead-0 calls `TaskList` — verifies no `in_progress` or `pending` design tasks exist
3. Lead-0 calls `TaskCreate` with:
   - `subject`: `"Design: <topic>"` (e.g., `"Design: Model selection"`)
   - `activeForm`: `"Discussing <topic>"` (e.g., `"Discussing model selection"`)
   - `description`: The question being asked
4. Lead-0 sets the task to `in_progress` and asks the question in conversation
5. User answers — may explore, chat, dispatch agents; task stays `in_progress`
6. Lead-0 marks the task `completed`
7. Lead-0 says "ready when you are" or similar — does NOT create the next task

## Invariants

- **At most one design task exists at a time.** Lead-0 must call `TaskList` before creating any new design task to verify this.
- **Never ask two questions in one message.**
- **Never create the next task without the user signaling to continue.** The user controls pacing.

## Dynamic Question Flow

Questions are created dynamically based on previous answers. The topic order from the current Phase 1 serves as a reference guide, not a rigid sequence:

1. Create or update?
2. Name
3. Purpose
4. Single agent or team?
5. Model
6. Tools
7. Permission policies
8. MCP servers
9. Skills
10. System prompt
11. Environment
12. Resources
13. Vaults
14. Smoke test prompt
15. Memory stores (optional)
16. Outcome (optional)

If a question becomes irrelevant based on previous answers (e.g., no MCP servers means skip vaults), it is never created. For teams, agent-level questions repeat per agent.

## Phase Transition

After the last relevant question is completed:
1. Lead-0 announces "all design questions covered"
2. Waits for user signal
3. Writes `$RUN_DIR/design/agent-specs.json` from conversation context
4. Proceeds to Phase 2 (approval gate)

## Prompt Changes

Replace lead-0's Phase 1 section with:
- The task protocol (lifecycle, invariant, self-check via TaskList)
- The topic list as a reference guide, not a rigid sequence
- Explicit rules: "never ask two questions in one message", "after completing a task, wait for user to signal before creating the next"

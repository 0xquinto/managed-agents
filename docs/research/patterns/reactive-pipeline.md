# Reactive Pipeline Pattern

**Research date:** 2026-04-09  
**Pattern category:** Agentic automation  
**Abstract model:** Event → Agent → Artifact → Delivery

---

## 1. Pattern Definition

A **reactive pipeline** is an agent workflow that activates in response to an external event rather than a human prompt. The pipeline has four invariant stages:

1. **Event** — An external system emits a signal (HTTP webhook POST, queue message, schedule tick, comment mention).
2. **Agent** — Claude receives a normalized representation of the event, enriches it with context from connected tools, reasons about the required action, and executes a sequence of tool calls.
3. **Artifact** — The agent produces a concrete output: a pull request, a ticket comment, a drafted reply, a Slack message, a file, or an API mutation.
4. **Delivery** — The artifact is posted back to the originating system or routed to a downstream channel.

The pipeline is stateless between invocations but may read and write shared state (a ticket tracker, a Git branch, a queue) as part of its processing steps. Human review is optional and can be inserted between the Artifact and Delivery stages, or gated by a confidence threshold computed during the Agent stage.

**Concrete instantiations found in the wild:**

| Instance | Trigger | Artifact | Delivery |
|---|---|---|---|
| Issue-to-PR bot | GitHub issue opened / `@claude` mention | Git branch + code changes + test run | Pull request |
| Alert fixer | PagerDuty / Datadog / Sentry webhook | Code fix + analysis comment | PR or GitHub issue comment |
| Support auto-responder | Zendesk / Jira ticket created | Drafted reply (RAG-augmented) | Ticket comment or draft |
| CI failure fixer | `workflow_run` completed with failure | Code edit + commit | Push to PR branch |
| PR reviewer | `pull_request` opened / synchronize | Review comment set | GitHub PR review |
| Incident enricher | PagerDuty alert | Enriched incident brief | Slack message to on-call channel |
| Issue triager | GitHub issue opened | Labels + assignee | Issue update via GitHub API |
| Webhook automation | Any HTTP POST (Stripe, Linear, Notion) | Classification / action output | API call or notification |

---

## 2. Common Trigger Types Found

### 2.1 Inbound HTTP Webhook (most common)

The external system POSTs a signed JSON payload to a public endpoint owned by the pipeline. The receiver must:

- Respond `200 OK` within 3–5 seconds (before external service retries).
- Verify the HMAC-SHA256 signature using a shared secret.
- Push the normalized payload to an async queue; never block on LLM inference inside the webhook handler.

**Sources observed:** GitHub (`pull_request`, `issues`, `issue_comment`, `push`, `workflow_run`), PagerDuty (v3 webhooks), Datadog (monitor alerts), Sentry (`issue.created`, `event.alert`), Zendesk (trigger rules), Jira (REST-registered webhooks), Slack (Event Subscriptions, `app_mention`, `message.channels`), Stripe, Linear, Notion.

### 2.2 `@mention` / Comment Trigger (human-initiated reactive)

A human types `@claude <instruction>` in a GitHub PR comment, issue, or Slack thread. The platform webhook fires; the pipeline checks for the mention keyword before proceeding. This is the lowest-friction adoption path — the agent only runs when explicitly summoned.

**Used by:** `anthropics/claude-code-action@v1` (interactive mode), Hookdeck + Trigger.dev pattern, Computer Agents platform.

### 2.3 GitHub Actions Event Triggers (CI-native)

GitHub Actions `on:` block events route directly into the pipeline without a separate webhook server:

- `pull_request: types: [opened, synchronize]` — fires on every PR update.
- `issues: types: [opened, assigned, labeled]` — fires on issue lifecycle events.
- `issue_comment: types: [created]` — fires on any comment.
- `workflow_run: types: [completed]` — fires when another workflow finishes (used for CI-failure auto-fix).
- `repository_dispatch: types: [alert-name]` — fires when an external system (PagerDuty forwarder, Datadog webhook bridge) calls the GitHub API.
- `schedule: cron: "..."` — time-based polling (error monitors, repo health checks).

### 2.4 Scheduled / Cron Poll

When a platform does not support outbound webhooks, the pipeline polls on a schedule (hourly, daily). Used by the Autonomy-AI on-call agent to scan Datadog logs every hour and create Linear tickets. Lower latency than pure polling patterns; accept 1–60 minute response lag in exchange for simpler infrastructure.

### 2.5 Queue / Pub-Sub Consumption

A separate webhook receiver puts normalized events on a Redis queue, SQS, or Cloud Pub/Sub topic. Agent workers pull from the queue asynchronously with configurable concurrency (10–50 workers typical). This decouples ingestion latency from LLM inference latency and enables horizontal scaling.

---

## 3. Common Processing Steps

The steps between trigger receipt and artifact delivery follow a consistent pattern across all instances observed:

### Step 1: Ingest and Normalize
Parse the raw webhook payload into a canonical internal schema. Different sources (PagerDuty v3, Datadog, Sentry) have incompatible formats; a parser/normalizer layer abstracts this. Queue the normalized event for async processing. Return `200 OK` immediately.

### Step 2: Deduplication / Idempotency Check
Before doing any LLM work, check whether this event has already been processed. Keying on `{platform}:{eventType}:{entityId}` with a 1-hour TTL prevents duplicate PRs or duplicate Slack messages from rapid webhook retries. The `oncall-agent` action defaults to a 0.7 similarity threshold and 24-hour lookback window for semantic deduplication of alerts.

### Step 3: Context Enrichment
The agent fetches additional context that was not in the webhook payload:
- **For alerts:** Sentry REST API (full stack trace, affected users, release data), Datadog metrics (error rates, latency, CPU), GitHub (recent commits touching relevant files), runbook knowledge base (Sanity CMS, vector DB).
- **For tickets:** RAG query against resolved tickets and help-center docs, CRM lookup (customer plan, account value), conversation history.
- **For PRs:** `git diff` output (only the diff, not full files — reduces token cost 70–90%), CI log tail, test results.

### Step 4: Classification / Confidence Scoring
The agent classifies the event and assigns a confidence score. This gates the next step:
- **Support tickets:** Classify as bug, billing, feature-request, how-to, etc. Low-confidence classifications route to human triage queue.
- **Alerts:** Classify as transient / systemic / data issue. High-confidence + low-risk = auto-execute. Low-confidence = Slack approval request.
- **PRs:** Classify severity of issues found (blocking / informational).

The Vigil system uses explicit thresholds: auto-execute if confidence > 90% AND runbook match > 85% AND risk = LOW.

### Step 5: Chain-of-Thought Reasoning + Tool Execution
The agent reasons step-by-step (structured Chain-of-Thought prompts enforce this), then issues a sequence of tool calls:
- Read files, run tests, inspect logs.
- Create or update tickets, PRs, branches.
- Post comments or Slack messages.
- Call external APIs (update PagerDuty status, create Linear issue, post Zendesk comment).

Tool calls are bounded: `max_files_changed` (default 10 for oncall-agent), `max_iterations` (default 5 for PR autofix), `timeout_minutes` (default 10).

### Step 6: Artifact Assembly
Produce the deliverable: a coherent PR description + diff, a ticket comment with reply + suggested next steps, an enriched incident brief, a labeling update. The artifact should include enough context for a human reviewer to evaluate it quickly.

### Step 7: Delivery
Post the artifact back:
- **GitHub:** `GITHUB_TOKEN` with `contents: write`, `pull-requests: write`, `issues: write` permissions.
- **Slack:** Incoming webhook URL or bot token; post to incident channel or thread.
- **Ticketing:** Write-back via unified API (Zendesk REST, Jira REST, Linear GraphQL).
- **Alert source:** Update PagerDuty incident with notes/annotations; resolve if fixed.

---

## 4. Common Delivery Mechanisms

| Delivery type | When used | Notes |
|---|---|---|
| **Pull request** | Code fix, new feature from issue | Never auto-merge — always human review required |
| **PR comment / review** | Code review, analysis, suggestions | Inline diff comments preferred for targeted feedback |
| **GitHub issue comment** | Triage output, analysis when fix not possible | Include confidence score and reasoning |
| **Issue label + assignee update** | Triage routing | Low-cost, high-value; no human needed |
| **Slack message** | Incident brief, routing notification, PR summary | Post to named channel; include direct link to artifact |
| **Ticket comment + status change** | Support auto-responder | Draft mode (human approves before send) is common |
| **Branch + commit push** | CI failure fix, issue-to-code | Pushed to feature branch; human merges via PR |
| **Email** | Fallback when Slack fails | Channel-level degradation fallback |
| **Source system annotation** | PagerDuty incident notes | Audit trail in the originating system |

**Key principle:** The most common pattern is "create artifact for human review, do not auto-apply." Auto-merge, auto-resolve, and auto-reply are opt-in escalations, not defaults.

---

## 5. Recommended Default Configuration for the Orchestrator

### 5.1 Model Selection

| Task complexity | Recommended model | Rationale |
|---|---|---|
| Classification only (triage, labeling) | `claude-haiku-3-5` | Fast, cheap; adequate for classification tasks |
| Standard reactive pipeline | `claude-sonnet-4-5` | Strong reasoning + code; $0.05–0.15 per typical run |
| Complex multi-file code fix | `claude-sonnet-4-5` or `claude-opus-4` | Upgrade if fix quality is insufficient |

The oncall-agent, PR autofix, and claude-code-action all default to Sonnet for code tasks. Haiku is appropriate for classification-only steps in a multi-stage pipeline.

### 5.2 Tool / Permission Configuration

**Minimum required permissions (GitHub-based pipelines):**
```yaml
permissions:
  contents: write        # read files, push commits, create branches
  pull-requests: write   # create PRs, post PR comments
  issues: write          # label, comment, assign issues
  actions: read          # read CI logs (for workflow_run trigger)
```

**Tool categories to enable:**
- **File system read** — always required for context enrichment.
- **File system write + git** — required for code-fix and issue-to-PR pipelines; restrict `max_files_changed`.
- **GitHub API** — required for PR/issue creation and updates.
- **External read APIs** (Sentry, Datadog, PagerDuty, Linear) — required for enrichment; use read-only API keys.
- **External write APIs** (Jira comment, Zendesk reply, PagerDuty annotation, Slack post) — required for delivery; scope minimally.
- **Shell / test runner** — optional; enable only for CI-failure fix patterns; adds risk surface.
- **RAG / vector DB** — optional; significantly improves support ticket reply quality.

**Protected paths (never modify automatically):**
- `*.env`, `secrets/**`, `*.pem`, `*.key` — credentials.
- `CODEOWNERS`, `.github/workflows/**` — governance files (configurable).
- Database migration files — high blast-radius changes.

### 5.3 Safety / Execution Guardrails

```yaml
max_iterations: 10          # hard cap on agent turns per invocation
timeout_minutes: 10         # kill the runner after this
max_files_changed: 10       # PR auto-fix scope limit
auto_merge: false           # never auto-merge; humans approve
allowed_bots: []            # empty = only humans can trigger interactive mode
confidence_threshold: 0.75  # below this, route to human instead of acting
deduplication:
  enabled: true
  lookback_hours: 24
  similarity_threshold: 0.7
```

### 5.4 Async Architecture (non-GitHub deployments)

For webhook receivers outside GitHub Actions:

```
Webhook receiver (FastAPI / Express)
  → HMAC-SHA256 verification
  → Return 202 immediately
  → Push to Redis / SQS queue
    → Worker pool (concurrency: 10–50)
      → Deduplication check
      → Context enrichment
      → LLM inference (with retry + exponential backoff)
      → Artifact delivery
      → Dead Letter Queue on exhausted retries
```

**Retry policy:**
- Transient failures (rate limit, timeout, 503): exponential backoff, 3 retries, base 1s, cap 60s.
- Non-retryable failures (schema error, hallucination, safety filter): send directly to DLQ.
- DLQ retention: 7 days standard, 30 days for model failures, 90 days for safety-filter triggers.

### 5.5 Error Handling Architecture

**Failure categories and responses:**

| Failure type | Response |
|---|---|
| LLM rate limit / timeout | Retry with exponential backoff (up to 3x) |
| Token limit exceeded | Truncate context (prioritize diff > logs > history), retry |
| Low-confidence output | Skip auto-delivery; route to human escalation queue |
| External API unreachable | Circuit breaker; degrade to analysis-only (no write-back) |
| Max iterations reached | Post partial analysis comment; flag for human |
| Safety filter triggered | Log to 90-day DLQ; page on-call; no output posted |
| Repeated DLQ accumulation (> 50/hr) | Alert engineering; likely systemic issue |

**Self-correction (Try-Rewrite-Retry):** If a tool call fails with a parseable error (JSON schema violation, API 4xx), pass the error back to Claude with the failed output and ask for a corrected version. Cap at 3 self-correction attempts before escalating.

**Fallback model escalation:** If a smaller model fails 3 times, switch to a more capable model (e.g., Haiku → Sonnet → Opus) for that invocation.

### 5.6 Human-in-the-Loop Points

The following gates are where humans intercept the pipeline by default:

| Gate | Trigger condition | Human action |
|---|---|---|
| **Confidence gate** | Classification confidence < threshold | Human reviews routing decision |
| **High-risk change gate** | Files changed > limit, or protected path touched | Human approval before merge |
| **Draft delivery** | Support reply or PR description generated | Human edits and sends |
| **PR review** | PR created by agent | Human code review before merge |
| **DLQ review** | Task failed all retries | Human inspects, edits prompt, resubmits |
| **Alert: low confidence** | Vigil-style: confidence < 90% or risk != LOW | Slack approval request to on-call |
| **Explicit `@claude` gate** | Interactive mode only | Human must mention agent to trigger |

**Never auto-apply without human review:**
- Merging pull requests.
- Sending external communications to end-customers.
- Modifying production database schemas or migration files.
- Changes touching > N files (configurable, default 10).

---

## 6. Pattern-Specific Phase 1 Questions

These are the questions the orchestrator must ask the user before instantiating a reactive-pipeline agent:

### Trigger configuration
1. **What event fires this pipeline?** (GitHub webhook event type, Sentry alert, PagerDuty incident, Zendesk ticket, scheduled cron, Slack message, other HTTP webhook)
2. **How is the trigger authenticated?** (HMAC secret, API key, OAuth token — provide the secret or explain where it is stored)
3. **Is this trigger push-based (webhook) or pull-based (scheduled poll)?** If pull-based: what is the acceptable latency / poll interval?
4. **What event subtypes should be filtered in?** (e.g., only `issues.opened` with label `bug`, only PagerDuty severity P1/P2, only Sentry `issue.created` not `issue.resolved`)

### Context and enrichment
5. **What external systems should the agent read for context?** (e.g., Datadog metrics, GitHub commit log, Zendesk ticket history, RAG knowledge base, customer CRM)
6. **Provide API keys / credentials for each read-only data source.**
7. **Is there a CLAUDE.md or system context file that describes the codebase / domain?** (Critical for code-fix pipelines — without it, fix quality degrades significantly)

### Output and delivery
8. **What is the target delivery channel?** (GitHub PR, Slack channel name, Zendesk ticket comment, PagerDuty annotation, email)
9. **Should the output be delivered automatically, or held for human approval first?** (Draft mode vs. auto-post)
10. **What write credentials does the agent need?** (GitHub token with specific permissions, Slack webhook URL, Jira API key, etc.)

### Guardrails and scope
11. **What is the maximum scope of a single agent run?** (max files changed, max iterations, timeout)
12. **Are there protected files or paths the agent must never touch?**
13. **What is the confidence threshold below which the agent should escalate to a human instead of acting?**
14. **Who should be notified when the agent cannot complete a task?** (Slack handle, email, PagerDuty escalation policy)

### Cost and frequency
15. **How frequently do events arrive?** (Helps estimate token spend — e.g., 50 PRs/month at $0.10 each = $5/month vs. 500 Sentry alerts/day at $0.15 each = $2,250/month)
16. **Are there draft PRs, bot-generated events, or low-signal events that should be filtered out to control costs?**

---

## References

- `anthropics/claude-code-action` — official Anthropic GitHub Action (7K stars, v1.0): https://github.com/anthropics/claude-code-action
- `claude-on-call` GitHub Action (PagerDuty/Datadog/Sentry → Claude → PR): https://github.com/marketplace/actions/claude-on-call
- Autonomy-AI on-call agent (Datadog → Linear → PR): https://github.com/marketplace/actions/ai-on-call-agent-error-monitor
- GitHub automation with Hookdeck + Trigger.dev + Claude: https://hookdeck.com/webhooks/platforms/github-trigger-dev-claude-automation
- Anthropic ticket routing guide: https://docs.anthropic.com/en/docs/about-claude/use-case-guides/ticket-routing
- AI auto-responder for Zendesk/Jira (Truto blog): https://truto.one/blog/how-to-build-an-ai-product-that-auto-responds-to-zendesk-and-jira-tickets/
- Webhook-triggered LLM workflows (Codehooks.io): https://codehooks.io/blog/building-llm-workflows-javascript
- Dead Letter Queues for AI agents (Google Cloud pattern): https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production
- Error handling and human escalation in production agents: https://www.arunbaby.com/ai-agents/0033-error-handling-recovery/
- Multi-platform webhook triggers (awesome-agentic-patterns): https://github.com/nibzard/awesome-agentic-patterns/blob/main/patterns/multi-platform-webhook-triggers.md
- Vigil autonomous incident response system (9-stage state machine): https://devpost.com/software/productionagents
- Sentry webhook AI agent (WebhookAgent guide): https://webhookagent.com/guides/how-to-process-sentry-error-webhooks-with-ai-agent
- Claude Code × GitHub Actions complete guide: https://claudelab.net/en/articles/claude-code/claude-code-github-actions-automated-workflow
- Groundy: Claude Code in GitHub Actions (automated PR fixes): https://groundy.com/articles/how-to-run-claude-code-as-a-github-actions-agent-for-automated-pr-fixes/

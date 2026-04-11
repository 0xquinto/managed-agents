# Operator Agent Pattern

Research compiled: 2026-04-09  
Sources: Acceldata, Agentin.ai, Kognitos, Strongly.AI, HashiCorp Vault docs, Zylos Research, agentpatterns.tech, inference.sh, Claw EA, dev.to (multi-tenant MCP), skillful.sh, mcp-agent docs, agentgateway.dev, Corsair, Continue.dev, Scalekit blog, Thallus, Govyn, Aegis/CloudMatos, ibl.ai, agent-vault, gnanaguru.com.

---

## 1. Pattern Definition

The **Operator** pattern describes an agent that acts as a live intermediary between two or more enterprise systems. It abstracts the canonical workflow:

```
System A (source of truth) → Extract → Reconcile → Act → System B (target)
```

The agent does not simply relay data. It reasons about discrepancies, classifies exceptions, decides which system is authoritative for which fields, and takes corrective action — or holds for human approval when the action is irreversible.

**Structural invariants:**
- At least two external system connections (read-source + write-target, or bidirectional)
- Explicit reconciliation step that compares state across systems
- Write operations gated by either confidence threshold or approval workflow
- Full audit trail of every match, mismatch, action, and decision

**Concrete instantiations observed in the wild:**

| Use Case | System A (read) | System B (write) | Reconcile object |
|---|---|---|---|
| Procure-to-Pay | ERP (SAP/NetSuite) + vendor API | ERP (POs, invoices) | Purchase orders vs invoices vs receipts |
| Quote-to-Cash | CRM (Salesforce) | ERP (SAP/Oracle) | Quotes, orders, billing records |
| Intercompany recon | Multiple ERP ledgers | ERP journal entries | Payables vs receivables across entities |
| DevOps triage | Sentry/GitHub issues | Linear, Slack | Bug reports, PRs, sprint tickets |
| Balance-sheet close | GL, billing platform, expense system | ERP/accounting | Transaction records, period balances |
| Slack→Linear bridge | Slack thread | Linear issues | Bug reports, feature requests, status updates |

---

## 2. Common Multi-System Topologies

### 2a. Two-System Read→Write (most common)

```
[MCP Server A: read-only]    [MCP Server B: write-capable]
        ↓                              ↑
    Agent extracts ──── reconciles ──→ proposes action
                                       ↓
                              approval gate (if write)
```

Seen in: Slack→Linear, Sentry→GitHub, Stripe→accounting.

### 2b. Three-Way Match

```
[MCP Server A: purchase orders]
[MCP Server B: goods receipts]     →  Agent  →  [MCP Server C: ERP invoice posting]
[MCP Server C: invoices]
```

Seen in: Procure-to-Pay automation, 2-way and 3-way invoice matching (eZintegrations, Agentin.ai). All three sources are read; one (ERP) receives write actions after match.

### 2c. Multi-ERP Fan-In Reconciliation

```
[MCP Server: Entity A ERP]
[MCP Server: Entity B ERP]   →  reconcile  →  suggest journal entries
[MCP Server: Entity C ERP]                    (human reviews before posting)
```

Seen in: Kognitos intercompany reconciliation. Writes (journal entry suggestions) are proposals only — agent suggests, human posts.

### 2d. Gateway-Multiplexed (operational convenience)

```
[agentgateway or MCP aggregator]
  ├─ MCP Server: SAP (read-only)
  ├─ MCP Server: Salesforce (read-only)
  ├─ MCP Server: ServiceNow (write-capable)
  └─ MCP Server: Slack (write-capable)
         ↓
    Agent sees unified tool namespace with server-prefixed names
    (e.g., sap_get_order, servicenow_create_ticket)
```

Gateway tools: agentgateway, MCPAggregator (mcp-agent SDK), mcp-gateway-registry.  
Benefit: one MCP connection for the agent; server-level tool namespacing prevents collision.  
Trade-off: single gateway is a blast-radius amplifier; prefer per-system server isolation for write paths.

### 2e. Polling Loop (event-driven alternative)

```
Agent polls System A on interval
  → detects delta since last run
  → reconciles against System B state
  → writes or queues approval
```

Seen in: Scalekit DevOps assistant (GitHub PRs → Linear issues → Slack digest). The agent idempotently checks "does a Linear issue already exist for this PR?" before creating one.

---

## 3. Read/Write Permission Models

### Principle: Default Read-Only, Explicit Write Grant

Production deployments consistently apply a two-tier permission structure:

| Tier | Systems | Permission | Rationale |
|---|---|---|---|
| Source of truth | ERP, GL, CRM | Read-only MCP connection | Prevents accidental mutation of authoritative records |
| Action targets | Ticketing, comms, staging tables | Write-capable MCP connection | Bounded scope of automated writes |
| Regulated targets | ERP journal entries, payment systems | Write-capable + approval gate | Human must confirm before irreversible action |

**Read-only enforcement patterns:**
- MCP server configured with scoped API key that only holds `GET` permissions
- Separate OAuth scope set per system (e.g., `salesforce.read` not `salesforce.write`)
- MCP server itself filters tools: write tools simply not exposed in manifest
- Connection-level: database MCP servers pointed at read-replica, not primary

**Write gates (what triggers an approval hold):**
- Financial mutations (post journal entry, approve payment, create invoice)
- External communications (send email, post Slack message to customer channel)
- Deletions or archiving (irreversible data loss)
- Permission/identity changes
- Any action above a configurable threshold (e.g., payment > $200)
- First-time actions with a new counterparty

**Govyn / Claw EA / Thallus pattern:** write-action confirmation enforced at the execution layer (not the prompt layer). Prompt injection cannot bypass a code-level gate on `tool_call.requires_approval == true`.

---

## 4. Reconciliation Strategies

### 4a. Deterministic Rule Matching

Apply ordered matching rules in priority sequence:

```
1. Exact match on primary key (invoice_id, PO_number)
2. Exact match on compound key (vendor_id + amount + date)
3. Fuzzy match on amount + date within tolerance window
4. Manual queue (no match found)
```

Lido, SAYA ReconX, InsightReconcile all expose configurable rule chains. Rules are declarative (no-code or YAML).

### 4b. AI-Augmented Fuzzy Matching

For unstructured or inconsistently formatted data (vendor name on PO = "GE Services", ERP record = "General Electric Services LLC"):

- Semantic embedding similarity
- Contextual field cross-reference (address + weight + date when name differs)
- Confidence threshold: matches above threshold auto-accept, below threshold queue for human

**Key parameter:** confidence threshold is operator-configurable. Lower threshold = more human review, higher = more automation.

### 4c. Discrepancy Classification → Action Mapping

Acceldata's agentic reconciliation taxonomy (widely adopted):

| Discrepancy Type | Agent Action | Notes |
|---|---|---|
| Missing data (lag) | Auto-rerun / backfill trigger | Only if classified as timing issue |
| Missing data (permanent) | Lineage trace + alert | Escalate if not resolved in SLA |
| Transformation error | Generate + apply schema fix | Requires confidence check before applying |
| Duplicate transaction | Cluster exceptions, cancel duplicate PO | High confidence action, approval recommended |
| Amount mismatch | Flag for human review + suggest adjustment | Never auto-correct financial amounts |
| Currency mismatch | Apply FX rate + flag for review | FX calculation is automated, posting is not |

### 4d. Saga-Pattern Write Ordering

For three-way or multi-step writes (Agentsarcade / distributed systems pattern):

1. Each step records completion and its **compensation action**
2. On failure mid-saga, walk backward through recorded steps
3. Only attempt compensation if the forward step was confirmed complete
4. Idempotency key on every write prevents duplicate side-effects on retry

### 4e. Reconciliation Lifecycle Tracking

InsightReconcile / Concourse model:
- Every exception carries: `severity`, `status` (Open → In Progress → Resolved/Dismissed/Escalated), `SLA deadline`, `assigned owner`
- SLA breach auto-escalates to secondary approver
- Audit trail is append-only: every match decision, rule applied, who approved, timestamp

---

## 5. Approval Workflows for Write Actions

### Approval Gate Architecture

The consensus from inference.sh, Govyn, Claw EA, Thallus, Aegis:

```
Agent proposes tool call
      ↓
Approval policy engine evaluates (tool name + arguments + context)
      ↓
   allow / deny / approval_needed
      ↓
If approval_needed:
  - Persist workflow state (execution physically halts)
  - Send structured message to approver (Slack Block Kit / Teams Adaptive Card)
  - Include: action summary, parameters (PII-redacted), approval ID, risk score
  - Mint single-use approval token on confirm
  - Resume with token; log decision + approver identity + timestamp
      ↓
If timeout (configurable, typically hours):
  - Escalate to secondary approver
  - Default action: DENY (fail-closed) for high-risk; ALLOW for low-risk
```

**Critical implementation note:** Approval gates must be enforced at the execution layer, not in the prompt. A prompt instruction ("ask before deleting") can be bypassed by prompt injection or tool indirection. A code-level gate cannot.

### Policy-as-Code Pattern (Claw EA / Aegis / OPA)

```yaml
tool_policy:
  default: deny
  rules:
    - tool: "post_journal_entry"
      action: approval_needed
      threshold: null           # always
    - tool: "create_po"
      action: approval_needed
      condition: "amount > 10000"
    - tool: "get_*"             # all read tools
      action: allow
    - tool: "send_slack_message"
      action: approval_needed
      condition: "channel.type == 'external'"
```

### Approval Routing

| Action type | Route to |
|---|---|
| Financial mutations | Finance team approver |
| Infrastructure / code deploy | Engineering lead |
| External communications | Content/legal reviewer |
| Identity / permission changes | Security team |
| Procurement | Procurement manager |

### Batch Approvals

To prevent approval fatigue: low-risk approvals of the same type within a time window can be batched into a single approval card. High-risk (irreversible) actions always require individual approval.

---

## 6. Error Handling When a System Is Unavailable

### Failure Classification First

Error class determines recovery path:

| Class | Examples | Recovery |
|---|---|---|
| Transient | Timeout, 429, 502-504, network blip | Retry with exponential backoff |
| Auth failure | 401, 403, expired token | No retry; alert operator; rotate credential |
| Permanent | 404, schema mismatch, data not found | Fail fast; log; alert |
| Partial / degraded | Mixed 200/timeout/5xx from same service | Circuit breaker; switch to degraded mode |

### Circuit Breaker (per system)

State machine: `CLOSED` → (N failures in window) → `OPEN` (fast-fail) → (cooldown) → `HALF-OPEN` (probe) → `CLOSED`

**Key configuration:**
- Failure threshold: 3-5 failures to trip
- Cooldown: 30-60 seconds typical
- One circuit breaker per upstream system, not shared
- Only trip on infrastructure failures, not business-logic errors (a "no match found" is not a circuit-trip condition)

### Graceful Degradation Chain

When System A is unavailable in a two-system reconciliation:

```
Level 1: Full reconciliation (both systems available)
Level 2: Read cached/stale snapshot of System A; flag outputs as "based on data from [timestamp]"
Level 3: Queue work items for when System A recovers; notify operator
Level 4: Escalate to human: "Cannot complete reconciliation; System A unavailable since [time]"
```

Always be explicit about degraded state: acknowledge what is unavailable, explain what is still possible, annotate outputs with uncertainty markers.

### Dependency Health Snapshot

Pattern from agentpatterns.tech: lock a health snapshot of all upstream systems **at workflow start**. If any system is below threshold, immediately enter degraded mode rather than discovering it mid-saga. Avoids partial writes where System B was updated but System A read was incomplete.

### Partial-Outage Detection

Partial outage (mixed 200/timeout/5xx) is more dangerous than full outage because the system appears alive. Detection signal: `timeout_rate` and `retry_attempts_per_run` trending up while `tool_2xx_rate` stays non-zero. Response: switch to fail-fast; do not continue retrying until health probe confirms recovery.

---

## 7. Credential Isolation Per System

### Recommended Architecture: Tool/MCP Runtime Layer Isolation

**Do not** give the agent process direct access to credentials. The agent should never see plaintext API keys, OAuth tokens, or passwords.

```
Agent (untrusted process)
   ↓  "create invoice for $500" (no credentials)
MCP Runtime / Tool Gateway (trusted)
   ↓  validates policy + fetches credential from internal vault
   ↓  refreshes token if expired
   ↓  makes authenticated API call
   ↓  sanitizes response (strips tokens, keys, PII)
   ↑  returns clean result only
External System
```

Source: Pattern 7 in gnanaguru.com's 8-pattern taxonomy; CaMeL paper (Google DeepMind); Arcade platform architecture.

### Vault Options by Scale

| Scale | Recommended pattern | Notes |
|---|---|---|
| Local / solo | `agent-vault` (age encryption, per-agent keys, git-stored ciphertext) | Zero hosted dependency; owner key never committed |
| Small team | AWS Secrets Manager / GCP Secret Manager with per-agent IAM roles | Runtime fetch; still in-process after fetch |
| Enterprise | HashiCorp Vault with dynamic secrets + JWT/OIDC auth | Just-in-time provisioning; credentials expire after use; full audit log |

### Per-System Credential Scoping

Each MCP server (= each connected system) gets its own scoped credential:

```
sap_mcp_server       → Vault path: prod/sap/api-key       (read-only scope)
salesforce_mcp_server → Vault path: prod/salesforce/token  (read scope only)
servicenow_mcp_server → Vault path: prod/servicenow/token  (write scope, ticketing only)
slack_mcp_server      → Vault path: prod/slack/bot-token   (post to #internal only)
```

**Strongly.AI pattern (100+ enterprise MCP servers observed):**
- Each MCP server runs in isolated Kubernetes pod
- JIT credentials: provisioned on-demand, auto-revoked after use or short TTL
- Minimum-permission scope at provisioning time
- Per-connection credential lookup (not per-server-config): server holds a credential resolver, not static keys

### What to Never Do

- Shared API key across multiple systems in one config file
- Long-lived admin-scoped tokens in environment variables
- Credentials passed through the agent context/prompt (agent logs are not secret)
- One-server-per-tenant at scale (operationally unsustainable; use multi-tenant isolation patterns instead)

---

## 8. Recommended Default Config (for Claude Managed Agents)

```yaml
# Operator pattern template
pattern: operator

systems:
  source_a:
    mcp_server: "<system-a-mcp>"
    permission: read_only
    credential_scope: "minimum read scope"
    circuit_breaker:
      failure_threshold: 3
      cooldown_seconds: 45

  source_b:
    mcp_server: "<system-b-mcp>"
    permission: read_only
    credential_scope: "minimum read scope"
    circuit_breaker:
      failure_threshold: 3
      cooldown_seconds: 45

  target:
    mcp_server: "<target-system-mcp>"
    permission: write_capable
    credential_scope: "scoped write — specific resource types only"
    approval_required: true  # all writes hold for approval by default

reconciliation:
  matching_strategy: rule_chain   # deterministic first, fuzzy fallback
  confidence_threshold: 0.85      # below = queue for human
  discrepancy_classification: true
  saga_compensation: true         # record compensation for each write step

approval_policy:
  engine: policy_as_code          # not prompt instructions
  default_action: deny
  timeout_hours: 4
  timeout_action: deny            # fail-closed
  routing:
    financial: finance_approver
    external_comms: content_approver
    default: operator_owner
  notification_channel: slack     # or teams

error_handling:
  retry_policy:
    max_retries: 3
    backoff: exponential
    retryable_status: [408, 429, 500, 502, 503, 504]
  degraded_mode:
    on_source_unavailable: queue_and_notify   # do not partial-write
    on_target_unavailable: queue_and_notify
    stale_cache_allowed: false                # operator decision
  health_snapshot_at_start: true

credentials:
  storage: vault                  # never in agent process
  provisioning: jit               # just-in-time, auto-expire
  per_system_isolation: true      # one credential path per system
  audit_log: true
```

---

## 9. Pattern-Specific Questions

These are open design questions for this pattern in the Claude Managed Agents context. Answers should be captured before implementation.

**System authority & conflict resolution**
1. When Systems A and B disagree on a field value, which is authoritative? Is this per-field or per-record-type? Who defines the authority mapping?
2. What is the business definition of "resolved" for a discrepancy? (Matching amounts, matching amounts within tolerance, human confirms match?)

**Write scope and approval thresholds**
3. What is the complete list of write actions the agent is permitted to take autonomously (no approval)? What actions always require approval regardless of confidence?
4. Is there a financial threshold above which all actions require approval regardless of type?
5. Should approval be per-action or per-batch (e.g., approve 50 low-risk POs at once)?

**System availability and SLAs**
6. If the source system is unavailable at reconciliation time, should the agent: (a) abort and retry later, (b) proceed with stale cache, or (c) escalate immediately?
7. What is the SLA for resolving an unmatched exception before it escalates? Who does it escalate to?

**Credential and permission model**
8. Which systems need OAuth user-attribution (actions traceable to a human identity) vs service-account-only credentials?
9. Is there a requirement for credential rotation period (e.g., tokens expire every 24h)?

**Reconciliation logic**
10. What matching keys are available on each system? Are they globally unique, or only unique within one system?
11. For fuzzy matching: what is the acceptable false-positive rate? A high false-positive rate (auto-accepting wrong matches) in financial reconciliation has direct monetary risk.

**Audit and compliance**
12. Does this workflow need a compliance audit trail (SOX, SOC 2, HIPAA)? If so, the audit log must be append-only, include approver identity, and be retained for a defined period.
13. Are there systems in this topology that legally cannot be written to by an automated agent without prior written authorization?

---
name: operator
description: Use when the user wants to build an agent that bridges multiple external systems — extracting data from one, reconciling across others, and taking action. Triggers on "reconcile", "sync between", "cross-reference", "integrate systems", "procurement", "bridge", "workflow automation across tools".
---

# Operator

Abstract pattern: **System A + System B → Extract → Reconcile → Act**

An agent that connects to multiple external systems via MCP, reads data from each, cross-references to find discrepancies or derive actions, and writes results back — with human approval on writes.

## When to Use

- User says "reconcile data between System A and System B"
- User says "sync tickets from Jira to Linear"
- User says "check purchase orders against invoices"
- User says "automate workflow across Slack, GitHub, and Linear"
- User describes any multi-system extract→reason→act workflow
- Key distinction from reactive-pipeline: operator bridges MULTIPLE systems bidirectionally, reactive-pipeline is event→response through one channel

## Pre-filled Configuration

```yaml
model: claude-sonnet-4-6
tools:
  - type: agent_toolset_20260401
    default_config:
      permission_policy: {type: always_ask}     # all tool calls human-approved by default
    configs:
      - name: web_search
        enabled: false
      - name: web_fetch
        enabled: false
mcp_servers: []                                  # user provides per-system MCP servers
environment:
  networking:
    type: limited
    allowed_hosts: []                            # populated from MCP server hosts
    allow_mcp_servers: true
    allow_package_managers: false
```

**Security-first defaults**: `always_ask` on all tools. Limited networking. No web access. Every write requires human approval.

## Questions to Ask (replaces Phase 1)

| # | Question | Why | Example answers |
|---|---|---|---|
| 1 | Name? | Agent identity | "po-reconciler", "jira-linear-sync", "procurement-agent" |
| 2 | Create or update existing? | Agent mode | "create new", "update agt_01abc123" |
| 3 | What systems does it connect to? | Maps MCP topology | "SAP (read) + ServiceNow (write)", "Stripe + QuickBooks" |
| 4 | For each system: MCP URL? | Wires mcp-vaults-expert | `https://mcp.example.com/sap`, `https://mcp.example.com/servicenow` |
| 5 | For each system: read-only or read-write? | Permission model | "SAP: read-only, ServiceNow: read-write" |
| 6 | For each system: auth type + credentials? | Vault per system | "SAP: OAuth, ServiceNow: static bearer" |
| 7 | What is the reconciliation/workflow logic? | Core task description | "Match POs by vendor+amount, flag unmatched > $500" |
| 8 | What write actions can the agent take? | Scopes write permissions | "Create tickets", "Update status fields", "Post Slack messages" |
| 9 | What requires human approval? | Approval policy | "All writes", "Financial actions > $1000", "External communications" |
| 10 | When a system is unavailable? | Error handling | "Queue and retry", "Abort entire run", "Continue with available systems" |
| 11 | Where to report results/discrepancies? | Delivery channel | "Slack #ops", "Email", "Dashboard" |
| 12 | Delivery MCP URL + auth? | Wires delivery | MCP URL + credential, or "same as one of the connected systems" |

## Specialist Dispatch Order

```
1. mcp-vaults-expert                      — one vault + credential per connected system (called N times)
2. agents-expert + environments-expert    — parallel: agent with multiple MCP servers + container
3. sessions-expert                        — session with all vault IDs
4. events-expert                          — smoke test
```

Note: mcp-vaults-expert creates one vault per connected system, each with its own scoped credential. Credential isolation is mandatory — never share credentials across systems.

## System Prompt Template

```
You are an operator agent that bridges multiple systems.

## Connected Systems
[For each system:]
- [SYSTEM_NAME]: [READ_ONLY or READ_WRITE] via MCP server "[MCP_NAME]"

## Task
[RECONCILIATION_LOGIC]

## Process
1. Extract data from source systems (read-only calls)
2. Cross-reference and reconcile
3. Classify discrepancies: exact match / fuzzy match / unmatched / conflict
4. For unmatched items above threshold, prepare write actions
5. Present write actions for approval before executing
6. Execute approved writes
7. Report results

## Write Permission Rules
- Permitted autonomous writes: [AUTONOMOUS_WRITES or "none"]
- Always require approval: [APPROVAL_REQUIRED_WRITES]
- Never auto-approve: financial amounts, external communications, deletions

## Error Handling
- If a source system is unavailable: [UNAVAILABLE_POLICY]
- Never make partial writes when source data is incomplete
- Log all actions with system, timestamp, and result

## Guardrails
- Never modify data in read-only systems
- Never auto-approve financial corrections without human review
- If confidence in a match is below threshold, queue for human review
- Report all discrepancies, even resolved ones, in the final summary
```

## Agent Spec Output

```json
{
  "mode": "create",
  "name": "[user-provided]",
  "model": "claude-sonnet-4-6",
  "system": "[generated from template]",
  "tools": [
    {
      "type": "agent_toolset_20260401",
      "default_config": {
        "permission_policy": {"type": "always_ask"}
      },
      "configs": [
        {"name": "web_search", "enabled": false},
        {"name": "web_fetch", "enabled": false}
      ]
    },
    {"type": "mcp_toolset", "mcp_server_name": "[system_a]"},
    {"type": "mcp_toolset", "mcp_server_name": "[system_b]"},
    {"type": "mcp_toolset", "mcp_server_name": "[delivery]"}
  ],
  "mcp_servers": [
    {"type": "url", "name": "[system_a]", "url": "[system_a_mcp_url]"},
    {"type": "url", "name": "[system_b]", "url": "[system_b_mcp_url]"},
    {"type": "url", "name": "[delivery]", "url": "[delivery_mcp_url]"}
  ],
  "environment": {
    "name": "[name]-env",
    "config": {
      "type": "cloud",
      "packages": {},
      "networking": {
        "type": "limited",
        "allowed_hosts": ["https://[system_a_host]", "https://[system_b_host]", "https://[delivery_host]"],
        "allow_mcp_servers": true,
        "allow_package_managers": false
      }
    }
  },
  "vault_ids": ["[vault_for_system_a]", "[vault_for_system_b]", "[vault_for_delivery]"],

  "_orchestration (not sent to API)": {
    "smoke_test_prompt": "Connect to each system, verify access, and report what data is available. Do not modify any data.",
    "credential_isolation": "one vault per connected system — never share credentials across systems",
    "note": "Template shows 2 systems + 1 delivery. For N systems, repeat mcp_servers, mcp_toolset, allowed_hosts, and vault_ids entries for each connected system."
  }
}
```

## Permission Model

```dot
digraph perms {
  rankdir=LR;
  "Source systems" [shape=box, label="Source A, Source B\nREAD-ONLY\nalways_allow on reads"];
  "Agent" [shape=ellipse];
  "Target system" [shape=box, label="Target\nREAD-WRITE\nalways_ask on writes"];
  "Human" [shape=box, label="Approval queue\n(Slack/Teams)"];
  "Source systems" -> "Agent" [label="read"];
  "Agent" -> "Human" [label="propose write"];
  "Human" -> "Target system" [label="approved"];
}
```

Default: all MCP toolsets use `always_ask`. For high-trust read-only sources, override to `always_allow`:

```json
{
  "type": "mcp_toolset",
  "mcp_server_name": "[read_only_system]",
  "default_config": {
    "permission_policy": {"type": "always_allow"}
  }
}
```

## Safety Defaults

- `always_ask` on ALL tool calls by default — operator pattern is highest-risk
- `web_search`, `web_fetch`: **disabled** — operator works with connected systems only
- `networking`: `limited` to system hosts only
- One vault credential per connected system — never shared
- Financial amounts never auto-corrected
- Partial writes prevented: if source unavailable, abort or queue entire batch
- All actions logged with system, timestamp, result
- Smoke test is read-only verification (no writes)

## Common Instantiations

| Use case | Systems | Logic | Write actions |
|---|---|---|---|
| PO reconciliation | SAP + invoicing system | Match POs by vendor+amount | Flag discrepancies, create tickets |
| Ticket sync | Jira + Linear | Mirror ticket status bidirectionally | Create/update tickets |
| Revenue reconciliation | Stripe + QuickBooks | Match payments to invoices | Flag mismatches |
| Procurement automation | Supplier portal + ERP | Extract delivery status, cross-ref | Update ERP status, draft actions |
| Incident enrichment | PagerDuty + Datadog + Slack | Gather metrics, enrich alert | Post brief to Slack |
| Workflow bridge | Slack + GitHub + Linear | Route conversations to tickets to PRs | Create issues, assign, label |

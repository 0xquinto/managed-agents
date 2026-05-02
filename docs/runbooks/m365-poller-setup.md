# Microsoft 365 Tenant Setup — Insignia Ingestion v3 Poller

**Audience.** Whoever stands up a fresh Insignia tenant for the v3 ingestion-via-email POC.
**Prerequisites.** Azure AD admin access on the target tenant. The OneDrive
account, Teams team, and inbox used for the demo are also the ones the system
uses going forward — there's no sandbox/prod split (spec § 9, demo plan).

> Treat every step here as a checklist. The poller will refuse to start if any
> required env var or scope is missing — see [§ 6 Smoke checks](#6-smoke-checks)
> for the verifying poll cycle.

---

## 1. Azure AD app registration

In Azure Portal → Azure Active Directory → App registrations → **New registration**.

| Field | Value |
|---|---|
| Name | `insignia-ingestion-poller` |
| Supported account types | "Accounts in this organizational directory only (single tenant)" |
| Redirect URI | leave blank (app-only client-credentials, no user flow) |

Click **Register**. From the resulting Overview page record:

- **Application (client) ID** → becomes `GRAPH_CLIENT_ID`
- **Directory (tenant) ID** → becomes `GRAPH_TENANT_ID`

### 1.1 Client secret

Certificates & secrets → **New client secret** → 24 month expiry → **Add**.
Copy the secret **value** immediately (Azure only shows it once). This becomes
`GRAPH_CLIENT_SECRET`. Rotation cadence: 18 months (calendared); break-glass:
revoke-and-reissue from the same Certificates & secrets page.

> **Do not** commit the secret to git, store in a `.env`, or paste into any
> chat surface. The poller reads `GRAPH_CLIENT_SECRET` from the deployment
> environment only.

### 1.2 API permissions

API permissions → **Add a permission** → **Microsoft Graph** → **Application
permissions** (NOT Delegated):

| Permission | Why |
|---|---|
| `Mail.ReadWrite` | inbox `delta`, mark-read, sendMail for client follow-ups |
| `Files.ReadWrite.All` | OneDrive `/Contracts/<client>/raw/` writes via createUploadSession |
| `ChannelMessage.Send` | Teams card posts |
| `Channel.Create` | per-contract channel materialization on `new_contract` |
| `ChannelMessage.Read.All` | reading the message reply thread for HITL |
| `Group.ReadWrite.All` | adding the per-contract channel under a Team |

After adding, click **Grant admin consent for &lt;Tenant&gt;**. The status
column should turn green for every row. If not, the consent didn't apply —
re-click; for restricted tenants escalate to a Global Admin.

> The poller hits `/me/...` endpoints under `WATCHED_INBOX`'s mailbox via
> mailbox impersonation routing. With application permissions, `/me` still
> resolves to the watched mailbox because Graph routes `me` to the calling
> identity's principal — for app-only flows, this is the inbox you set in
> § 2.

---

## 2. Watched inbox + OneDrive folder

### 2.1 Inbox

Pick a tenant mailbox the poller will poll, e.g. `contracts@insignia.com`.
This becomes `WATCHED_INBOX`. Senders email **here**; the poller reads via
delta query and never logs in interactively.

### 2.2 OneDrive root layout

In OneDrive → **Files** → **New** → **Folder**, create:

```
/Contracts/
```

Subfolders are auto-materialized by `AttachmentStager` per contract:

```
/Contracts/<client>/raw/<message_id>/<filename>
```

You don't need to pre-create per-contract folders — the createUploadSession
PUT chain creates intermediate parents. But you **do** need `/Contracts/`
itself to exist or the first upload returns 404.

---

## 3. Teams team + channels

### 3.1 Team

Create (or reuse) a Team named `Insignia Ingestion`. Note its **Team ID**
(visible in Teams admin center, also exposed via Graph
`/teams?$filter=displayName eq 'Insignia Ingestion'`). This becomes the
`default_team_id` argument to `Orchestrator` / `Scheduler`.

### 3.2 Triage channel

Inside that Team, create a channel `#contracts-triage`. The poller posts
ambiguous-resolution and platform-failure cards here. Note the **channel ID**
(via `Channels` → ⋯ → **Get link to channel**, or Graph
`/teams/{team-id}/channels`). This becomes the `triage_channel.channel_id`
argument.

### 3.3 Per-contract channels

Created on demand by the poller when a `new_contract` triage decision lands
(spec § 6 / § 9). Naming convention: `<client_name>-<contract_id>`.

---

## 4. Memory store + Anthropic API key

The poller talks to the Anthropic Memory Stores API for the six top-level
keys in [spec § 5.1](../superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md#51-layout-insignia_pipeline_state).

> **Gate 0b (spec § 8.2).** The memory-store HTTP shape is research preview as
> of 2026-05-01. Until it's pinned, `AnthropicMemoryBackend.read_bytes` etc.
> raise `NotImplementedError`. Local development can use
> `LocalFilesystemBackend(root=Path("./poller-state/"))` via
> `_local_dev_orchestrator()`.

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys → new |
| `INSIGNIA_MEMORY_STORE_ID` | the memory store id once provisioned |

The two managed-agent definitions (`insignia_resolver`,
`insignia_ingestion_v3`) come from `lead-0` provisioning. Their IDs go into:

| Variable | Source |
|---|---|
| `INSIGNIA_RESOLVER_AGENT_ID` | output of `ant beta:agents create insignia_resolver ...` |
| `INSIGNIA_INGESTION_V3_AGENT_ID` | output of `ant beta:agents create insignia_ingestion_v3 ...` |

> **Gate 0a (spec § 8.2).** The session-API uses the
> `extended-cache-ttl-2025-04-11` beta header to opt into 1h cache TTL on the
> resolver kickoff. Confirm the API key has that beta entitlement before
> standing up the production poller — until then,
> `StubAnthropicSessionsBackend.run_session` raises NotImplementedError.

---

## 5. Vault (for Graph client secret)

Per spec § 2.4, the Graph `client_secret` lives in a vault — never on disk,
never in env, never agent-visible. With `lead-0`:

```
ant beta:vaults create --name insignia_graph_credentials \
  --kind generic \
  --description "Microsoft Graph app-only client_secret for the v3 ingestion poller"

ant beta:vaults:credentials add \
  --vault insignia_graph_credentials \
  --key client_secret \
  --value "$GRAPH_CLIENT_SECRET"
```

The vault ID feeds the resolver/ingestion agent definitions' `mcp_servers`
section so credential pull happens server-side at session start, never as
plain text in this repo.

---

## 6. Smoke checks

### 6.1 Required env vars

The poller refuses to boot without these (`Settings.from_env` raises):

```
GRAPH_TENANT_ID
GRAPH_CLIENT_ID
GRAPH_CLIENT_SECRET
WATCHED_INBOX
ANTHROPIC_API_KEY
INSIGNIA_RESOLVER_AGENT_ID
INSIGNIA_INGESTION_V3_AGENT_ID
INSIGNIA_MEMORY_STORE_ID
```

### 6.2 First poll cycle

```
python -m poller.scheduler
```

Expected on a fresh tenant with empty inbox:

```json
{
  "decisions_applied": 0,
  "emails_seen": 0,
  ...
  "errors": []
}
```

If `errors` is non-empty: read each error string. Common issues:

| Symptom | Likely fix |
|---|---|
| `mail_feed: Graph delta query failed: 401` | Admin consent didn't apply — re-grant in § 1.2 |
| `mail_feed: ... 403 Forbidden` | Missing `Mail.ReadWrite` — § 1.2 |
| `_registry.json must be a JSON array` | Manual upsert against the memory store left a non-array — re-init |
| `StubAnthropicSessionsBackend ... is gated on spec § 8.2 Gate 0a` | API key doesn't have extended-cache-ttl beta yet — request it |

### 6.3 End-to-end smoke (after agents are provisioned)

Send one email with one PDF attachment to `WATCHED_INBOX`. Within 5 minutes
(or whenever the next scheduled cycle fires), expect:

1. New file at `/Contracts/<client>/raw/<message_id>/<filename>.pdf` in OneDrive.
2. New plain-text card in `#contracts-triage` (if the resolver triages) or in
   the per-contract channel (if continuation/new).
3. `seen_attachments.json` in the memory store grows by one entry.

If any of those three is missing, check `errors` in the cycle summary.

---

## 7. Calendar + ownership

| Item | Cadence | Owner |
|---|---|---|
| Client secret rotation (`GRAPH_CLIENT_SECRET`) | 18 months | Insignia ops |
| API permissions audit | Quarterly | Insignia ops + Anthropic SE |
| Memory store size review (still <1 MB?) | Quarterly | Insignia ops |
| Aging-triage cron sweep (5d / 10d alerts) | Built into Orchestrator | the poller |

All other state lives in the memory store and rotates with the contract
lifecycle.

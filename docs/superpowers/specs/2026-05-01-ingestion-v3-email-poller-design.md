# Insignia Ingestion v3 — Email-Driven Real POC (Design Spec)

**Date:** 2026-05-01
**Status:** Design (not yet implemented)
**Branch:** `feat/ingestion-v3-email-poller-poc`
**Supersedes (in scope):** the ingestion slice of the 2026-04-30 5-agent POC (`runs/2026-04-30T18-40-29Z-poc/`). Does NOT supersede the rest of that design (transversal modeler, bespoke modeler, synthesis); those remain deferred.
**Ancestor agents:** `agents/insignia_ingestion/v2_system_prompt.md`. v3 is a minimal-diff descendant of v2.

## 0. Why this exists

The 2026-04-30 POC proved that a managed agent can do the *cleaning* job — given pre-uploaded files, the v1 ingestion agent produced a structurally valid manifest with non-trivial domain flags (going-concern, encoding corruption, biweekly-snapshot caveat). What it did not prove is that the system can close the *intake loop*: pick up files where Insignia actually receives them, decide which contract they belong to, surface what's missing, and draft the follow-up the business owner currently writes by hand.

The Insignia diagnostic (`docs/contracts/Insignia/diagnostics/insignia_diagnostics.md`) is explicit that this is the largest lead-time sink. The "Review" phase (2–4 days) and the "Interaction" phase (2–3 days) are the tail; the modeling phase the v1 POC scoped against is only one third of the bleed. A "real POC" means closing the email loop end-to-end on at least one new client onboarding.

This spec covers the agent and orchestration design for that. It is intentionally narrow: ingestion + resolver only, no team wiring, no modeling, no synthesis.

## 1. System overview

The system is a poller (cron or Azure Function timer trigger) that watches a Microsoft 365 inbox via Microsoft Graph and invokes two managed-agent definitions per inbound email. The agents are stateless transformation steps; the poller is the control plane and owns all Graph traffic, all HITL surfaces, and all durable state.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Insignia POC v3 — control plane = poller, work units = managed agents  │
└─────────────────────────────────────────────────────────────────────────┘

  Microsoft 365 (Graph)                Poller (cron / Azure Function)
  ┌────────────────────┐               ┌──────────────────────────────┐
  │ Outlook inbox      │ ◀──poll────── │ 1. Fetch new mail            │
  │ contracts@…        │               │ 2. Stage attachments         │
  │                    │ ──upload────▶ │    → OneDrive/Contracts/...  │
  │ OneDrive/Contracts │               │ 3. Read registry from        │
  │   /<client>/...    │               │    memory store              │
  │                    │               │ 4. Build kickoff             │
  │ Teams channels     │ ◀──post────── │ 5. Create resolver session   │
  │   /Contracts/<X>   │               │ 6. Switch on resolver out:   │
  │ #contracts-triage  │               │     - triage  → post card    │
  └────────────────────┘               │     - resolved → ingestion   │
                                       │ 7. Create ingestion session  │
   ┌────────────────────┐              │ 8. Read manifest             │
   │ Memory store       │ ◀──r/w────── │ 9. Switch on manifest:       │
   │   /_registry.json  │              │     - email_draft → card     │
   │   /priors/…        │              │     - blocked     → status   │
   │   /tone_examples/… │              │     - ok          → status   │
   └────────────────────┘              └──────────────────────────────┘
                                                  │       │
                                                  ▼       ▼
                                    ┌──────────────┐  ┌──────────────────┐
                                    │ resolver     │  │ ingestion v3     │
                                    │ agent        │  │ agent (≈v2 +     │
                                    │ (Haiku)      │  │  email-draft)    │
                                    │ ──────────── │  │ ──────────────── │
                                    │ in: registry │  │ in: contract_id, │
                                    │   + email    │  │     attachments  │
                                    │ out: triage  │  │ out: manifest +  │
                                    │   OR resolved│  │   envelope       │
                                    └──────────────┘  └──────────────────┘
```

**Two agent definitions, two eval slices, three independent A/Bs:** v1↔v2 (existing), v2↔v3 (ingestion axis only), and a standalone resolver characterization slice. The v2 prompt is preserved verbatim where possible to keep these contrasts clean.

**State boundary discipline.** No env-filesystem state. Per-session ephemeral state lives at `/tmp/<contract_id>/` and `/mnt/session/`. Cross-session durable state lives in one memory store (Section 5). The "stateless cattle" invariant from `CLAUDE.md` is observed.

**HITL surfaces.** Two: a `#contracts-triage` Teams channel for ambiguous-resolution decisions, and a per-contract Teams channel for status updates and client-email approvals. Both posted out-of-band by the poller; human responses fire fresh sessions.

**EmailGate annotation.** The "Fetch new mail" step in the diagram is the entry point of a five-stage filter pipeline (Section 2) that decides whether to spawn an agent session at all. No-attachment emails, cosmetic-only attachments, byte-identical re-sends, and rate-limit trips are all rejected before any session cost is paid.

## 2. Poller architecture

The poller is the system's load-bearing component. This section is architectural per Q9 of the brainstorm; field-level Graph mechanics (subscription renewal, retry budgets, idempotency keys) are deferred to a separate poller spec.

### 2.1 Components

```
┌──────────────────────────────────────────────────────────────────────┐
│ Poller                                                                │
│                                                                       │
│  ┌────────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │ Scheduler  │──▶│ MailFeed │──▶│  EmailGate   │──▶│ ResolverStep │ │
│  │ (cron)     │   │ (Graph)  │   │ (5-stage     │   │              │ │
│  │            │   │          │   │  filter)     │   │              │ │
│  └────────────┘   └──────────┘   └──────────────┘   └──────┬───────┘ │
│                                                            │         │
│                                                            ▼         │
│  ┌─────────────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │ TeamsCardPoster     │◀──│ ManifestStep │◀──│ IngestionStep    │  │
│  │ (Graph)             │   │ (read JSON)  │   │ (sessions.create)│  │
│  └─────────────────────┘   └──────────────┘   └────────┬─────────┘  │
│                                                        │             │
│  ┌─────────────────────┐   ┌──────────────┐            │             │
│  │ AttachmentStager    │◀──┤ MemoryClient │ ◀──────────┘             │
│  │ (Graph download +   │   │ (registry +  │                          │
│  │  OneDrive upload)   │   │  priors r/w) │                          │
│  └─────────────────────┘   └──────────────┘                          │
└──────────────────────────────────────────────────────────────────────┘
```

| Component | Responsibility |
|---|---|
| **Scheduler** | Runs the poller on an interval. Cron / Azure Function timer / GitHub Action schedule. Default N = 5 min. |
| **MailFeed** | Reads new mail from the watched inbox via Graph `/me/mailFolders/Inbox/messages?$filter=receivedDateTime gt <last_seen>`. Maintains `mail_cursor` in the memory store. |
| **EmailGate** | Five-stage filter that decides whether to spawn (§ 2.2). Output: `(spawn, reason, ResolverKickoff)`. |
| **ResolverStep** | Creates a managed-agent session against `insignia_resolver`, kickoff = `ResolverKickoff`. Reads the resolver's envelope. |
| **AttachmentStager** | Downloads email attachments via Graph, uploads to `OneDrive/Contracts/<client>/raw/<message_id>/`. Re-uploads as session resources for the ingestion session. Updates `seen_attachments`. |
| **IngestionStep** | Creates a managed-agent session against `insignia_ingestion_v3`, kickoff = `IngestionKickoff`. |
| **ManifestStep** | Reads `/mnt/session/out/<contract_id>/manifest.json` from the captured session output. Switches on `triage_request` / `client_email_draft` / `status`. |
| **TeamsCardPoster** | Posts cards to `#contracts-triage` (resolver triage) or per-contract channel (status, `client_email_draft` approval). Card payload includes `manifest_path` and a callback ID for HITL resume. |
| **MemoryClient** | Read/write to the memory store via the Memory API. Keys per § 5. |

### 2.2 EmailGate — the five-stage filter

Runs in order; any rejection short-circuits the rest.

```
Stage 1: HasAttachments
  if message.attachments == [] → reject("no-op email")

Stage 2: StripCosmetic
  drop attachments where (isInline) or (size < 5KB AND content-type in {image/png, image/jpeg})
  if remaining == [] → reject("cosmetic-only")

Stage 3: ContentHashDedup
  for each remaining attachment: compute sha256
  lookup in memory_store.seen_attachments
  if all hashes seen AND all map to same contract → reject("duplicate-bundle"),
    post one-line note to contract Teams channel
  else → continue (carry hash list forward)

Stage 4: ThreadRateLimit
  if conversationId saw >0 spawns in last 60s → defer (re-queue, do not reject)
  if sender saw >6 spawns in last hour → reject("rate-limit-tripped"),
    post warning to #contracts-triage

Stage 5: BuildKickoff → ResolverStep
  ResolverKickoff includes the email metadata, attachment hashes, the full
  registry inlined (cache_control: ephemeral), and the seen_attachments slice
  for the top-N candidate contracts.
```

Stages 1–4 are pure poller logic, zero managed-agent cost. Semantic supersession (byte-different but same content) is **not** caught here — that judgment belongs in the resolver (§ 3).

### 2.3 HITL resume routing

When the poller posts a card, the card carries a callback ID. Two ways to capture the human response:

- **Option A (preferred for v2)** — Adaptive Card with action buttons that POST to a tiny webhook on the poller side. Latency in seconds.
- **Option B (v1 fallback)** — poller polls the Teams channel for replies on the card. Latency = poll interval. Cheaper to build.

**v1 ships Option B.** Same scheduler, additional polling job for HITL replies.

### 2.4 Auth model

Microsoft Graph **app-only** application registration in Insignia's Azure AD tenant.

| Permission | Why |
|---|---|
| `Mail.ReadWrite` | Inbox read + sendMail for client follow-ups |
| `Files.ReadWrite.All` | OneDrive contract folders |
| `ChannelMessage.Send`, `Channel.Create` | Teams cards + per-contract channel creation |
| `Group.ReadWrite.All` | Teams team membership for new channels |

Client credentials flow with client_id + secret (or cert). Secret stored in the `insignia_graph_credentials` vault. Token cache lives in the memory store under `graph_token` with expiry; refreshed by `MailFeed` when stale. Never on disk, never in env, never visible to the agents.

### 2.5 Out of scope (poller-side)

- Graph subscription/webhook mechanics (we chose polling).
- Production deployment topology, scaling, retry budgets, idempotency-key design.
- Token rotation cadence and break-glass auth.
- Adaptive Card schema for Teams cards.

## 3. Resolver agent (`insignia_resolver`)

### 3.1 Identity

A small, specialized agent whose only job is to decide one of three things about an inbound email: *new contract*, *continuation*, or *triage*. It also makes the literal-vs-meaningful supersession call on attachments. It does not extract, normalize, or post anywhere.

### 3.2 Model

`claude-haiku-4-5` (or Haiku-class equivalent). Short-context classification + small reasoning trace. Sonnet is overkill and the per-email latency budget matters. Bumping to Sonnet is a v2 option if eval shows triage precision drop.

### 3.3 Tools

`read` only. No `bash`, no `write`, no skills. The whole job is "read kickoff JSON, emit envelope JSON."

### 3.4 Kickoff schema (`ResolverKickoff`)

```json
{
  "email": {
    "from": "ana@tafi.com.ar",
    "to": ["contracts@insignia.com"],
    "cc": [],
    "subject": "Re: Análisis financiero Q1",
    "conversationId": "AAQk…",
    "messageId": "AAMk…",
    "body_text": "Hola, te envío…",
    "received_at": "2026-05-01T14:22:11Z"
  },
  "attachments": [
    { "message_attachment_id": "att_…", "filename": "EF Tafi 2025 v3.pdf",
      "sha256": "9f…", "size": 1543210, "content_type": "application/pdf" }
  ],
  "registry": [
    { "contract_id": "INS-2026-007", "client_name": "Financiera Tafi",
      "sender_addresses": ["ana@tafi.com.ar","jorge@tafi.com.ar"],
      "subject_tag": null, "onedrive_path": "/Contracts/Tafi/",
      "teams_channel_id": "19:abc…@thread.tacv2", "status": "open",
      "opened_at": "2026-04-12T09:00:00Z" }
  ],
  "attachment_hashes_seen_for_candidate": {
    "INS-2026-007": ["a1…","9f…"]
  }
}
```

The poller marks the `registry` field with `cache_control: {type: "ephemeral"}` at the prompt-payload level. The resolver doesn't see the cache marker; it just reads the JSON.

### 3.5 Output envelope (`ResolverEnvelope`)

```json
{
  "decision": "new_contract" | "continuation" | "triage",
  "contract_id": "INS-2026-007" | null,
  "confidence": 0.0,
  "rationale_short": "exact sender match + subject thread continuity",
  "superseded_by_prior": false,
  "superseded_reason": null,
  "triage_payload": null,
  "new_contract_proposal": null
}
```

When `decision == "triage"`:

```json
"triage_payload": {
  "question": "...",
  "candidates": [{ "contract_id": "...", "score": 0.0, "reason": "..." }],
  "inferred_new_contract": { "client_name_guess": "...", "sender_domain": "..." }
}
```

When `decision == "new_contract"`:

```json
"new_contract_proposal": {
  "client_name": "Financiera Tafi",
  "sender_domain": "tafi.com.ar",
  "suggested_contract_id": "INS-2026-009",
  "suggested_onedrive_path": "/Contracts/Tafi-2026-Q2/",
  "suggested_teams_channel_name": "tafi-2026-q2"
}
```

When `decision == "continuation"` and `superseded_by_prior == true`: the poller skips ingestion and posts a "duplicate update — ignored" note to the contract's Teams channel.

### 3.6 System prompt outline

Drafted in full when the implementation plan lands. Structure:

1. Identity: "You resolve email-to-contract identity. You do not extract, normalize, or write."
2. Decision rules:
   - **Continuation**: exact sender-address match against a registry row's `sender_addresses` AND (`conversationId` matches a prior message in `priors/<contract_id>.json` OR registered subject-tag match) → confidence ≥ 0.9.
   - **New contract**: zero registry hits, sender domain not in any `sender_addresses` array → confidence ≥ 0.8. Propose `contract_id` per the convention `INS-<year>-<NNN>` (next ordinal).
   - **Triage**: anything else (multiple candidates, partial match, consultant forwarding, etc.).
3. **Supersession rule**: for each post-EmailGate attachment, if `sha256 ∈ attachment_hashes_seen_for_candidate[resolved_contract_id]` then it's a literal duplicate. If ALL post-EmailGate attachments are stale → `superseded_by_prior: true`.
4. **Output discipline**: emit only the envelope JSON, no fences, no prose. Same BLOCK_COMPLETED rule v2 enforces.

### 3.7 Out of scope

- Field-level prompt text.
- A `known_consultant_domains` registry key (heuristic for v2 — v1 inspects the email body).

## 4. Ingestion agent (`insignia_ingestion_v3`)

### 4.1 Identity

Direct descendant of v2. Same "you are a cleaner, not a modeler" identity, same v2 efficiency rules (`/tmp/<contract_id>/` state persistence, combined bash calls, no redundant `cp -r`), same envelope shape, same output paths. Surgical diff.

### 4.2 Diff vs. v2 — added

1. Kickoff carries a resolved `contract_id` and `email_context` blob (§ 4.4).
2. New manifest key: `client_email_draft` (§ 4.5). Populated only when `missing_fields` is non-empty AND ingestion otherwise succeeded. Spanish, threads on the original `messageId`.
3. Prompt section "When you cannot complete because of missing data," located right after "Quality check." Six lines (§ 4.7).
4. **No triage logic.** Triage is upstream (resolver). Prompt explicitly says "your kickoff always carries a resolved `contract_id`; if it doesn't, that's a poller bug, not your problem."
5. Memory store mounted at `/mnt/memory/`. Read-only access in v1 to `priors/<contract_id>.json` and `tone_examples/`. Read on demand only when drafting a `client_email_draft`.

### 4.3 Diff vs. v2 — removed

- The contract_id-derivation paragraph from v2's "Inputs you receive" section. Resolved upstream now.
- Nothing else. v2's PDF/CSV/XLSX/DOCX extraction logic, the `pypdf → pdfplumber → ocr` fallback, the `/mnt/session/uploads/` mount discipline, the BLOCK_COMPLETED discipline — all preserved verbatim. This is the cleanest possible diff for the v2↔v3 paired-McNemar A/B.

### 4.4 Kickoff schema (`IngestionKickoff`)

```json
{
  "contract_id": "INS-2026-007",
  "client_name": "Financiera Tafi",
  "input_files": [
    "input/INS-2026-007/EF Tafi 2025 v3.pdf",
    "input/INS-2026-007/Cartera Total TAFI.csv"
  ],
  "email_context": {
    "from": "ana@tafi.com.ar",
    "to": ["contracts@insignia.com"],
    "cc": [],
    "subject": "Re: Análisis financiero Q1",
    "conversationId": "AAQk…",
    "messageId": "AAMk…",
    "body_text_excerpt": "Hola, te envío...",
    "received_at": "2026-05-01T14:22:11Z",
    "language": "es"
  },
  "memory_paths": {
    "priors": "/mnt/memory/priors/INS-2026-007.json",
    "tone_examples_dir": "/mnt/memory/tone_examples/"
  }
}
```

`email_context.body_text_excerpt` is the first ~500 chars — enough for tone alignment when drafting a reply, not the full body.

### 4.5 Manifest schema additions

v2's manifest gets two new top-level optional keys:

```json
{
  "...": "all v2 keys unchanged",
  "client_email_draft": null | {
    "to": ["ana@tafi.com.ar"],
    "cc": [],
    "subject": "Re: Análisis financiero Q1",
    "in_reply_to_message_id": "AAMk…",
    "language": "es",
    "body": "Hola Ana,\n\nGracias por enviar la información. ...",
    "missing_fields_referenced": ["cashflow_2024", "balance_sheet_q4_2024"],
    "tone_examples_consulted": ["tone_examples/2026-q1-followup.md"]
  },
  "triage_request": null
}
```

`triage_request` stays `null` in ingestion's output. It's present because the manifest schema is shared across the resolver and ingestion paths and the poller switches on the union; ingestion never populates it.

### 4.6 Envelope (unchanged from v2)

```json
{
  "status": "ok" | "blocked" | "failed",
  "normalized_dir": "/mnt/session/out/<contract_id>/normalized/",
  "manifest_path":  "/mnt/session/out/<contract_id>/manifest.json",
  "missing_fields": []
}
```

When `client_email_draft` is populated, `status: "blocked"` and `missing_fields` is non-empty. Poller switches on the manifest, not the envelope.

### 4.7 System prompt diff outline

```
[REPLACE] "Inputs you receive"
   v2: contract_id, input_files at /mnt/session/uploads/input/<contract_id>/
   v3: contract_id (resolved), client_name, input_files, email_context blob,
       memory_paths blob

[ADD AFTER] "Quality check"
   "When `missing_fields` is non-empty, populate `manifest.client_email_draft`
    with a Spanish-language follow-up. Read 1–3 examples from
    `memory_paths.tone_examples_dir` first to match Insignia's voice.
    Reference the specific missing items by name. Reply via the email thread:
    set `in_reply_to_message_id` from `email_context.messageId`. The orchestrator,
    not you, will send the email after human approval. Do NOT use any tool to
    send mail; you have no such tool."

[KEEP VERBATIM] Everything else from v2: extraction logic, fallback chain,
   /tmp/<contract_id>/ persistence, BLOCK_COMPLETED discipline, identity rules.
```

### 4.8 Tools

Same as v2: `bash`, `read`, `write`, `edit` + `pdf`, `xlsx`, `docx` skills. No `mcp_*` tools (Graph traffic stays in the poller). No new custom tools.

## 5. State model

One memory store, six top-level keys, strict access discipline.

### 5.1 Layout (`insignia_pipeline_state`)

```
/mnt/memory/
├── _registry.json          # contract rows; hot, mutates, inlined into resolver kickoff
├── mail_cursor.json        # { last_seen_received_at, last_seen_message_id }
├── seen_attachments.json   # append-only: [{sha256, contract_id, message_id, first_seen_at}]
├── graph_token.json        # { access_token, expires_at } — refreshed by poller
├── priors/
│   └── <contract_id>.json  # per-contract accumulator: prior manifests, conversation history
└── tone_examples/
    └── *.md                # approved client-email drafts; corpus accretes over time
```

### 5.2 Access matrix

| Key | Poller r | Poller w | Resolver r | Resolver w | Ingestion r | Ingestion w |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `_registry.json` | ✓ | ✓ | ✓ (kickoff, cached) | ✗ | ✗ | ✗ |
| `mail_cursor.json` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `seen_attachments.json` | ✓ | ✓ | ✓ (kickoff slice) | ✗ | ✗ | ✗ |
| `graph_token.json` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `priors/<contract_id>.json` | ✓ | ✓ | ✓ (`read` tool) | ✗ | ✓ (`read` tool) | ✗ |
| `tone_examples/*.md` | ✓ | ✓ | ✗ | ✗ | ✓ (`read` tool) | ✗ |

Three encoded rules:

1. **Agents never write to the memory store.** All durable state is the poller's responsibility. Agents emit JSON envelopes; the poller decides which keys to update.
2. **The registry reaches the resolver via cached kickoff, not via tool call.** Resolver's only `read` tool use is for `priors/` lookups when the kickoff suggests a per-contract continuation needs deeper context.
3. **Token rotation is poller-only.** No agent ever touches `graph_token.json`.

### 5.3 Per-session ephemeral state

Unchanged from v2. `/tmp/<contract_id>/` for cross-bash-call PDF/CSV caching. `/mnt/session/uploads/` for poller-pre-staged attachments. `/mnt/session/out/<contract_id>/` for normalized outputs and the manifest. Container is recycled; nothing in env filesystem persists.

### 5.4 Sizing

| Key | Estimate | Note |
|---|---|---|
| `_registry.json` | ~100 KB at 200 contracts/yr | Inline-cacheable. |
| `seen_attachments.json` | ~400 KB at ~2k attachments/yr | Only the resolved-candidate slice goes into kickoff. |
| `priors/<contract_id>.json` | ≤50 KB capped per contract | Read on demand. |
| `tone_examples/` | ~90 KB at ~30 examples | Read on demand. |

Total working set well under 1 MB at year-2 volumes.

### 5.5 Cache hit math

The resolver's kickoff prefix is: stable system prompt + stable tool definitions + first-user-turn `cache_control` block containing the registry (mostly stable). Cache hit applies to that prefix. Per-email cache miss is just the email-specific tail (subject, body excerpt, attachment metadata). At ~5–20 emails/day with the 1-hour TTL beta, the registry stays warm essentially all day; cold-start cost is paid at most a few times daily.

Ingestion's kickoff is per-contract (`contract_id`-keyed); cache hits there only fire on consecutive sessions for the same contract within TTL.

## 6. Failure modes and error handling

Every failure tagged with the eval slice's three-column taxonomy (`process` / `outcome` / `environment`).

### 6.1 Microsoft Graph (environment)

| Failure | Detected by | Behavior |
|---|---|---|
| Inbox poll 5xx | MailFeed | Exponential backoff (1s,2s,4s,8s,max 60s), 5 retries. After 5 → log, alert, skip cycle. `mail_cursor` not advanced. |
| Token expired / 401 | Any Graph call | Refresh once. If refresh fails → halt, post critical alert to `#contracts-triage`. |
| Throttling (429 + Retry-After) | Any Graph call | Honor Retry-After. If wait > next tick, defer affected message. |
| Attachment download corruption | AttachmentStager | Re-download once. Still bad → dead-letter index, warning to `#contracts-triage`. Email NOT past `mail_cursor` until cleared. |
| OneDrive upload conflict | AttachmentStager | Suffix filename with `_<message_id_short>`, retry. |
| Teams card POST failure | TeamsCardPoster | Retry 3x. Still failing → log card payload to dead-letter, surface as `pending_card`. Manifest is already written. |

### 6.2 Resolver (process)

| Failure | Detected by | Behavior |
|---|---|---|
| Resolver session timeout (no envelope, tool budget exhausted) | ResolverStep | Treat as `triage` with `rationale_short: "resolver timeout"`. Post triage card. Process-column failure. |
| Malformed envelope | ResolverStep | Same as timeout — convert to triage with `rationale_short: "resolver malformed output"`. |
| `decision: "new_contract"` but `client_name` collides with existing registry row | ResolverStep | Demote to triage. The poller refuses to silently shadow a contract id. |
| `superseded_by_prior: true` but `seen_attachments` slice was stale | ResolverStep | Re-read `seen_attachments` immediately before skipping. Defer only when the re-read confirms. |

### 6.3 Ingestion (process / outcome)

Mostly inherited from v2. New v3 modes:

| Failure | Detected by | Behavior |
|---|---|---|
| `client_email_draft.missing_fields_referenced` not subset of manifest's `missing_fields` | Poller schema validator | Reject draft. `degraded` status card to contract channel. Process-column. |
| `client_email_draft` not Spanish when `email_context.language: "es"` | Poller (lang-detect on body) | Reject draft. Process-column. |
| `body` < 50 chars OR contains "TBD" / "TODO" / "[…]" | Poller content lint | Reject. Process-column. |
| `client_email_draft` malformed JSON inside the manifest | Poller | Treat as `status: "failed"` even if envelope says `"blocked"`. Process-column. |

### 6.4 HITL (process / environment)

| Failure | Detected by | Behavior |
|---|---|---|
| Approved draft fails sendMail | TeamsCardPoster post-action callback | Retry 3x. Still failing → failure card with bounce reason. Manifest's `email_sent_at` stays null. Email lands in a dead-letter retryable from Teams. |
| Human edits draft to something the agent never wrote | TeamsCardPoster | Send what the human typed. Poller delivers; it doesn't police edits. |
| Triage card aged 5+ business days | Aging cron | Re-post with "aging" tag. After 10 business days → "stale triage" alert. No automated resolution. |
| Client reply lands on different `conversationId` (broken threading) | MailFeed → EmailGate → Resolver | Resolver sees it, no thread match, strong sender-domain match against open contract → triage. Registry learns the new sender on resolution. |

### 6.5 Memory store (environment)

| Failure | Detected by | Behavior |
|---|---|---|
| Memory store unavailable | Any MemoryClient call | Retry 3x with backoff. Still down → halt cycle, critical alert. |
| `_registry.json` corrupted | MemoryClient on read | Halt. Critical alert. Poller does NOT silently overwrite. |
| `seen_attachments.json` corrupted | MemoryClient on read | Degrade gracefully — treat all attachments as new, post warning. False-positive supersession is more expensive than duplicate ingestion. |

### 6.6 Configuration / drift (process)

| Failure | Detected by | Behavior |
|---|---|---|
| Resolver/ingestion shared field-name drift | Poller schema validator | Reject at poll time. Both agents share a versioned schema; the poller is the only enforcement point. |
| Memory-store schema version mismatch | MemoryClient reads `schema_version` field | Halt; require manual migration. No auto-migration in v1. |

### 6.7 Cross-cutting principles

1. **Failures escalate to the most relevant human surface.** Triage failures → `#contracts-triage`. Per-contract failures → that contract's Teams channel. Critical platform failures → `#contracts-triage` for v1.
2. **The poller is the only retry boundary.** Agents do not retry their own work; the poller decides between same-session retry, escalation to triage, and dead-letter.

### 6.8 Out of scope

- Specific alert routing (PagerDuty, Slack, email-to-ops).
- Cost-explosion guardrails beyond EmailGate's per-thread / per-sender caps. A global daily session cap is required; the specific value is set by the implementation plan.
- Adversarial / abuse threat modeling.

## 7. Eval strategy

Three independent slices, three independent A/Bs, each sized to its decision per the playbook §6 MDE table.

### 7.1 Slices

| Slice | Cases | Tier | Decision |
|---|---|---|---|
| `evals/ingestion/tafi_2025` (existing, frozen) | tafi_2025 happy-path | Tier-1 | v1↔v2 paired McNemar (already pre-registered in v2 changelog). |
| `evals/ingestion/tafi_2025_v3` (new) | `tafi_2025_v3_complete`, `tafi_2025_v3_missing_cashflow` | Tier-1 + Tier-2 (parser-validation on `client_email_draft`) | v2↔v3 paired McNemar on the ingestion axis. |
| `evals/resolver/<cases>` (new) | `clean_continuation`, `clean_new_contract`, `ambiguous_consultant_forward`, `superseded_attachment` | Tier-1 + Tier-2 | Resolver characterization (Wilson 95%) and prompt-version regression detection. |

The v2↔v3 contrast runs on `tafi_2025_v3` with a "v2 prime" — minimal-change adapter to v2 that accepts the new kickoff schema, NOT v2 plus client-email logic. This isolates the client-email-drafting capability as the single variable.

### 7.2 Construct-validity carry-over

Every new slice ships with `spec.md` (Bean's-8) and `factsheet.md`. Specifically:

- **Bean §1 Phenomenon.** Resolver: "registry-resolution correctness." Ingestion v3: v2's phenomenon plus "produces a non-null `client_email_draft` with an in-language, in-tone, in-thread Spanish reply when missing-fields is non-empty."
- **Bean §3 Sampling.** Resolver gets four cases at v1 ship; held-out 5th is the first real client onboarding after v1.
- **Bean §5 Contamination.** The tone-examples corpus is held-out from any case the agent is evaluated on. Approved drafts going back into the corpus lock the case they came from to its current `expected.json` version.
- **Bean §6 N + power.** Resolver decision A/B: n=10 paired McNemar per case (40 paired trials total). Ingestion v3 inherits the existing tafi sizing.
- **Bean §7 Error analysis.** ≥20 traces before measurement claims. Until then, exploratory.
- **Bean §8 Phenomenon→task→metric chain.** Resolver: pass-rate per (case × prompt_version) cell, `process` column. Ingestion v3: extends existing tafi assertion shape with two new `process`-tagged assertions on `client_email_draft` (existence-when-required, non-existence-when-not-required) and one `outcome`-tagged assertion on language detection.

### 7.3 `expected.json` deltas

`evals/ingestion/tafi_2025_v3/expected.json` adds:

```json
"client_email_draft": {
  "must_be_null_when": "missing_fields == []",
  "must_be_present_when": "missing_fields != []",
  "field_assertions": [
    { "field": "client_email_draft.language", "type": "exact", "value": "es", "column": "process" },
    { "field": "client_email_draft.in_reply_to_message_id", "type": "exact", "value": "<from kickoff>", "column": "process" },
    { "field": "client_email_draft.body", "type": "min_length", "value": 50, "column": "process" },
    { "field": "client_email_draft.body", "type": "must_not_contain", "values": ["TBD", "TODO", "[…]"], "column": "process" },
    { "field": "client_email_draft.missing_fields_referenced", "type": "is_subset_of", "of_field": "missing_fields", "column": "process" }
  ]
}
```

The `is_subset_of` assertion is new — scorer needs a rule that one array is a subset of another (~30 lines).

Resolver `expected.json` per case (sketch):

```json
{
  "case_id": "resolver/clean_continuation",
  "schema_version": 1,
  "envelope": [
    { "field": "decision", "type": "exact", "value": "continuation", "column": "process" },
    { "field": "contract_id", "type": "exact", "value": "INS-2026-007", "column": "process" },
    { "field": "confidence", "type": "range", "min": 0.9, "max": 1.0, "column": "process" },
    { "field": "superseded_by_prior", "type": "exact", "value": false, "column": "process" }
  ],
  "envelope_format": [
    { "type": "no_markdown_fences", "column": "process" },
    { "type": "no_surrounding_prose", "column": "process" }
  ]
}
```

### 7.4 Runner / scorer changes

- `evals/runner.py` learns to spin a resolver session (different agent ID, different kickoff shape, different output capture). One binary, multiple slice configs.
- `evals/score.py` learns the `is_subset_of` and `must_not_contain` assertion types. Adds a deterministic language-detect helper (e.g., `langdetect` or `lingua`, pinned).
- `resources.json` extends with a `kickoff_template` field referencing a Jinja2 template the runner fills in per case. Resolver kickoffs are constructed; ingestion v3 kickoffs are constructed too. Captured POC files become a sanity-check fallback, not the canonical input.

### 7.5 Out of scope

- Specific assertion values for resolver cases (filled in when authoring cases).
- The `tone_examples/` seed corpus content.
- Behavior-auditor probes for the new agents (post-deploy, dev-tooling agent's job).
- Cost-of-eval guardrails (resolver eval is cheap; ingestion v3 inherits v2 cost).

## 8. Provisioning, scope, and rollout

### 8.1 What ships in v1 of the design

- 2 managed-agent definitions: `insignia_resolver`, `insignia_ingestion_v3`.
- 1 environment: same `insignia_pipeline_env` family as v1's POC. Reuse vs. new image decided per § 8.2.
- 1 memory store: `insignia_pipeline_state`, layout per § 5.
- 1 vault: `insignia_graph_credentials`. Distinct from the existing `insignia_pipeline` vault — independent rotation policy.
- 2 new eval slices: `evals/ingestion/tafi_2025_v3`, `evals/resolver/<4 cases>`.
- 1 new component (out-of-tree): the poller. Architecturally specced here; full spec deferred to a separate doc.

### 8.2 Provisioning order

```
files (eval fixtures + tone seed examples)
  → vaults (Graph creds)
  → skills (none new — pdf, xlsx, docx are pre-built Anthropic)
  → memory (insignia_pipeline_state)
  → agents (resolver + ingestion_v3 in parallel — independent definitions)
  → environments (reuse env_01WaJyfTQu9YDfQC5vXiXWj5 if package set unchanged; new image otherwise)
  → sessions (poller's job at runtime, not Phase 3)
```

Phase 3 finishes when the agent + memory store + vault exist; Phase 4 (smoke) runs synthetic `ResolverKickoff` and `IngestionKickoff` against the deployed agents to verify the schema contracts.

### 8.3 Scope guardrails — explicitly NOT in v1

- **No coordinator / multi-agent team wiring.** v1 is two single-agent definitions invoked sequentially by the poller. The `callable_agents` research-preview gate that bit the v1 POC is a non-issue here because orchestration lives outside the platform.
- **No transversal / bespoke / synthesis agents.** v1 stops at "ingestion produces a manifest the human can act on, the email loop is closed."
- **No webhooks.** Polling only. Webhook latency upgrade is a v2 enhancement.
- **No production deployment of the poller.** The POC poller runs as a local cron OR a single Azure Function instance, not a hardened production service. Auth/secret rotation, observability, retries, deployment topology are explicit follow-ups.
- **No automated tone-corpus growth.** v1 ships with 1–2 hand-authored Spanish examples. Approved drafts going back into the corpus is a v2 feature with its own contamination-decay guarantee.
- **No outcome-based agent validation** (`user.define_outcome` + rubric). The eval slices are the validation surface; outcome iteration is overkill for a stateless transformation.

### 8.4 Rollout — three gates

**Gate 1 — Synthetic smoke (orchestrator Phase 4).** Both agents deployed against constructed kickoffs from the eval slices. Pass rule: 1/1 trial per case in each slice produces a parseable envelope that meets all `process`-column assertions. Smoke-grade only; confirms agents and contract, not measurement properties.

**Gate 2 — Shadow-run on captured email.** Take 5–10 emails from Insignia's actual contracts inbox (with business-owner consent, after a manual privacy pass). Run them through the poller in non-acting mode: full pipeline EXCEPT no email send and no Teams post. All decisions logged for human review. Pass rule: human reviewer agrees with ≥4/5 resolver decisions, ≥4/5 ingestion drafts are "would have approved with at most minor edits." Failure → back to prompts.

**Gate 3 — One real client onboarding, end-to-end.** With business-owner sign-off, point the poller at live `contracts@insignia.com` for one new contract. Human in the approval loop on every Teams card. Pass rule: contract closes within the diagnostic's stretch goal of ~3 days (vs. current 5–12). The first real onboarding's capture becomes the seed of `evals/resolver/<client>_<period>` and `evals/ingestion/<client>_<period>` (held-out validation case).

### 8.5 Versioning policy

- `agents/insignia_resolver/v1_system_prompt.md` and `agents/insignia_ingestion/v3_system_prompt.md`. v2 stays committed for the paired-McNemar baseline.
- `CHANGELOG.md` per agent. v3 ingestion changelog explicitly lists what changed vs. v2 and what's preserved verbatim.
- Schema versions for `manifest.json`, `_registry.json`, `seen_attachments.json` start at 1; bump on any breaking change. Mismatches are a hard halt per § 6.6.

### 8.6 Acceptance criteria for shipping the design (NOT the implementation)

The design is "shipped" when:

- This brainstorm produces this spec at `docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md` covering Sections 1–8.
- The spec passes self-review (no placeholders, no contradictions, no scope ambiguity, no unstated assumptions).
- The user signs off.

Implementation (poller code, prompt drafts, eval slice authoring, smoke runs against deployed agents) is the next session's job, kicked off by the writing-plans skill.

### 8.7 Cost back-of-envelope

At ~10 emails/day × ~5k tokens resolver (Haiku, mostly cached prefix) + ~50k tokens ingestion (Sonnet, with caching), ~$15–25/day in API costs at current pricing. Not a v1 blocker.

### 8.8 Out of scope

- Specific calendar dates / sprint sizing.
- Privacy / data-handling policy for client documents — Gate 2 prerequisite, not designed here.

## 9. Open questions for the implementation plan

These are deliberately deferred from this spec — they affect implementation, not architecture:

- Where exactly does the registry physically live: a single `_registry.json` blob in the memory store, or a SharePoint list with a poller-side mirror? (Spec assumes blob; SharePoint is a v2 candidate.)
- How does the poller construct `attachment_hashes_seen_for_candidate` efficiently as `seen_attachments.json` grows? (Index by `contract_id` at write time vs. linear scan on read; trade-off depends on write/read ratio.)
- What's the exact convention for `INS-<year>-<NNN>` ordinal allocation under concurrent polls? (Likely a single-writer poller for v1; concurrent-safe ID minting is a v2 problem.)
- Should the `tone_examples/` corpus be Spanish-only, or include English examples for clients outside LatAm? (v1 says Spanish-only; v2 reconsiders if client mix changes.)
- Adaptive Card schema for the Teams cards (Section 2.3 deferred this; implementation plan picks a concrete schema).

## 10. Demo plan

### 10.1 Stance: demo IS the production smoke run

A faked demo (scripted poller, pre-staged Teams cards, mocked Graph) is cheaper to build but builds nothing. Insignia's first held-out eval case (§ 8.4 Gate 3) wants to *be* this demo: same poller, same agents, same Microsoft 365 tenant, same code path. Synthetic contracts substitute for unknown real clients; everything else is real.

This means:

- **One Microsoft 365 tenant** (Insignia's, or a dedicated demo tenant in the same trust posture). No sandbox-vs-production split. The Graph app registration, OneDrive folders, Teams channels, and inbox used in the demo are the ones the system will use on the next real onboarding.
- **One poller deployment.** Whatever runs the demo is what runs the next contract. A switch from "demo mode" to "production mode" is a config flag (which inbox to watch, which Teams team to post into), not a code path.
- **Demo failures are real failures.** If the demo cracks, that's a real bug — not a "the demo broke, but production is fine" deflection.

This raises the cost of the demo by ~2–3 weeks of Graph plumbing work that a fake demo would skip. It saves ~2–3 weeks of "now make it real" rebuild work that a fake demo would force later.

### 10.2 Three demonstration contracts

| Contract | Source | Role in the demo |
|---|---|---|
| **Tafi 2025** | Real client data (existing POC capture) | Anchor. The agent's domain flags (going-concern, UTF-8 mojibake, biweekly-snapshot caveat) are unfakeable proof that the agent is doing real work, not pattern-matching. |
| **Synthetic Contract B** | Fake LatAm SME, Spanish-language, P&L + balance sheet provided, **`cashflow_2024` deliberately absent** | Triggers the `client_email_draft` path — the headline moment. Spanish follow-up materializes in Teams; presenter clicks Approve; email goes out via Graph in front of the audience. |
| **Synthetic Contract C** | Fake email from `advisor@<consultant_domain>.com` forwarding files for "Cliente XYZ" | Triggers the resolver-triage path. Card lands in `#contracts-triage` live; presenter resolves it; next session fires automatically. |

**Tafi exposure caveat.** Showing Tafi to anyone besides Insignia themselves needs explicit Tafi consent. If the demo audience is non-Insignia (investors, partners, sales), Tafi must be either redacted or replaced with a fourth synthetic contract designed to surface the same domain flags (negative equity, encoding corruption, snapshot caveat). This decision precedes synthetic-data authoring — the answer changes whether two or three synthetic contracts are needed.

### 10.3 Synthetic-data authoring

Not free. Estimated ~2 days of authoring per contract:

- **Fictional company name + tax ID.** Avoid collision with real registered companies (verify against any public registry the audience might check).
- **Financial statement PDF.** Built off the Tafi statement template but with different line items, periods, and amounts. ~30–40 pages, NIIF/IFRS structure, Spanish. The supersession-test variant (used in resolver eval) is byte-identical to the canonical version; the missing-cashflow-2024 variant is the demo input.
- **Loan portfolio CSV (for Contracts B and C if applicable).** Same 24-column schema as Tafi's `Cartera Total TAFI.csv`, ~50k–150k rows of fake biweekly snapshot data. Generate procedurally; do not copy Tafi's actual rows with names changed (PII risk plus regulatory weirdness).
- **Email bodies + threading.** Spanish, business-casual, signature blocks. Realistic enough to test the resolver's `body_text` heuristics; not so polished that the audience suspects AI authorship of the demo material itself.

Authoring lives under `evals/ingestion/<synthetic_id>/` and `evals/resolver/<synthetic_id>/` so the demo data is also eval data. Each synthetic contract gets a Bean's-8 `spec.md` and a `factsheet.md` per § 7. **Synthetic data that doesn't pass the eval framework's construct-validity check doesn't ship.**

### 10.4 Demo arc (≈10 minutes)

The arc is a single take, not a slide deck. Each beat is timed to the system actually running.

1. **Open with the pain (1 min).** Pull up the diagnostic's lead-time chart (`docs/contracts/Insignia/diagnostics/insignia_diagnostics.md` § 3, the 5–12 day table). One sentence: "Today, between client email and modeling-ready data, this is 5–12 days, almost all of it manual. Watch."
2. **Show the inbox (30s).** A real Outlook inbox view of `contracts@<demo_domain>` with three unread emails staged: Tafi update, synthetic Contract B initial, synthetic Contract C ambiguous-forward.
3. **Run one scheduler tick live (90s).** Poller fires. Logs scroll on screen. EmailGate decisions visible (Contract A passes, Contract B passes, Contract C passes — none rejected today; rejection is its own demo if time permits).
4. **Watch Teams light up (90s).** Three channels populate concurrently: Tafi posts "ingestion complete, manifest at <link>"; Contract B posts the `client_email_draft` Approve/Edit/Reject card; `#contracts-triage` posts Contract C's resolver question.
5. **The headline moment (2 min).** Open Contract B's Teams channel. Read the Spanish draft aloud. Click Approve. Show the email landing in the synthetic client's inbox in real time. Total elapsed: from "email arrived" to "follow-up sent" is now under 3 minutes vs. the 2–3 day "Interaction" row of the diagnostic.
6. **Resolve the triage (1 min).** Click into `#contracts-triage`. Read the resolver's question. Pick "new contract — client name X." Show the new OneDrive folder + Teams channel materializing live. Show the registry growing by one row.
7. **Close with the manifest (2 min).** Open Tafi's `manifest.json`. Show the going-concern flag. Show the UTF-8 mojibake count. Show the snapshot caveat. "Four days of human work. Ninety seconds of agent work. Every flag here is something a human would have caught — eventually. The agent caught all of them on the first read."
8. **Honest close (1 min).** "Modeling and synthesis are still manual. This POC closes the intake loop only. The next milestone is automating the transversal modeling — that's a different agent, different design, not part of today's demo."

### 10.5 Failure-mode demos (optional, time-permitting)

Drop in if the demo audience is technical or skeptical:

- **Supersession skip.** Re-send Contract B's same attachments. EmailGate logs `duplicate-bundle`. No session spawned. Contract B's Teams channel gets a one-line "ignored duplicate update" note. Demonstrates the system has *taste*.
- **Resolver malformation.** Pre-stage a resolver session with a deliberately broken kickoff. Show the poller demoting to triage with `rationale_short: "resolver malformed output"`. Demonstrates the system fails safely.
- **Send-mail bounce.** Configure Contract B's recipient address to bounce. After Approve, show the failure card with the bounce reason and the dead-letter retry surface.

These are not core to the arc. Use them only if the audience is asking "what about errors?"

### 10.6 Demo prerequisites

Hard prerequisites before any demo can run, in dependency order:

1. **Tenant and inbox.** Microsoft 365 tenant identified; `contracts@<domain>` inbox provisioned; Graph app registration completed with the § 2.4 permission set; client secret in `insignia_graph_credentials` vault.
2. **Tafi consent decision.** Audience scoped → Tafi inclusion approved or substituted.
3. **Synthetic contracts authored.** B and C (and optionally a Tafi-substitute) shipped under `evals/ingestion/<id>/` and `evals/resolver/<id>/` with passing Bean's-8 worksheets.
4. **Tone seed corpus.** 1–2 hand-authored Spanish follow-up examples in `tone_examples/`. Without these the headline moment produces text that sounds like AI; with them it sounds like Insignia.
5. **Poller deployed.** Cron or Azure Function timer, hitting the demo inbox on a 1–2 minute interval (faster than the 5-min default, for demo-pace reasons).
6. **Dry-run rehearsal.** Run the full arc against the demo data at least 3 times in a row before the live demo. Catch the timing bugs (Teams card-render latency varies by 5–30 seconds).

### 10.7 Out of scope for the demo plan

- Recording / livestream production logistics.
- Investor-deck materials wrapping the demo.
- Localization to English or Portuguese (Spanish-only for v1; the diagnostic is LatAm-anchored).
- A "what if the demo fails" backup plan beyond the dry-run rehearsal — if rehearsal can't get to 3 consecutive clean runs, the demo isn't ready.

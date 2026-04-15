# Anthropic rate research

_Pulled 2026-04-15 — source URLs listed per entry. Managed Agents is in general availability (not beta); rates may move._

## Model rates

| Model | Input $/MTok | Output $/MTok | Source URL | Date |
|-------|--------------|---------------|------------|------|
| claude-opus-4-6 | $5.00 | $25.00 | https://www.anthropic.com/pricing (API tab) | 2026-04-15 |
| claude-sonnet-4-6 | $3.00 | $15.00 | https://www.anthropic.com/pricing (API tab) | 2026-04-15 |

Secondary confirmation from official docs page: https://platform.claude.com/docs/en/about-claude/pricing

### Prompt caching adders (for reference in cost model)

| Model | Cache write (5 min TTL) $/MTok | Cache write (1 hr TTL) $/MTok | Cache read (hit) $/MTok |
|-------|-------------------------------|-------------------------------|-------------------------|
| claude-opus-4-6 | $6.25 | $10.00 | $0.50 |
| claude-sonnet-4-6 | $3.75 | $6.00 | $0.30 |

### Batch API rates (50 % discount, async only — not applicable to Managed Agents sessions)

| Model | Batch input $/MTok | Batch output $/MTok |
|-------|--------------------|---------------------|
| claude-opus-4-6 | $2.50 | $12.50 |
| claude-sonnet-4-6 | $1.50 | $7.50 |

Note: Batch API discount does **not** apply inside Claude Managed Agents sessions (sessions are stateful/interactive — no batch mode).

## Platform costs

### Claude Managed Agents — separately published billing model

Source: https://platform.claude.com/docs/en/about-claude/pricing#claude-managed-agents-pricing

Billing is on **two dimensions**:

| Dimension | SKU | Rate | How metered |
|-----------|-----|------|-------------|
| Tokens | Standard model rates (see table above) | $5/$25 MTok (Opus 4.6) or $3/$15 MTok (Sonnet 4.6) | All input + output tokens consumed by a session |
| Session runtime | Session runtime | **$0.08 per session-hour** | Accrues only while session status = `running`; idle / rescheduling / terminated time is excluded |

**Metering details:**
- Runtime is measured to the millisecond.
- Time the session spends `idle` (waiting for a user message or tool confirmation), `rescheduling`, or `terminated` does **not** accrue runtime charges.
- Session runtime replaces the standalone Code Execution container-hour charge — you are **not** billed separately for container hours on top of session runtime.
- Prompt caching multipliers apply identically inside sessions.
- Web search inside a session costs $10 / 1,000 searches (same as standard API).

**Modifiers that do NOT apply to Managed Agents sessions:**

| Modifier | Reason |
|----------|---------|
| Batch API 50 % discount | Sessions are stateful/interactive |
| Fast mode premium | Inference speed managed by runtime |
| Data residency multiplier (`inference_geo`) | Messages API field, not applicable |
| Long context premium | Context window managed by runtime |
| Third-party platform pricing (Bedrock, Vertex) | Managed Agents is Claude API only |

### Worked example from official docs

A one-hour Opus 4.6 coding session consuming 50,000 input tokens and 15,000 output tokens:

| Line item | Calculation | Cost |
|-----------|-------------|------|
| Input tokens | 50,000 × $5 / 1,000,000 | $0.25 |
| Output tokens | 15,000 × $25 / 1,000,000 | $0.375 |
| Session runtime | 1.0 hr × $0.08 | $0.08 |
| **Total** | | **$0.705** |

### Other platform feature costs (for completeness)

| Feature | Rate |
|---------|------|
| Web search (server-side tool) | $10 / 1,000 searches |
| Code execution (standalone, outside Managed Agents) | $0.05 / container-hour (1,550 free hrs/org/month) |
| US-only data residency (`inference_geo`) | 1.1× multiplier on all token categories |

## Ambiguities / gaps

- **No beta disclaimer found for Managed Agents pricing.** The platform docs present the $0.08/session-hour rate as generally available without beta or preview caveats (as of 2026-04-15). However, Managed Agents itself was launched under the `managed-agents-2026-04-01` beta API header; runtime pricing could change when the API exits beta.
- **No per-environment-hour or per-file-storage-GB-month charge found.** The published billing model is exclusively tokens + session-hours. Environment and file storage are not billed as separate line items in any public documentation found.
- **No per-session flat fee.** Billing is purely time × $0.08, not a per-session connection charge.
- **Volume discounts are negotiated case-by-case** (enterprise sales required); no published discount schedule for Managed Agents runtime.
- **Fast mode (beta / research preview) on Opus 4.6** costs $30/$150 MTok (6× standard) but is explicitly excluded from Managed Agents sessions.
- Third-party platform availability: Managed Agents is **Claude API direct only** — not available on AWS Bedrock or Google Vertex AI.

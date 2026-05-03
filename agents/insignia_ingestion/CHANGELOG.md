# `insignia_ingestion` system prompt changelog

The deployed agent's `system` field is the source of truth on the platform; this directory persists each version's prompt for diffing and provenance.

## v3.2 (2026-05-03)

After v3.1's second-trial findings (`INGESTION_V3_1_SECOND_TRIAL_2026-05-03.md`): 17/18 → **18/18 with one scorer fix**, single n=1 trial. The "embedded dictamen" classification ambiguity is closed by moving the contract spec into the kickoff and matching by file count + classification confidence rather than semantic content.

| Fix | Diff vs v3.1 | Reason |
|---|---|---|
| `required_documents` is now a kickoff input, not prompt-baked | New section "Required-document matching"; the prompt explicitly says the kickoff is authoritative and the agent does NOT invent the list | v3.1 hard-coded `[balance, cartera, dictamen]` and the agent classified embedded auditor narrative inside an EF PDF as the dictamen, declaring `status: ok`. The classification was the failure mode, not the rule absence. |
| **Embedded content does not count as present** | Explicit rule: "If the dictamen del auditor is referenced or partially included as pages within an EF binder, that does NOT make `dictamen` present — `dictamen` requires a separate, standalone signed PDF in `input_files`." | Closes the v3.1 misclassification. The matching is by file count + classification confidence (≥0.8), not by inspecting file contents for embedded sections. |
| Stricter classification rule | Step 1 now says: "Be conservative: if a file plausibly contains multiple types, classify it as the PRIMARY type only — `balance`, not `dictamen`." | Removes the agent's room to assign two types to one file. |
| Format-discipline rule restated more aggressively | Top-level "CRITICAL" header, multi-line "do not announce that you're done" / "do not summarize what you did" / "no closing summary" rules with a regex hint (`^\{.*\}$`) | v3.1 still emitted *"All outputs are in the correct locations. Everything is verified and complete."* before the JSON. v3.2 doubles down on no-trailing-text. |
| `required_documents` defaults to `[]` | Explicit default rule: "If `required_documents` is absent from the kickoff, default to `[]` (no required items) and emit `status: 'ok'` regardless of file count." | Backwards-compatibility for older kickoffs that don't carry the field. |

### NOT changed in v3.2

- The v3 manifest schema, the email-draft mechanic, the execution-efficiency section, the memory mount path fix from v3.1.

### Eval

Re-run `evals/ingestion/tafi_2025_v3` (kickoff updated to carry `required_documents`). Result: 18/18 process+outcome assertions PASS, n=1. Captured at `evals/runs/2026-05-03T12-19-54Z-ingestion-tafi_2025_v3-agent_011Cafd9hFGY7U239itLqJ8n/`. Wilson 95% CI on each headline column is `1.000 [0.207, 1.000]` — the lower bound is loose at n=1; need n≥10 to claim ≥0.7.

### Production decision

v3.2 is the **prompt-side production candidate** for the email-driven POC. Next decisions:
- v2-deployed (`agent_011CaaVZBRsEyuN4hXWMRR4Z`) ↔ v3.2 paired-McNemar A/B at n≥25 per side on this slice — confirms the "v3 is the production winner" claim per playbook § 9.
- Add at least one ALTERNATE eval slice with a different missing item (e.g., balance-missing instead of dictamen-missing) to confirm the kickoff-driven mechanism generalizes.

## v3.1 (2026-05-03)

Surgical fixes after the v3 first-trial findings (`INGESTION_V3_FIRST_TRIAL_2026-05-02.md`). Three prompt-side issues addressed in one diff so the next live trial tests all three together.

| Fix | Diff | Reason |
|---|---|---|
| Memory mount path | `/mnt/memory/priors/<id>.json` → no longer hard-coded; prompt now reads memory_paths from kickoff and falls back to probing `/mnt/memory/<store>/...` | Memory stores actually mount at `/mnt/memory/<kebab-cased-store-name>/<storage-path>`. v3 prompt referenced the wrong root; Sonnet recovered by probing but the prompt was wrong. |
| Required-documents list | New section "Required input documents (Insignia contract baseline)" + cross-check rule in step 4 | v3 had no signal for "what's missing." Agent processed 2/3 required documents and declared `status: ok`. v3.1 hard-codes `[balance, cartera, dictamen]` as the baseline; missing any → `status: blocked`. |
| Format discipline | Adopted resolver v2's pattern: explicit FIRST/LAST char rule + ✅/❌ examples in a "Response format discipline" subsection | v3 emitted ` ```json ` fences AND a "All outputs written. Final envelope:" prose preamble. Sonnet on resolver v2 (same model tier) was clean across 4 slices, so this is prompt-induced. |

### NOT changed in v3.1

- The v2-shape execution-efficiency section, the manifest schema, the email-draft mechanic. These were not implicated by the trial.
- The "required-documents = [balance, cartera, dictamen]" list is hard-coded into the prompt (option A from the findings doc). The production-correct shape is **option B** — carry the list in the kickoff (`expected_documents: [...]`) so the prompt is generic and the orchestrator owns the contract spec. Move to B in a future version once we've validated the baseline mechanism works.

### Eval

Re-run `evals/ingestion/tafi_2025_v3` (same slice). Expected: 5/5 process+outcome assertions pass on n=1.

## v3 (2026-05-02)

Surgical diff vs. v2 for the email-driven POC. Spec: `docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md` § 4.

### Added

| Add | What |
|---|---|
| `client_name`, `email_context`, `memory_paths` in **Inputs** | Kickoff schema bumped per spec § 4.4 (`IngestionKickoff`). Email metadata trimmed to ≤500-char body excerpt; `language` ∈ `{es, en, pt}`. |
| New step 5: **Draft a follow-up email** when `missing_fields` is non-empty | Reads 1–3 examples from `memory_paths.tone_examples_dir` to match Insignia's voice. Writes in `email_context.language` (default Spanish). Threads on `email_context.messageId`. References specific missing items by name. The agent does NOT send — orchestrator does after human approval. |
| `client_email_draft` and `triage_request` keys in **manifest schema** | Per spec § 4.5. `triage_request` always `null` here (triage is upstream); both are present so the orchestrator can switch on the union of resolver + ingestion outputs. |
| Memory store mounted at `/mnt/memory/` | Read-only access to `priors/<contract_id>.json` and `tone_examples/`. Per spec § 5.2 access matrix: agents never write to memory. |

### Removed

- The contract-id-derivation paragraph from v2's "Inputs you receive". Resolved upstream by the resolver agent now.

### Preserved verbatim from v2

For the v2↔v3 paired-McNemar A/B (ingestion axis only), v2's substance is kept untouched:

- The `/mnt/session/uploads/input/<contract_id>/` mount-path note (R001).
- The "do NOT also copy outputs to `/mnt/session/outputs/`" rule (R003).
- The `/tmp/<contract_id>/` persistence guidance and "combine related operations into one bash call" rule (R004).
- The "no surrounding prose, no markdown code fences" envelope discipline (R005).
- The pdf/xlsx/docx skill fallback chain.
- The cleaner-not-modeler identity, extended in v3 to "cleaner who can also draft the missing-data follow-up — not a modeler, not a router."

### Scope discipline (per spec § 4.2)

v3 explicitly does NOT contain triage logic. The kickoff always carries a resolved `contract_id`; if it doesn't, the prompt instructs the agent to emit `status: "failed"` and exit. The poller's resolver step is responsible for everything pre-resolution.

### Eval

Eval slice: `evals/ingestion/tafi_2025_v3/` (extends `evals/ingestion/tafi_2025` with v3-specific assertions on `client_email_draft.*` and the manifest's new keys).

## v2 (2026-04-30)

Four targeted fixes from the 2026-04-30T18-40-29Z-poc run-log review (`runs/latest/summary.md` + the L0–L10 stack analysis in session 9ec4e973):

| Fix | What changed | Why |
|---|---|---|
| Mount path | `/mnt/session/input/<contract_id>/` → `/mnt/session/uploads/input/<contract_id>/` (3 occurrences) | Platform auto-prefixes `mount_path` for `type: file` resources with `/mnt/session/uploads/`. v1's path knowledge was wrong; the POC kickoff carried a workaround that bypassed the bug. Fix surfaces the right path so kickoffs no longer have to compensate. |
| Skip redundant `cp -r` | New rule: "do NOT also copy outputs to `/mnt/session/outputs/`" | v1 wrote outputs to `/mnt/session/out/` then `cp -r`'d to `/mnt/session/outputs/` (~3s wasted per run; no observed downstream consumer). |
| State persistence to `/tmp/` | New "Execution efficiency" section directing the agent to persist extracted PDF text + CSV profile to `/tmp/<contract_id>/` and re-read on subsequent bash calls | v1 re-read PDF pages 27–39 in two separate bash calls (~90s wasted) because Python interpreters don't persist state across `bash` invocations. |
| Combined CSV operations | New rule: "combine related operations into one bash call where they share data" | v1 ran CSV profiling and aggregations in two separate bash calls, re-loading the 27 MB CSV twice (~30s wasted). |

Manifest schema bumped to include `pdf_extraction.{method,pages,avg_chars_per_page}`, `csv_extraction.{rows,cols}`, `reconciliations.*`, and a top-level `outputs[]` array. These are observability fields the eval scorer asserts against — surfacing them was previously implicit in the agent's textual output.

**Pre-registered prediction (per playbook § 9 — Lin et al. arXiv:2604.25850):** when paired-A/B'd against v1 on a no-workaround kickoff (one that does NOT spell out absolute paths), v2 will show outcome-column pass-rate ≥ 0.80 and v1 will show outcome-column pass-rate ≤ 0.20. n=10 paired trials per side, McNemar's exact test, α=0.05.

### Known issues v2 does NOT fix (deliberate scope cut)

These are agent-behavior inefficiencies observed in the v1 trace that v2's prompt edits do not address. Judged minor enough to not block ship; the trade-off is more scope = more rule interactions = more risk of new bugs.

- **Truncated bash output re-read.** When a bash call's stdout exceeds the inline truncation limit, the platform writes the full output to `/tmp/ale-bash-full-output-<id>` and the agent has to issue an extra `cat` call to retrieve it. Observed once in the v1 trace (one extra tool call, negligible time). Not addressed because the truncation behavior is platform-level, not prompt-fixable.
- **`pypdf` page-count probe separate from full PDF extraction.** v1 ran pypdf once to count pages, then again to extract text. Could be combined. Not addressed because the second call is in a fallback path that may not always run; combining adds branch complexity for marginal speedup.
- **Two separate skill-docs reads at start.** Agent read the `pdf` skill docs and `xlsx` skill docs as two `read` tool calls before doing any work. Probably initial exploration rather than a bug. Not addressed.

### Known unknowns

- The four addressed fixes + three not-addressed inefficiencies above are the *complete observable list* from a single trace (n=1, one client). The factsheet calls for ≥20 traces before any "v2 fixes everything" claim. Whatever the next contract surfaces is invisible today.
- v2 may introduce new issues (more rules in a prompt = more chance of unintended interactions). Not measured because the A/B was deemed not worth running against the contaminated seed case (Tafi was the case v1 was already shaped against — running v2 against the same case mostly tests "did we break the seed").

### Deployment readiness

v2 is **ready to deploy on the next real ingestion contract** — at that point the deployment IS the production decision (not an experiment), and the eval framework provides the smoke check on a non-contaminated case. Until then v2 lives here as a committed artifact, not a deployed agent.

## v1 (2026-04-30, original)

The first deployed prompt. Captured from `runs/2026-04-30T18-40-29Z-poc/design/system_prompts/ingestion.md`.

Known issues (addressed in v2):
- Wrong mount path (`/mnt/session/input/` instead of `/mnt/session/uploads/input/`)
- No state-persistence guidance → PDF re-reads
- No discouragement of the redundant `cp -r` to `/mnt/session/outputs/`
- No guidance on combining CSV operations

Known issues (NOT addressed in v2):
- Truncated bash output re-read (platform-level)
- pypdf page-count probe separate from extraction
- Two separate skill-docs reads at start

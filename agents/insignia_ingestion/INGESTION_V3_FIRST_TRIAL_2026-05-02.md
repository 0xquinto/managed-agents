# Ingestion v3 — first live trial — 2026-05-02

Sonnet-4-6 v3 prompt (`agent_011CaepbFeQ7jVvS8jY5baTX`) against `evals/ingestion/tafi_2025_v3` slice (dictamen pruned, expects `status: blocked`). 1 trial, n=1.

Captured at `evals/runs/2026-05-03T02-11-22Z-ingestion-tafi_2025_v3-agent_011CaepbFeQ7jVvS8jY5baTX/trials/v3_000/`.

**Trial outcome: 0/5 process+outcome assertions pass.** Trial completed cleanly (`idle:end_turn`, ~8 minutes), envelope captured, manifest written inside the session — but the failure surfaces 4 distinct issues, only one of which is "the v3 prompt is wrong."

## Finding 1 — Memory store mount path drift (HIGH)

**The memory store mounts at `/mnt/memory/<store_name_kebab>/<storage_path>`, not `/mnt/memory/<storage_path>`.**

- Configured: store name `insignia_memory`, storage paths `/priors/tafi_2025_v3.json`, `/tone_examples/example_001.txt`, etc.
- Container path the agent saw: `/mnt/memory/insignia-memory/priors/tafi_2025_v3.json` (underscore→hyphen, store name as a path segment).
- v3 prompt (`agents/insignia_ingestion/v3_system_prompt.md`) and kickoff (`evals/ingestion/tafi_2025_v3/kickoff_v3.json`) both reference `/mnt/memory/priors/...` directly — wrong.
- `.claude/agents/sessions-expert.md` L196 says "memory_store (`/mnt/memory/...`) show absolute paths, suggesting they are not affected by the [file-resource] prefix" — also wrong / incomplete: there's a different prefix (the kebab-cased store name).

The Sonnet agent recovered: probed `ls /mnt/memory/`, saw `insignia-memory/` as the only entry, used `ls /mnt/memory/insignia-memory/` to find `priors/` and `tone_examples/`, then read all 4 memories. **Haiku may not recover this gracefully** — worth re-confirming under the production tier choice (likely Sonnet for ingestion, but document the assumption).

**Action items:**
- Update v3 prompt: change `/mnt/memory/priors/<contract_id>.json` → `/mnt/memory/<store_name>/priors/<contract_id>.json`, OR generalize to "Find the memory store under `/mnt/memory/`; the store mount name is the kebab-cased name configured at session creation."
- Update `kickoff_v3.json` `memory_paths` blob to match.
- Update `sessions-expert.md` L196 with the corrected mount semantics.
- File a behavior-auditor probe extension for the memory_store mount-path case (P-sessions-1 only covers files).

## Finding 2 — Agent did not detect missing dictamen (HIGH, eval-blocking)

The slice deliberately omits the dictamen attachment to provoke `status: blocked` with `missing_fields ⊇ ["dictamen"]`. The agent emitted `status: "ok"` with `missing_fields: []` — never recognized dictamen as required.

The v3 prompt has no "required documents" list or "blocked when X is missing" rule for the financial-modeling case. The agent has no signal to know that 2 input files (PDF balance + CSV cartera) is incomplete vs. complete.

**Two ways to fix:**
- **A. Bake required-fields list into the prompt** — "For an Insignia contract, required input documents are: balance, cartera, dictamen del auditor. If any are absent, set `status: blocked` and list the missing ones in `missing_fields`." Simplest, but couples the prompt to one contract type.
- **B. Carry required-fields list in the kickoff** — `expected_documents: ["balance", "cartera", "dictamen"]`. Keeps prompt generic, makes the orchestrator carry domain knowledge. Better long-term.

Option B is the production-correct shape. Option A is fine for the eval slice if we just want to validate the v3 mechanism (draft when blocked) works.

## Finding 3 — Sonnet ingestion v3 violates format discipline

```
All outputs written. Final envelope:

```json
{
  "status": "ok",
  ...
}
```
```

Both `no_markdown_fences` and `no_surrounding_prose` fail. Notable because Sonnet on the resolver v2 prompt produced clean JSON across all 4 slices (see `agents/insignia_resolver/MODEL_TIER_FINDINGS_2026-05-02.md` § 3) — so this is **prompt-induced**, not model-induced.

The v3 ingestion prompt should adopt the same discipline pattern as resolver v2: explicit "FIRST char `{`, LAST char `}`, no preamble, no fences" rule. The current prompt language is weaker.

## Finding 4 — Runner's manifest-fetch step is broken (MEDIUM, runner bug)

Agent successfully wrote `/mnt/session/out/tafi_2025_v3/manifest.json` (5047 chars) via the `write` tool — verified in events.json. But `manifest_captured: false` in trial.json, and no `manifest.json` lands in the trial dir.

`runner.py::fetch_container_file` fires a follow-up `user.message` asking the agent to `cat` the file. Suspect cause: (a) the follow-up event triggers a fresh agent turn that doesn't behave like a simple shell command — Sonnet may interpret the request and return commentary instead of raw output, or (b) the follow-up doesn't reach the agent because session is past the model's turn budget. Worth investigating in a separate runner fix — orthogonal to the v3 prompt question.

**Workaround for re-running the trial today:** read the manifest content directly from the captured `events.json` (the `agent.tool_use` event for `write` carries the full manifest in `input.content`). The runner could short-circuit by extracting from events instead of re-cat'ing in a follow-up turn.

## What the manifest actually said

Agent wrote a complete v3-shaped manifest with all required keys: `entity`, `periods`, `pdf_extraction`, `csv_extraction`, `quality_flags`, `reconciliations`, `missing_fields`, `outputs`, `client_email_draft`, `triage_request`. **`status` is null**, `missing_fields: []`, `client_email_draft: null` — consistent with finding 2 (agent saw no problem, so didn't draft an email).

The bones are there. The agent followed the schema. The only thing missing is the "this contract is incomplete" judgment — finding 2.

## Cost

~$0.15 (one Sonnet ingestion session, 18 tool calls, ~8 min). Manifest, events, envelope all captured.

## Recommended next steps (sequence)

1. Fix finding 1 (memory mount path) in v3 prompt + kickoff. Required for any future trial.
2. Decide finding 2 strategy (A vs B). Option A unblocks the slice today; option B is the production answer.
3. Fix finding 3 (format discipline) — surgical prompt edit, ~5 lines.
4. File finding 4 as a runner issue; workaround by reading manifest from events.json for now.
5. Re-run n=1 trial; if 5/5 pass, fan out to n=10 for the v2↔v3 paired-McNemar A/B.

Per playbook § 9, the A/B between v2-deployed (`agent_011CaaVZBRsEyuN4hXWMRR4Z`) and v3 (`agent_011CaepbFeQ7jVvS8jY5baTX`) is the "is v3 the production winner" decision — needs n≥25 paired per side once the prompt-side fixes land.

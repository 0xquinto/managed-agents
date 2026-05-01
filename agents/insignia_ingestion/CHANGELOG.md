# `insignia_ingestion` system prompt changelog

The deployed agent's `system` field is the source of truth on the platform; this directory persists each version's prompt for diffing and provenance.

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

## v1 (2026-04-30, original)

The first deployed prompt. Captured from `runs/2026-04-30T18-40-29Z-poc/design/system_prompts/ingestion.md`.

Known issues (all addressed in v2):
- Wrong mount path (`/mnt/session/input/` instead of `/mnt/session/uploads/input/`)
- No state-persistence guidance → PDF re-reads
- No discouragement of the redundant `cp -r` to `/mnt/session/outputs/`
- No guidance on combining CSV operations

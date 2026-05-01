# Prompt lint report

Scanned **21** prompt files.

Found **8 error**, **6 warn**, **0 info** violations.

## Rules

| Rule | Severity | Title |
|---|---|---|
| `R001` | error | wrong-mount-path |
| `R002` | warn | mount-path-prefix-undocumented |
| `R003` | warn | redundant-output-copy |
| `R004` | warn | fresh-interpreter-undocumented |
| `R005` | warn | json-envelope-unguarded |
| `R006` | warn | missing-required-section |

## Violations

### `.claude/agents/lead-0.md`

- **`R002`** (warn) line 321 — Documents `mount_path` without explaining the `/mnt/session/uploads/` auto-prefix for type=file resources. Downstream prompt authors will compute wrong container paths.
  - `/sessions/*/session_resources/*/mount_path`

### `agents/insignia_ingestion/v1_system_prompt.md`

- **`R001`** (error) line 3 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- `contract_id` — run correlation ID - `input_files` — list of absolute paths under `/mnt/session/input/<contract_id>/`. Formats are mixed and messy: PDFs (financial statements, risk classifications),`
- **`R004`** (warn) line 5 — Actor prompt uses bash for file extraction without warning that the bash interpreter resets between calls. Add `/tmp/<id>/` persistence guidance and a 'combine related operations into one bash call' rule. Source: v1 ingestion trace re-read PDF ~90s wasted.
  - `1. **Classify each file.** Determine type (financial statement, identifier doc, risk classification, market research, other) and confidence. Write classifications to `/mnt/session/out/<contract_id>/cl`
- **`R001`** (error) line 10 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- Never modify files under `/mnt/session/input/`. Read-only (mounted files are RO copies anyway). - All outputs go under `/mnt/session/out/<contract_id>/`. - Prefer auto-correction ONLY when confidenc`
- **`R001`** (error) line 13 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `Tools: `bash`, `read`, `write`, `edit` + `pdf`, `xlsx`, `docx` skills. (MS Graph MCP for pulling intake files from Teams/OneDrive will be wired in v2 once vault credentials are provisioned; v1 reads l`

### `runs/2026-04-14T21-37-35Z/design/system_prompts/bespoke_modeler.md`

- **`R004`** (warn) line 24 — Actor prompt uses bash for file extraction without warning that the bash interpreter resets between calls. Add `/tmp/<id>/` persistence guidance and a 'combine related operations into one bash call' rule. Source: v1 ingestion trace re-read PDF ~90s wasted.
  - `- **All writes to the model — use `bash` + `openpyxl` ONLY.** The `xlsx` skill does not reliably preserve named ranges or cross-sheet formula links on load-modify-save. Writing through the skill risks`

### `runs/2026-04-14T21-37-35Z/design/system_prompts/coordinator.md`

- **`R001`** (error) line 6 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- `input_files` — list of absolute paths to client-provided files mounted under `/mnt/session/input/<contract_id>/``
- **`R001`** (error) line 37 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- Every file path you write or reference MUST be under `/mnt/session/input/<contract_id>/` (read) or `/mnt/session/out/<contract_id>/` (write). No other paths.`

### `runs/2026-04-14T21-37-35Z/design/system_prompts/ingestion.md`

- **`R001`** (error) line 6 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- `input_files` — list of absolute paths under `/mnt/session/input/<contract_id>/`. Formats are mixed and messy: PDFs (financial statements, risk classifications), Excel workbooks, CSVs, and occasiona`
- **`R004`** (warn) line 12 — Actor prompt uses bash for file extraction without warning that the bash interpreter resets between calls. Add `/tmp/<id>/` persistence guidance and a 'combine related operations into one bash call' rule. Source: v1 ingestion trace re-read PDF ~90s wasted.
  - `- PDFs → use the `pdf` skill first. If the skill returns blank or near-blank output (<50 characters of text per page average), the PDF is likely scanned/image-only — fall back to `bash` + `pdfplumber``
- **`R001`** (error) line 54 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `- Never modify files under `/mnt/session/input/`. Read-only (mounted files are RO copies anyway).`
- **`R001`** (error) line 63 — Path `/mnt/session/input/` does not exist for type=file resources. Files mounted via session_resources are auto-prefixed with `/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`.
  - `Tools: `bash`, `read`, `write`, `edit` + `pdf`, `xlsx`, `docx` skills. (MS Graph MCP for pulling intake files from Teams/OneDrive will be wired in v2 once vault credentials are provisioned; v1 reads l`

### `runs/2026-04-14T21-37-35Z/design/system_prompts/synthesis.md`

- **`R004`** (warn) line 13 — Actor prompt uses bash for file extraction without warning that the bash interpreter resets between calls. Add `/tmp/<id>/` persistence guidance and a 'combine related operations into one bash call' rule. Source: v1 ingestion trace re-read PDF ~90s wasted.
  - `1. **Read the model.** Extract every computed KPI, trend, and forecast from the four core sheets plus bespoke assumptions. The `xlsx` skill is for read/inspect only — use it to preview cells and named`

### `runs/2026-04-14T21-37-35Z/design/system_prompts/transversal_modeler.md`

- **`R004`** (warn) line 16 — Actor prompt uses bash for file extraction without warning that the bash interpreter resets between calls. Add `/tmp/<id>/` persistence guidance and a 'combine related operations into one bash call' rule. Source: v1 ingestion trace re-read PDF ~90s wasted.
  - `- **All writes (populating cells, inserting formulas, adding rows) — use `bash` + `openpyxl` ONLY.** The `xlsx` skill does not reliably preserve named ranges, cross-sheet formula links, or dynamic arr`


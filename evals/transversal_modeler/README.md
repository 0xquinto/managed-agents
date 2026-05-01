# `evals/transversal_modeler/`

Eval slices for the `transversal_modeler` role — the agent that takes
ingestion's normalized output and builds the standardized financial core
workbook (P&L, Balance Sheet, Cash Flow, Valuation sheets).

## Why a second role exists

This directory is the **proof of scaffold reusability**. The L6 question
behind PRs #5–#8 was: does the eval framework generalize beyond one agent?
A second role with materially different I/O shape is the test:

|  | `ingestion` | `transversal_modeler` |
|---|---|---|
| **Input** | Raw PDF + CSV from client | Normalized CSVs + JSON manifest from ingestion |
| **Output** | Manifest JSON + normalized CSVs | `model.xlsx` (Excel workbook) |
| **Envelope** | `{status, normalized_dir, manifest_path, missing_fields[]}` | `{status, model_path, transversal_sheets[], validation}` |
| **Ground truth** | File-existence + manifest-field assertions | Sheet existence, named-range preservation, balance-check formula presence |
| **Failure modes** | Wrong mount path, sequential CSV ops | Skill-based xlsx writes corrupting named ranges (see prompt) |

If the same scaffold (spec + factsheet + expected.json + resources.json +
kickoff variants + score columns) drops cleanly into both, the abstraction
is real.

## Forward-looking status

> **The `transversal_modeler` agent is not yet provisioned on the platform.**
> The full Insignia POC ran only the `ingestion` agent inline; the downstream
> roles were designed (see `runs/2026-04-14T21-37-35Z/design/system_prompts/`)
> but never deployed. This slice is therefore **scaffold-only** at ship: the
> directory shape, fixtures, and assertions are real and reviewed; the
> live trial loop turns on once the agent is provisioned.

The point of shipping this now is to prove that the scaffold doesn't need to
be re-architected for a different agent. If the directory structure had to
change to accommodate Excel output, that would be a real signal that the
ingestion-shaped scaffold was too narrow.

## Cases

- `tafi_2025/` — same client as `ingestion/tafi_2025`, downstream of its
  output. Fixtures are synthesized to match the schema ingestion produces;
  numerical values are illustrative only (no real PII).

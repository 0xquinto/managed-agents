# `lint/` — prompt lint

Static checker for managed-agent prompt files. Each rule encodes an observed
failure mode from a real session trace, not a style preference.

## Rules

| ID | Severity | Source observation |
|---|---|---|
| `R001` | error | `behavior-auditor` probe `P-sessions-1`. `type=file` resources are auto-prefixed with `/mnt/session/uploads/`; prompts that hardcode `/mnt/session/input/` send the agent to a path that does not exist. |
| `R002` | warn | Same as R001, applied to *expert* prompts that document `mount_path` without explaining the prefix. |
| `R003` | warn | POC trace 2026-04-30 (`sesn_011CaacsF6hNQ5GJPNQMie2E`): redundant `cp -r` from custom out dir to `/mnt/session/outputs/` cost ~3s/run. |
| `R004` | warn | Same trace: bash spawns a fresh interpreter per call; without `/tmp/<id>/` persistence guidance the agent re-extracted PDF pages 27–39 (~90s wasted). |
| `R005` | warn | General: actor prompts that promise a JSON envelope but don't forbid surrounding prose / markdown fences routinely produce ```` ```json ```` wrapped output that breaks strict downstream parsers. |
| `R006` | warn | Structural: actor prompt missing one of the required schema sections. See [`lint/schema.md`](schema.md). |

## Usage

```bash
python lint/prompt_lint.py                       # markdown report, exits 1 on any error
python lint/prompt_lint.py --format json         # machine-readable
python lint/prompt_lint.py --severity warn       # show warns and errors only
python lint/prompt_lint.py --paths agents/foo    # scope to a path
python lint/prompt_lint.py --no-default-excludes # include frozen historical files
```

## Default excludes

Two paths are excluded from CI scans because they're intentionally preserved:

- `agents/insignia_ingestion/v1_system_prompt.md` — the v1 baseline. Kept frozen
  for the v1 vs v2 paired McNemar A/B in `evals/ingestion/tafi_2025/`. Editing
  it would invalidate the comparison.
- `runs/` — captured historical run snapshots. Frozen by definition.

Override either with `--exclude <path>` (additive to defaults) or
`--no-default-excludes` (drop them entirely — used by `lint/baseline.md`).

## Adding to the exclude list

Edit `DEFAULT_EXCLUDES` in `lint/prompt_lint.py`. Each entry is a repo-relative
path; suffix `/` for directory match. A new exclude needs a one-line comment
explaining *why* the file is being preserved as-is — without that, the next
contributor will assume it should be cleaned up.

## What it scans

By default: `.claude/agents/`, `agents/`, `runs/`. Within those, files matching
`*-expert.md`, `*_system_prompt.md`, `v*_system_prompt.md`, named scripts
(`lead-0.md`, `behavior-auditor.md`, `docs-auditor.md`), and any `.md` under a
`system_prompts/` directory.

## Adding a new rule

Each rule should cite an evidence source — a probe ID, a session trace
timestamp, or a specific PR review finding. Style-preference rules without an
evidence trail belong in a separate linter, not here.

```python
def rule_rNNN_short_name(path: Path, content: str) -> list[Violation]:
    """RNNN: one-sentence what + the source observation."""
    ...
```

Then append to `RULES`. `lint/baseline.md` is a captured snapshot of the
current repo's violations — refresh it after rule changes (`python
lint/prompt_lint.py > lint/baseline.md`).

## Relationship to `behavior-auditor`

`behavior-auditor` (in `.claude/agents/`) detects platform↔documentation drift
at runtime by sending real probes. This lint detects prompt↔prompt drift at
edit time. Together they form a closed loop:

```
behavior-auditor probes the live API   → finds drift
            │
            ▼
runs/behavior-drift/<ISO>.md (weekly)  → human reviews
            │
            ▼
python lint/audit_coverage.py          → which probes have no lint coverage?
            │
            ▼
python lint/from_audit.py <report>     → scaffold a rule for each new drift
            │
            ▼
lint/proposed/R0NN_<probe>__<slug>.py  → human edits regex / heuristic
            │
            ▼
move into lint/prompt_lint.py + RULES  → CI now blocks the mistake forever
```

Every R0NN rule should cite its source probe ID in its docstring. `audit_coverage.py`
verifies the citation; without it, the loop is open and a future drift
re-discovery is silent.

### Pipeline tools

- `lint/audit_coverage.py` — coverage matrix: probes ↔ citing rules. Pass `--strict`
  to exit non-zero if any probe is uncovered.
- `lint/from_audit.py` — parse a `runs/behavior-drift/<ISO>.md` report, identify
  drifts not yet covered, write rule scaffolds to `lint/proposed/`. Use `--dry-run`
  to print without writing.

The pipeline is intentionally not fully automatic: the regex / heuristic in each
new rule is a human judgment call (what's a documentation context vs an
instruction? what's the false-positive surface?). Auto-generated rules would be
noisy. The scaffold removes the boilerplate so the reviewer focuses on the
heuristic.

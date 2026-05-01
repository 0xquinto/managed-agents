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

## Usage

```bash
python lint/prompt_lint.py                 # markdown report, exits 1 on any error
python lint/prompt_lint.py --format json   # machine-readable
python lint/prompt_lint.py --severity warn # show warns and errors only
python lint/prompt_lint.py --paths agents/insignia_ingestion  # scope to a path
```

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
edit time. Run them together: behavior-auditor finds new failure modes; the
lint encodes them as rules so the same mistake doesn't reappear in another
prompt.

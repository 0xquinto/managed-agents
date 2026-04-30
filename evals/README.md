# Evals

Behavioral test cases for managed agents. Each case is a frozen ground-truth contract that any version of an agent must satisfy. The eval scorer takes a captured run (envelope + container artifacts) and produces a pass/fail scorecard.

Evals are how we tell whether an L6 (system-prompt) change made an agent better, worse, or the same. Without them every prompt edit is unfalsifiable.

## Structure

```
evals/
├── README.md             # this file
├── score.py              # scorer: takes a captured run, diffs against expected
├── runner.sh             # runner: provisions a fresh session, fires kickoff, captures envelope
└── <agent>/<case>/
    ├── README.md         # what this case tests + why
    ├── kickoff.json      # the user event that starts the run
    └── expected.json     # ground-truth assertions (typed: exact, contains, range, count_at_least, …)
```

Cases are organized by **agent role** (`ingestion`, `coordinator`, `synthesis`, …), not by client — the same `ingestion/tafi_2025` case scores any ingestion agent (v1, v2, future) without modification.

## Running an eval

### Replay mode (cheapest)

Score an existing captured run:

```bash
./score.py ingestion/tafi_2025 --run runs/latest/smoke/
```

Output: `evals/runs/<ts>-<case>-<agent_id>/scorecard.md` (pass/fail per dimension, summary line, exit code = number of failures).

### End-to-end mode (production)

Provision a new session against an agent and run the case live:

```bash
./runner.sh ingestion/tafi_2025 agent_011CaaVZBRsEyuN4hXWMRR4Z
```

The runner creates a session bound to the agent + case files, fires `kickoff.json`, polls until idle, captures the envelope + relevant container artifacts, then calls `score.py`. Costs platform quota.

### A/B mode

Same case, two agents:

```bash
./runner.sh ingestion/tafi_2025 agent_v1 agent_v2
```

Output: a side-by-side scorecard so prompt changes can be evaluated head-to-head.

## Adding a case

1. Create `evals/<agent>/<case>/`.
2. Write `kickoff.json` — the user event that starts the run.
3. Run the case once manually (or via `runner.sh`) and inspect the result.
4. Codify the result as `expected.json` — be deliberate about which fields are exact-match vs. tolerant.
5. Re-run `score.py` against the same captured run; it must pass.
6. Commit. Future runs of the same case must continue to pass — that's the regression bar.

## Assertion types in `expected.json`

| Type | Use for |
|---|---|
| `exact` | Values that must be byte-identical (`status: "ok"`, `missing_fields: []`). |
| `contains` | A field that must include a substring or set member. |
| `count_at_least` / `count_at_most` | Quality-flag counts, output-file counts. |
| `range` | Numeric tolerances (reconciliation diff within ±1.0). |
| `categories_include` | Quality-flag category labels that MUST appear (going-concern, encoding-issue). |

If you need a new assertion type, add it to `score.py`'s dispatch table and document it here.

## Anti-patterns

- **Don't commit client data.** Assertions reference structure, categories, and bounded counts — not specific borrower names, balance figures, or PII.
- **Don't make assertions too tight.** `quality_flag_count = 7` will break if the agent surfaces an 8th legitimate flag. Use `count_at_least: 5`.
- **Don't conflate eval and smoke.** A smoke test verifies "did anything come out." An eval verifies "did the right thing come out."

## Ground-truth provenance

The first case (`ingestion/tafi_2025`) was captured from the 2026-04-30 POC run (`runs/2026-04-30T18-40-29Z-poc/smoke/`). The run was reviewed manually for correctness before being frozen as ground truth. Every assertion in `expected.json` traces back to a verified output from that run.

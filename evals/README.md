# Evals

Behavioral test cases for managed agents, built to the discipline bar set in [`supabase-realtime-skill/playbook/PLAYBOOK.md`](../docs/external-references/playbook-reference.md) (the eval-methodology playbook synthesized from the LLM-evals YouTube playlist + ~50 academic sources).

Evals are how we tell whether an L6 (system-prompt) change made an agent better, worse, or the same. Without them every prompt edit is unfalsifiable.

## Discipline bar (per playbook)

This eval system commits to:

- **Tier-1 programmatic + tier-2 verifiable scoring; no LLM-judge** until human ground-truth + judge-alignment metrics exist (playbook § 2).
- **Binary pass/fail per assertion**, never Likert (playbook § 8 — Bowyer ICML 2025; OJItZndMUII).
- **Process / outcome / environment column tagging** on every assertion (playbook § 8 — Microsoft Universal Verifier 2026). The agent is graded on **process**; outcome and environment are reported separately to surface confounders.
- **Wilson 95% CIs** for every reported rate (playbook § 8 — Bowyer ICML 2025; ICLR Blogposts 2025). Wald / CLT-based intervals are forbidden.
- **≥3 paraphrases per kickoff prompt** (playbook § 8 — Lior et al. ReliableEval EMNLP 2025).
- **Pre-registered MDE before any A/B run** (playbook § 9 — Lin et al. arXiv:2604.25850 decision observability).
- **McNemar's exact test for paired binary A/B** (playbook § 9 — Miller arXiv:2411.00640).
- **Bonferroni multiplicity correction by default**, Holm-Bonferroni or BH if k≥4 (playbook § 8 — Luo NeurIPS 2025).
- **Run manifest with content shas** per slice run (playbook § 9 — OLMES NAACL 2025 + HAL ICLR 2026).
- **Bean's-8 construct-validity worksheet** per slice (playbook § 9 — Bean NeurIPS 2025 D&B). See `<slice>/spec.md`.
- **Eval Factsheet header** per slice (playbook § 9 — arXiv:2512.04062). See `<slice>/factsheet.md`.
- **Content checks defeat stub-file masking** — every `file_exists_and_nonempty` assertion confirms `>0 bytes` and parses as the declared format (playbook § 8 — Slice-1 self-clean masking lesson).
- **Smoke-grade vs. measurement-grade explicitly distinguished.** A single-trial run prints "n=1, exploratory only, not a measurement." Only `--trials` mode produces measurement claims.

## Structure

```
evals/
├── README.md                           # this file
├── score.py                            # scorer (single-trial + multi-trial aggregate, Wilson CIs, column tagging)
├── runner.sh                           # next PR — provisions session, fires kickoff, captures envelope + manifest
└── <agent>/<case>/
    ├── README.md                       # what this case tests + why
    ├── spec.md                         # Bean's-8 construct-validity worksheet (REQUIRED before measurement claims)
    ├── factsheet.md                    # Eval Factsheet header (auto-updated by runner)
    ├── kickoff_v1_canonical.json       # canonical phrasing
    ├── kickoff_v2_directive.json       # ≥3 paraphrases per playbook § 8
    ├── kickoff_v3_terse.json
    ├── kickoff_v4_conversational.json
    └── expected.json                   # ground-truth assertions, each tagged with column + rationale
```

Cases are organized by **agent role** (`ingestion`, `coordinator`, `synthesis`, …), not by client — the same `ingestion/tafi_2025` case scores any ingestion agent (v1, v2, future) without modification.

## Running

### Single-trial replay (cheap, smoke-grade)

```bash
./score.py ingestion/tafi_2025 --run runs/latest/smoke/
```

Output: a markdown scorecard with per-column pass/fail counts and a per-assertion detail table. **Header explicitly flags n=1 as exploratory, not a measurement.** Exit code = number of process-column failures (0 = agent passed).

### Multi-trial aggregate (measurement-grade)

```bash
./score.py ingestion/tafi_2025 --trials evals/runs/<ts>-<case>-<agent>/trials/
./score.py ingestion/tafi_2025 --trials evals/runs/<ts>-<case>-<agent>/trials/ --paraphrase v2_directive
```

Output: per-assertion `k/n` + Wilson 95% CI, broken out by column. Exit code = 1 if any process-column assertion has CI upper bound < 1.0 (the conservative gate).

### End-to-end provision-and-run (next PR)

```bash
./runner.sh ingestion/tafi_2025 \
  --agent-id agent_011CaaVZBRsEyuN4hXWMRR4Z \
  --env-id env_01WaJyfTQu9YDfQC5vXiXWj5 \
  --files file_011CaaVTNcQEKbg4Dt1vCcCF,file_011CaaVTupcqW1ZuPvi63z1M \
  --paraphrases all \
  --trials-per-paraphrase 25
```

The runner provisions a fresh session per trial (or batches per the platform's session reuse rules), fires the kickoff, polls until idle, captures envelope + manifest + events, writes a per-run `manifest.json` with foundation sha + agent shas + model + temp + seed, then calls `score.py --trials`.

### A/B mode (next PR)

```bash
./runner.sh ingestion/tafi_2025 --agent-id <v1>,<v2> --paraphrases all --trials-per-paraphrase 25
```

Output: side-by-side per-paraphrase scorecard + paired McNemar's exact test on each assertion. Pre-register MDE in the slice spec before running.

## Adding a case

1. **Read the playbook first.** Especially § 1 (start narrow), § 4 (failure-mode taxonomy from real traces, not a priori), § 8 (anti-patterns), § 9 (Bean's 8).
2. Create `evals/<agent>/<case>/`.
3. Write `spec.md` answering Bean's 8. The slice cannot ship measurement claims until § 7 (qualitative+quantitative error analysis) has ≥20 captured traces with open + axial coding.
4. Write `factsheet.md` (Eval Factsheet header).
5. Write **≥3** `kickoff_v*.json` paraphrases. Single-prompt scoring is forbidden (playbook § 8).
6. Run the case once manually and inspect the result. Sample ≥30 events for Mousavi's 4-flaw audit.
7. Codify the result as `expected.json` with `column` tags on every assertion. Be deliberate about exact-match vs. tolerant.
8. **Have the user (Benevolent Dictator) sign off** on `expected.json` before the slice ships measurement claims (playbook § 8).
9. Re-run `score.py` against the captured run; process column must pass.
10. Commit. Future runs of the same case must continue to pass — that's the regression bar.

## Assertion types in `expected.json`

| Type | Use for | Column tag |
|---|---|---|
| `exact` | Values that must be byte-identical (`status: "ok"`). | `process` (agent emitted it) |
| `contains` / `contains_one_of` | Field includes a substring or set member. | varies |
| `count_at_least` / `count_at_most` | Quality-flag counts, output-file counts. | `process` if agent emitted; `outcome` if file count |
| `range` | Numeric tolerances (reconciliation diff within ±1.0). | `outcome` (numerics check out) |
| `categories_include` | Quality-flag category labels that MUST appear. | `process` |
| `file_exists_and_nonempty` | Output file is present, > 0 bytes, parses as declared format. | `outcome` |
| `no_error_events` | Event stream contains zero `is_error: true`. | `environment` (most platform errors) |
| `stop_reason` | Agent terminates with the expected stop reason. | `process` |

If you need a new assertion type, add it to `score.py`'s dispatch table and document it here.

## Anti-patterns the playbook explicitly warns against (and how this system handles them)

| Anti-pattern (playbook § 8) | Mitigation in this system |
|---|---|
| Likert scoring | Binary only (enforced in `expected.json` schema) |
| Generic off-the-shelf metrics | Every assertion has a `rationale` field; "conciseness/hallucination/toxicity" rubrics rejected |
| Single-prompt cell scoring | ≥3 paraphrases enforced; runner sweeps all paraphrases |
| Stub-file masking (self-clean) | `file_exists_and_nonempty` requires content + parseability |
| Process/outcome/env conflation | Column tagging is mandatory in `expected.json` |
| n=1 measurement claims | Single-trial scorecards print exploratory banner; only `--trials` aggregates emit Wilson CIs |
| Static-benchmark contamination decay | `schema_version` + `slice_version` SemVer; quarterly freshness audit policy |
| No run manifest | Runner emits `manifest.json` per run with foundation sha + agent shas + model + temp + seed |
| Wald CIs at small n | Only Wilson CIs implemented; Wald not available |
| Multiplicity unhandled | Bonferroni default in A/B mode |
| Whack-a-mole prompt tweaking | Pre-registered MDE before A/B runs; regression set immutable |
| Stacked abstractions | Slice cannot ship without user sign-off on `expected.json` (Benevolent Dictator) |
| Reading thousands of traces | Stop at theoretical saturation (~20–40 per playbook § 1, § 9) |
| Phenomenon-proxy gap | Bean's-8 worksheet § 1 + § 8 names the construct + non-target routes |

## Honest gaps in this implementation

- **n=1 collected.** All cases ship with `--run` data only. The runner that backfills to n≥75 is the next PR.
- **No production-trace failure-mode taxonomy yet.** The first case was authored from the POC happy path. Open + axial coding pending.
- **No held-out validation case.** First case is the seed; the next client will be held-out.
- **No Benevolent Dictator sign-off recorded.** Awaits user review of `expected.json` before any measurement claim.
- **Self-clean masking only partially defended.** Content checks verify `>0 bytes` and parseability, not semantic correctness of normalized CSVs. Future enhancement: schema-validate columns and value distributions.
- **No A/B paired-test code yet.** McNemar's exact test ships with the runner.
- **No state-transition matrix yet.** Diff-eval visualization (which trials moved pass↔fail between agent versions) is a follow-up.

## Cleanup pass policy

If new playbook research supersedes a discipline rule above, the cleanup pass is part of the work — not an afterthought. Document the change in this README + the affected slice's `factsheet.md`.

## External references

- Local mirror of the playbook: `/Users/diego/Dev/supabase-realtime-skill/playbook/` (PLAYBOOK.md + research/*.md). Read PLAYBOOK § 8 (anti-patterns) and § 9 (cross-cutting heuristics) before adding any new assertion type, scoring rule, or slice.

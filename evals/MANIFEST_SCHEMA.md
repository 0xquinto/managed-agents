# Run manifest schema

Per playbook § 9 (OLMES NAACL 2025 + HAL ICLR 2026): every slice run MUST emit a `manifest.json` capturing enough state for the run to be replicated months later. Without this, a finding from May is unreplicable in July when the agent's prompt changes.

The runner (next PR) writes this file to `evals/runs/<ts>-<case>-<agent>/manifest.json`. The scorer reads it (when present) and includes the shas in the scorecard header.

## Required fields

```json
{
  "schema_version": 1,

  "slice": {
    "case_id": "ingestion/tafi_2025",
    "slice_version": "0.1.0",
    "expected_sha256": "<sha256 of expected.json>",
    "spec_sha256": "<sha256 of spec.md>"
  },

  "harness": {
    "foundation_commit_sha": "<git rev-parse HEAD of managed_agents repo>",
    "score_py_sha256": "<sha256 of score.py>",
    "runner_sh_sha256": "<sha256 of runner.sh>",
    "playbook_commit_sha": "<sha of PLAYBOOK.md if vendored locally; else null>"
  },

  "sut": {
    "agent_id": "agent_011CaaVZBRsEyuN4hXWMRR4Z",
    "agent_version": 1,
    "agent_name": "insignia_ingestion",
    "system_prompt_sha256": "<sha256 of the live system prompt fetched at trial time>",
    "tool_descriptions_sha256": "<sha256 of the agent's tools field, normalized JSON>",
    "skills_sha256": "<sha256 of the agent's skills field, normalized JSON>",
    "model": "claude-sonnet-4-6",
    "temperature": 1.0,
    "additional_config_sha256": "<sha256 of the full retrieved agent JSON>"
  },

  "environment": {
    "env_id": "env_01WaJyfTQu9YDfQC5vXiXWj5",
    "env_config_sha256": "<sha256 of the env's apt + pip + image config>"
  },

  "inputs": {
    "files": [
      { "file_id": "file_011CaaVTNcQEKbg4Dt1vCcCF", "filename": "...", "size_bytes": 1549255, "sha256": "<sha256 of file content if downloadable>" },
      { "file_id": "file_011CaaVTupcqW1ZuPvi63z1M", "filename": "...", "size_bytes": 27193741, "sha256": "..." }
    ]
  },

  "trials": {
    "paraphrases": ["v1_canonical", "v2_directive", "v3_terse", "v4_conversational"],
    "kickoff_shas": {
      "v1_canonical":     "<sha256>",
      "v2_directive":     "<sha256>",
      "v3_terse":         "<sha256>",
      "v4_conversational":"<sha256>"
    },
    "trials_per_paraphrase": 25,
    "seed": 42,
    "session_creation_strategy": "fresh_per_trial | reuse_idle"
  },

  "judge": {
    "model": null,
    "prompt_sha256": null,
    "alignment_metrics": null
  },

  "schedule": {
    "started_at": "2026-04-30T22:30:00Z",
    "ended_at":   "2026-04-30T23:45:00Z",
    "wall_seconds": 4500,
    "trials_completed": 100,
    "trials_failed_to_start": 0
  },

  "predictions": [
    {
      "id": "pred_001",
      "registered_at": "2026-04-30T22:25:00Z",
      "claim": "v2 ingestion prompt outperforms v1 by Δ ≥ 0.20 on outputs.* assertions",
      "metric": "outputs column mean pass-rate",
      "direction": "greater",
      "magnitude": 0.20,
      "verified": null
    }
  ]
}
```

## Why each field exists

| Field | Why required (which playbook entry) |
|---|---|
| `slice.expected_sha256`, `slice.spec_sha256` | Detect quiet ground-truth drift between runs. (§ 8 contamination decay; Chen EMNLP 2025) |
| `harness.foundation_commit_sha` | Replicate the harness state. (§ 9 OLMES + HAL) |
| `sut.system_prompt_sha256` | The single most important field — a prompt-byte change is the change you're trying to measure. (§ 9 OLMES) |
| `sut.tool_descriptions_sha256` | Tool names alone shift agent behavior substantially. (§ 9 PropensityBench Nov 2025) |
| `sut.model`, `sut.temperature` | Foundation-model swaps change everything. (§ 8 model-as-SUT framing) |
| `inputs.files[].sha256` | If the source PDF is re-uploaded with a tweak, every assertion's meaning shifts. |
| `trials.kickoff_shas` | Paraphrase identity must be byte-stable across runs. (§ 8 ReliableEval) |
| `trials.seed` | Where seeds are honored downstream (e.g. the agent's RNG), record. |
| `judge.*` | Even null is a recorded fact — "no judge in this slice" matters. (§ 9 Eval Factsheets) |
| `predictions[]` | Pre-register before running; verify after. (§ 9 decision observability — Lin et al.) |

## Sha256 contract

Every `*_sha256` is `sha256(<content as bytes>)` rendered lowercase hex. For JSON content, normalize via `json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()` before hashing — otherwise a key-order change produces a different hash and replays look "drifted."

## Schema versioning

`schema_version` is a SemVer integer. Breaking changes (renaming a field, removing one) bump it; additive changes (new optional field) do not. Scorer is required to handle the latest schema_version exactly; older versions raise a clear "manifest schema older than scorer expects" error rather than silently misinterpreting.

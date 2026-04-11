# Evaluator Agent Pattern

**Research date:** 2026-04-09
**Pattern family:** Output Quality & Governance
**Abstraction:** Artifact In → Criteria Check → Structured Feedback

---

## 1. Pattern Definition

An **evaluator agent** is a read-only agent that receives a completed artifact, applies a
structured set of criteria or a rubric to it, and emits structured feedback without mutating
the artifact or any external state.

The core loop is:

```
artifact (read) → criteria (loaded from config / rubric store) → verdict (structured output)
```

Key distinguishing properties vs. other agent patterns:

| Property | Evaluator | Executor / Transformer |
|---|---|---|
| Artifact mutation | Never | Core purpose |
| Tool permissions | Read-only | Read + write |
| Output | Verdict + rationale | Modified artifact / side-effect |
| Human escalation trigger | Score below threshold or contested finding | Unrecoverable error |
| Idempotency | Always idempotent | May not be |

Concrete instances of the pattern (all verified in research):

- **AI code review agent** — evaluates a code diff against correctness, security, style criteria
- **Compliance checker** — evaluates infrastructure configs or policy docs against SOC 2, HIPAA, GDPR controls
- **CI/CD quality gate** — evaluates a PR or build artifact against numeric thresholds; blocks merge on failure
- **Rubric-based grader** — evaluates open-ended text/code against a weighted scoring rubric
- **Document reviewer** — evaluates contracts, RFPs, and technical specs against a structured criteria set

---

## 2. Common Artifact Types Evaluated

| Artifact | Format | Typical Evaluator Variant |
|---|---|---|
| Code diff / PR | Git patch + codebase context | Code review agent |
| Infrastructure config | YAML / Terraform / JSON | Compliance checker |
| Policy document | PDF / Markdown | Compliance checker |
| LLM output / agent response | Plain text | Rubric grader / LLM-as-judge |
| Contract / legal document | PDF / DOCX | Document reviewer |
| RFP submission | PDF / DOCX multi-vendor | Technical evaluation agent |
| Test result bundle | JUnit XML / JSON | CI quality gate |
| Student submission / essay | Text | Rubric-based auto-grader |
| Security scan result | SARIF / JSON | Security gate |
| Vendor proposal | Structured PDF | Procurement evaluation agent |

Artifacts are almost always **read from a source** (git, object storage, document repository,
CI artifact store). The evaluator agent should never write back to these sources except to
post a review comment or score record.

---

## 3. Common Criteria / Rubric Structures

### 3a. Checklist (pass/fail per item)

Each criterion is a boolean: the artifact either satisfies it or does not. Common in compliance
and quality-gate contexts.

```
Required: New API endpoints have corresponding integration tests        [PASS / FAIL]
Required: Database migrations are backward-compatible                   [PASS / FAIL]
Required: Error messages do not leak internal details                   [PASS / FAIL]
```

Used by: CI quality gates, compliance checkers, RFP requirement validators.

### 3b. Severity-ranked finding list

Findings are classified by impact level rather than a numeric score. Common in code review.

Claude Code Review uses a three-color system:
- **Red (Normal)** — bug that should be fixed before merging
- **Yellow (Nit)** — minor issue, not blocking
- **Purple (Pre-existing)** — existing bug not introduced by this PR

Other common severity tiers: Critical / High / Medium / Low / Informational.

### 3c. Weighted scoring matrix (analytic rubric)

Each criterion carries a weight and produces a sub-score. The weighted sum produces a
composite score. Common in grading and procurement evaluation.

```python
rubric = [
    {"criterion": "Correctness",   "weight": 0.4, "scale": "0.0–1.0"},
    {"criterion": "Completeness",  "weight": 0.3, "scale": "0.0–1.0"},
    {"criterion": "Clarity",       "weight": 0.2, "scale": "0.0–1.0"},
    {"criterion": "Conciseness",   "weight": 0.1, "scale": "0.0–1.0"},
]
```

Key design principle from AutoRubric research: **analytic rubrics outperform holistic rubrics**
because per-criterion evaluation prevents "criterion conflation" and "halo effects" — a high
score on one dimension should not inflate adjacent scores.

Negative-weight criteria (penalizing for specific failures) are also supported and useful for
compliance contexts (e.g., weight: -10 for "Contains PII in log output").

### 3d. Threshold-gated numeric score

A single composite score compared against a pass threshold. Common in CI pipelines.

```yaml
gate:
  min_score: 70           # composite 0–100
  max_complexity: 15      # cyclomatic complexity
  min_coverage: 80        # test coverage %
  max_drop: 5             # max coverage drop vs. base branch
```

Used by: CodeAnt AI, agentkit-cli, Datadog PR Gates, EvalGate.

### 3e. Control-mapped compliance score

Each finding maps to a specific regulatory control (e.g., SOC 2 CC6.1, HIPAA §164.312).
Score is reported per control area plus an overall readiness percentage.

```
Overall Compliance: 84%
Controls Verified:  61 passed / 70 total
Gaps Identified:    3 critical / 4 medium / 2 low
```

Used by: HIPAA Agent (10-category scoring, A–F grading), DuploCloud compliance agents,
CODITECT compliance checker.

### 3f. Comparative / pairwise scoring

The evaluator compares two or more artifacts against each other using the same rubric.
Common in procurement (vendor A vs. vendor B on the same RFP requirement set).

---

## 4. Common Output Formats

### 4a. Structured JSON verdict

The most composable output format. Downstream agents or orchestrators can act on it
programmatically.

```json
{
  "verdict": "FAIL",
  "composite_score": 0.72,
  "threshold": 0.80,
  "findings": [
    {
      "criterion": "Correctness",
      "score": 0.6,
      "passed": false,
      "rationale": "The handler does not check for nil pointer before dereferencing at line 47.",
      "severity": "critical",
      "location": {"file": "handler.go", "line": 47}
    }
  ],
  "summary": "1 critical finding requires remediation before merge."
}
```

Letta rubric graders, AutoRubric, and Langfuse score records all follow this pattern: a
`score` float, a `rationale` string, and optionally per-criterion breakdowns.

### 4b. Annotated inline feedback (PR / document comments)

Findings posted as line-level or section-level annotations within the artifact's hosting
system (GitHub inline comments, Google Docs suggestions, contract clause annotations).
Claude Code Review posts one high-signal overview comment + per-line inline comments.

### 4c. Gap analysis report (Markdown / PDF)

Structured report for compliance and procurement contexts. Common sections:

```markdown
# Compliance Gap Analysis Report
## Executive Summary
- Framework: SOC 2 Type II
- Overall Compliance: 84%
- Critical gaps: 3

## Detailed Findings
### CC6.1 — Logical Access Controls
**Status:** Non-Compliant
**Current state:** MFA not enforced for privileged accounts.
**Required evidence:** Access review report, MFA configuration screenshot.
**Remediation:** Enforce MFA in IdP within 30 days.
```

### 4d. Scorecard (procurement / grading)

A table comparing multiple artifacts or vendors across the same criteria set, with weights
and total scores. Common in RFP evaluation and educational auto-grading.

### 4e. Pass/fail CI status check

Binary signal posted to a CI system (GitHub status check, GitLab pipeline step). Optionally
blocks merge on failure. The actual detail is in a companion PR comment or artifact.

---

## 5. Architecture Patterns

### 5a. Single-agent, single-pass

One agent receives the artifact + criteria, produces the verdict in one call. Simpler,
cheaper, lower latency. Anthropic's own research found that a single LLM call with a
well-structured rubric is "the most consistent and aligned with human judgements" for many
evaluation tasks — better than deploying multiple specialized judges in some domains.

Best for: rubric-based grading, compliance checks, document review of moderate complexity.

### 5b. Multi-agent parallel (fan-out + merge)

Multiple specialized sub-agents evaluate different dimensions or sections of the artifact
simultaneously. A merge/deduplication agent combines findings and ranks them.

Claude Code Review uses this pattern: parallel agents target different issue classes (logic
errors, security, edge cases, regressions), then a cross-verification layer filters false
positives, and an overview agent produces the final ranked output. This yields a sub-1%
false-positive rate at the cost of $15–25 per review.

Best for: large, complex artifacts (1,000+ line PRs, multi-section compliance audits) where
depth matters more than cost.

```
artifact
  ├── Bug-Detection Agent     → findings_A
  ├── Security Agent          → findings_B
  ├── Regression Agent        → findings_C
  └── Edge-Case Agent         → findings_D
         ↓
    Verification Agent (cross-checks)
         ↓
    Overview Agent (deduplicates, ranks, summarizes)
         ↓
    Structured Output
```

### 5c. Tiered / layered gates

Fast deterministic checks run first (linting, schema validation, exact-match assertions);
slow LLM-based evaluation runs only if deterministic gates pass. Reduces cost and latency.

```
Layer 1: Static/deterministic (< 30s)  — linting, schema, format
Layer 2: Pattern/context matching       — architecture rule checks
Layer 3: LLM deep analysis             — logic, security, completeness
Layer 4: Notify + post results
```

Used by CodeIntelligently's SCAN pipeline and FutureAGI's CI eval pipeline.

### 5d. Evaluator in a feedback loop (self-refine)

The evaluator agent's output is fed back to the generator agent as correction signals.
The generator revises and resubmits until the evaluator's score exceeds a threshold or
a retry limit is hit. Spring AI's `SelfRefineEvaluationAdvisor` implements this pattern.

Best for: automated improvement loops, not direct human-facing review.

---

## 6. Read-Only Tool Configuration

**Evaluator agents must be configured read-only by default.** This is the most important
invariant of the pattern. An evaluator that can mutate artifacts conflates evaluation with
remediation and loses the pattern's core guarantee: that the verdict reflects the artifact
as submitted.

### Permitted tools (read-only)

| Tool category | Examples | Purpose |
|---|---|---|
| File / blob read | `read_file`, `get_object`, S3 GetObject | Read the artifact |
| Code search / grep | `grep_codebase`, `semantic_search` | Understand context |
| Git read | `git_diff`, `git_log`, `git_show` | Inspect history |
| Document fetch | `fetch_url`, `get_document` | Read referenced standards |
| Rubric / criteria load | `get_rubric`, `get_policy` | Load evaluation criteria |
| Registry / schema read | `get_schema`, `describe_table` | Validate structure |
| Clock / metadata | `get_timestamp`, `get_pr_metadata` | Contextual information |
| Post-result write | `post_comment`, `create_review`, `write_score_record` | Emit verdict only |

Note: posting the verdict (comment, score record, CI status) is a permitted write, but it
writes to the **result channel**, not back to the artifact being evaluated.

### Prohibited tools (write/exec)

- File write / delete on the artifact or its dependencies
- Code execution / test runner (evaluators reason about code, not run it)
- Database mutation
- Infrastructure provisioning or configuration
- Any tool that would alter the artifact under evaluation mid-review

### Read-only enforcement in practice

For Claude Managed Agents, configure the evaluator session with:

```json
{
  "permissions": {
    "allow_bash_execution": false,
    "allow_file_write": false,
    "allow_network_write": false,
    "allowed_tools": [
      "read_file", "grep_codebase", "git_diff", "fetch_url",
      "get_rubric", "post_review_comment", "write_score_record"
    ]
  }
}
```

---

## 7. Human-in-the-Loop for Evaluation Disputes

Research consistently shows that LLM judges achieve ~80–85% agreement with human
reviewers; the remaining 15–20% represents cases where human judgment is required.

### Recommended HITL escalation triggers

1. **Score near the pass/fail threshold** — e.g., composite score between 0.75 and 0.85
   when the threshold is 0.80. Uncertainty in this band warrants human review.
2. **Low judge confidence** — the agent expresses uncertainty or emits a `CANNOT_ASSESS`
   verdict on a specific criterion.
3. **Contested finding** — a developer disputes a finding; route to human reviewer rather
   than re-running the same judge.
4. **Novel artifact type** — the rubric was not calibrated against this category of artifact.
5. **High-stakes decision** — blocking a production release, failing a compliance audit,
   rejecting a vendor in a procurement.
6. **Systematic disagreement pattern** — the judge consistently disagrees with human
   corrections on a specific criterion type, signaling rubric drift.

### HITL patterns observed in production systems

- **Spot-check sampling** — a fixed % of passing evaluations reviewed by humans to detect
  silent judge degradation (Anthropic's internal research recommendation).
- **Disagreement resolution queue** — contested findings from developers route to a named
  human reviewer; decision recorded for rubric calibration.
- **Alignment feedback loop (LangSmith Align Evals pattern)** — human corrections collected
  on evaluator scores → used as few-shot examples → judge re-calibrated → agreement
  tracked over time with Cohen's kappa.
- **Expert escalation tier** — three-tier stack: (1) deterministic checks, (2) LLM judge,
  (3) human expert for high-stakes or ambiguous cases (Braintrust, Maxim AI recommendation).
- **Final-approval gate** — evaluator can find and rank issues but cannot approve; a human
  must approve. Claude Code Review explicitly does not approve PRs — that remains a human
  call.

---

## 8. Recommended Default Configuration for the Orchestrator

```yaml
agent_pattern: evaluator

# Model selection
model: claude-opus-4-5          # Prefer highest-capability model; evaluation quality >>>> cost
temperature: 0                  # Determinism is essential for reproducibility
structured_output: true         # Always emit JSON verdict schema

# Tools — read-only by default
tools:
  - read_file
  - grep_codebase
  - git_diff
  - fetch_url
  - get_rubric
  - post_review_comment         # write to result channel only
  - write_score_record          # write to result channel only

permissions:
  allow_bash_execution: false
  allow_file_write: false
  allow_network_write: false

# Rubric configuration
rubric:
  type: analytic                 # analytic > holistic (per-criterion evaluation)
  criterion_types:               # mix of binary and ordinal
    - binary                     # MET / UNMET — highest inter-rater reliability
    - ordinal                    # Likert scales for gradations
  negative_criteria: supported   # allow penalty criteria
  weighting: required            # each criterion must have a weight

# Output schema (required fields)
output_schema:
  verdict: enum[PASS, FAIL, ESCALATE]
  composite_score: float         # 0.0–1.0
  threshold: float               # the configured pass threshold
  findings:
    - criterion: string
      score: float
      passed: boolean
      severity: enum[critical, high, medium, low, nit, informational]
      rationale: string
      location: optional         # file + line for code artifacts
  summary: string
  escalate_reason: optional      # present when verdict == ESCALATE

# Human-in-the-loop
hitl:
  auto_escalate_when:
    - score_in_band: [threshold - 0.05, threshold + 0.05]
    - judge_confidence: low
    - finding_contested: true
    - artifact_type_novel: true
  spot_check_rate: 0.05          # 5% of passing evaluations reviewed by humans
  dispute_resolution: human_queue

# Multi-agent vs single-agent
architecture:
  default: single_agent          # single-pass is more consistent per research
  use_multi_agent_when:
    - artifact_size_lines: ">= 500"
    - artifact_sections: ">= 5"
    - depth_required: high

# Caching & idempotency
cache:
  enabled: true                  # same artifact + same rubric → same verdict (deterministic)
  cache_key: [artifact_hash, rubric_version]
```

---

## 9. Pattern-Specific Questions for the Orchestrator

The following questions need answers from the user when configuring an evaluator agent.
They map to the key variation points in the pattern.

### Artifact configuration

1. **What is the artifact?**
   What type (code diff, document, config, LLM output, RFP submission) and where is it stored?
   Is it a single file or a collection?

2. **How is the artifact delivered to the evaluator?**
   Pushed (e.g., webhook on PR open), pulled (e.g., polling an artifact store), or passed
   inline (e.g., piped from a generator agent)?

3. **What is the artifact's scope?**
   Just the changed portion (diff) or the full artifact in context? Full-codebase context
   significantly improves evaluation quality for code review.

### Criteria / rubric configuration

4. **Are the criteria pre-defined or does the evaluator derive them?**
   Pre-defined criteria produce more consistent, auditable evaluations. Derived criteria are
   more flexible but harder to calibrate.

5. **What is the rubric type?**
   Checklist (binary), severity-ranked, weighted scoring matrix, threshold-gated numeric,
   or compliance-control mapped?

6. **Are there mandatory (blocking) criteria vs. advisory criteria?**
   Which criteria must pass for the artifact to be accepted, vs. which are recommendations?

7. **How are the criteria versioned?**
   If the rubric changes, should historical evaluations be re-run? Is there a rubric registry?

8. **Is the rubric calibrated against human judgments?**
   Has the rubric been validated on a golden dataset? What is the current judge-human
   agreement rate (Cohen's kappa)?

### Output and downstream use

9. **Who or what consumes the verdict?**
   Human reviewer, CI system (merge blocker), another agent (self-refine loop), compliance
   dashboard, or audit log?

10. **What is the required output format?**
    JSON for machine consumption, Markdown/annotated comments for human review, or both?

11. **Should the evaluator post findings directly, or buffer them for approval first?**
    Direct posting is faster; buffered posting allows a human to review before publishing.

### Thresholds and escalation

12. **What is the pass threshold?**
    What composite score or finding configuration constitutes acceptance vs. rejection?

13. **Is the gate hard (blocks action) or soft (advisory)?**
    Hard gates block CI merge, deployment, or document approval. Soft gates surface findings
    without blocking.

14. **What triggers escalation to a human?**
    Score near threshold, contested finding, novel artifact type, high-stakes domain?

15. **Who handles disputed findings?**
    Is there a named review queue? What is the SLA for dispute resolution?

### Operational

16. **What is the acceptable latency for an evaluation?**
    Single-agent evaluations run in seconds to minutes; multi-agent evaluations can take
    20+ minutes. Does the downstream workflow block on the evaluation?

17. **What is the cost envelope?**
    Multi-agent deep reviews cost significantly more than single-pass. Is there a per-artifact
    budget?

18. **How often will the same artifact be evaluated?**
    On every push (high volume) or on merge only (lower volume)? This affects caching
    strategy.

19. **Does the evaluator need access to historical evaluations for trending?**
    Compliance posture over time, code quality regression tracking, and rubric calibration
    all benefit from historical score access (read-only).

20. **What is the audit and evidence retention requirement?**
    Compliance use cases often require immutable, timestamped evaluation records
    (e.g., blockchain-anchored audit trails for HIPAA).

---

## 10. Key Findings and Design Principles

Derived from research across code review, compliance checking, quality gates, rubric grading,
and document review:

1. **Read-only is the invariant.** The moment an evaluator can write to the artifact, it
   becomes a hybrid pattern (evaluator + transformer) with different risk properties.
   Configure `allow_file_write: false` at the session level, not just the prompt level.

2. **Analytic rubrics > holistic rubrics.** Per-criterion scoring prevents halo effects,
   makes it easier to identify which dimension failed, and produces more calibratable judges.

3. **Single-judge, well-structured rubric ≥ multi-judge ensemble** for many tasks.
   Anthropic's research found that a single LLM call with structured rubric output was more
   consistent than multiple specialized judges. Multi-agent parallelism adds value primarily
   for large, complex artifacts where specialization reduces each agent's cognitive load.

4. **Cross-verification is the key to low false-positive rates.** Claude Code Review achieves
   sub-1% false positives specifically because findings are checked against actual code
   behavior before posting. Without verification, single-pass reviews produce much higher
   noise.

5. **Temperature = 0 for reproducibility.** Evaluations must be deterministic to be auditable.
   Two evaluations of the same artifact with the same rubric must produce the same verdict.

6. **CANNOT_ASSESS is a valid verdict.** Explicit uncertainty handling (AutoRubric, Braintrust)
   is better than low-confidence guessing. Route CANNOT_ASSESS to human review.

7. **Human-in-the-loop is a calibration mechanism, not just a safety net.** The most
   sophisticated systems (LangSmith Align Evals, Microsoft Copilot Studio Kit) use human
   corrections to continuously improve the rubric and the judge, not just to catch individual
   errors.

8. **The evaluator never approves — it finds and ranks.** Even fully automated evaluators
   (Claude Code Review, CI quality gates) reserve the final approval decision for a human or
   a deterministic policy (e.g., "zero critical findings = auto-pass"), not the LLM itself.

9. **Severity ranking is required for actionable output.** An unranked list of findings is
   less actionable than a ranked list. Critical bugs first, nits last. Without ranking, human
   reviewers face the same triage work the evaluator should have done.

10. **Rubric calibration requires a golden dataset.** Before deploying an evaluator in a
    blocking gate, validate it against a set of human-labeled examples. Track Cohen's kappa
    over time. A rubric that was well-calibrated at launch will drift as the artifact domain
    evolves.

---

## Sources

- Anthropic Claude Code Review launch (March 2026): https://www.claude.com/blog/code-review
- Claude Code Review documentation: http://cc.bruniaux.com/guide/workflows/code-review/
- hamelsmu/claude-review-loop plugin: https://github.com/hamelsmu/claude-review-loop
- CodeIntelligently AI quality gate CI/CD: https://codeintelligently.com/blog/ai-code-quality-gate-ci-cd
- Developer Toolkit quality gates: https://developertoolkit.ai/en/shared-workflows/enterprise/code-quality/
- EvalGate open source: https://evalgate.aotp.ai/
- FutureAGI CI/CD eval pipeline: https://docs.futureagi.com/docs/cookbook/quickstart/cicd-eval-pipeline
- AI evaluation tools for CI/CD (Maxim AI): https://www.getmaxim.ai/articles/top-5-ai-evaluation-tools-for-running-ai-evals-in-your-ci-cd-pipeline-in-2025/
- HIPAA Agent compliance checker: https://hipaaagent.ai/docs
- DSALTA SOC2/HIPAA automation: https://www.dsalta.com/resources/articles/how-ai-automates-soc-2-and-hipaa-compliance-from-manual-spreadsheets-to-audit-ready-in-weeks
- CODITECT compliance checker agent: https://docs.coditect.ai/reference/agents/compliance-checker-agent
- Screenata compliance automation: https://github.com/Screenata/compliance-automation
- AutoRubric framework: https://autorubric.org/
- AutoRubric research paper (arxiv): https://arxiv.org/html/2603.00077v2
- RubricHub paper (arxiv): https://www.arxiv.org/pdf/2601.08430
- 8allocate rubric-based AI grading: https://8allocate.com/blog/how-to-build-rubric-based-ai-auto-grading-people-trust-and-adopt/
- Microsoft Copilot Studio Kit rubrics: https://learn.microsoft.com/en-ca/microsoft-copilot-studio/guidance/kit-rubrics-overview
- Letta rubric graders: https://docs.letta.com/pages/development-tools/evals/graders/rubric-graders
- Scale AI RFP Evaluation Assistant: https://scale.com/enterprise/prebuilt-applications/rfp-evaluation-assistant
- ProcBay Technical Evaluation Agent: https://procbay.com/ai-agent-technical-evaluation
- Innovation Labs AI in Legal / RFP: https://innovationlabs.net/contract-review.html
- LLM-as-judge vs HITL (Braintrust): https://www.braintrust.dev/articles/llm-as-a-judge-vs-human-in-the-loop-evals
- LLM-as-judge calibration (LangChain): https://www.langchain.com/articles/llm-as-a-judge
- Agent Patterns — LLM-as-Judge with spot-checking: https://agentpatterns.ai/workflows/llm-as-judge-evaluation/
- LLM-as-judge pattern (ReputAgent): https://reputagent.com/patterns/llm-as-judge-pattern
- Langfuse score data model: https://langfuse.com/docs/evaluation/evaluation-methods/data-model
- GRAFITE continuous benchmarking (arxiv): https://www.arxiv.org/pdf/2603.18173

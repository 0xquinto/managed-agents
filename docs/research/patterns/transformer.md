# Transformer Agent Pattern

> Research compiled 2026-04-09. Sources: Spotify Engineering Blog (Honk series), OpenSite AI large-scale-refactor skill, Augment Code, Aviator Agents, Datafold Migration Agent, Row Sherpa batch CSV processing, arxiv papers on LLM-based code transformation and validation.

---

## 1. Pattern Definition

The **Transformer** pattern abstracts the operation:

```
Input Corpus → [Agent applies Transformation Rule] → Output Corpus
```

A transformer agent receives a bounded set of artifacts (files, records, documents, configs), applies a consistent, describable modification rule across every member of the set, and produces a modified output corpus. The transformation rule is stated once — in natural language, a template, or a structured spec — and the agent applies it uniformly.

**Core invariant:** The rule does not change between items. What varies is only the artifact being transformed.

**Distinguishing characteristics vs. other patterns:**
- Unlike a **researcher** agent, a transformer writes, not reads.
- Unlike an **orchestrator**, the transformer itself executes the work (no sub-delegation per item).
- Unlike a one-shot code generator, the transformer processes *many* artifacts under the *same* rule.

**Concrete instances observed in production:**
| Instance | Input | Rule | Output |
|---|---|---|---|
| Spotify Fleetshift + Claude Code | Java source files using AutoValue | Migrate to Java Records + AutoMatter builders | Modernized Java source files |
| Spotify Honk | Scio pipeline files | Upgrade to latest Scio API | Updated pipeline source |
| Spotify Honk | YAML/JSON configs | Update parameters while preserving schema/format | Updated config files |
| Backstage component migration | TypeScript UI components | Move to new Backstage frontend system | Migrated component files |
| AI-assisted Spring Boot migration | Spring Boot 2.x + Java 8 source | Upgrade to Spring Boot 3.x + Java 17, javax→jakarta | Modernized microservice source |
| Datafold Migration Agent | SQL codebase (Snowflake/BigQuery/etc.) | Translate to target SQL dialect, convert stored procs to dbt | Migrated SQL + dbt project |
| Batch CSV classifier | CSV with N rows | Apply classification prompt to each row | CSV with added classification column |
| Rename refactoring | TypeScript monorepo | Rename symbol A → B across all files | Updated codebase |

---

## 2. Common Transformation Types

### 2.1 Code Migration (Language / Framework / API)

**Inputs:** Source files in the original language/framework version (git repo mount or file list)
**Rule description:** Natural language migration spec, often with before/after code examples embedded in the prompt. Spotify's AutoValue→Records prompt is ~500 words with multiple annotated Java examples.
**Key pattern:** The rule must encode *preconditions* ("only attempt if the repo uses Java 17+") and *out-of-scope guards* ("do not touch unrelated code").
**Observed at:** Spotify (Java Records, Scio, Backstage), AI-assisted Spring Boot migration demo, Uber NullAway, Aviator Agents.

**Transformation sub-types:**
- Language modernization: value types → records, callbacks → promises, `javax.*` → `jakarta.*`
- Framework version upgrade: Spring Boot 2→3, Scio version bumps
- API deprecation: replace deprecated method calls across all call sites
- Namespace/import migration: coordinate renames that cascade through import graphs
- Build file sync: update `BUILD.bazel`, `pom.xml`, `package.json` to match source changes

### 2.2 Codebase-Wide Rename / Pattern Replacement

**Inputs:** All files matching a glob or language filter within a repository
**Rule description:** Symbol mapping ("rename `UserData` → `UserProfile`") plus negative constraints ("do NOT rename string literals, do NOT touch `src/api/v1/types.ts`")
**Key pattern:** Negative constraints are as important as the positive rule. Without them, agents treat "rename everywhere" literally and corrupt API contracts, DB column names, or generated files.
**Observed at:** Cursor Composer Agent mode, Windsurf Cascade Agent, multi-agent coordinated rename (arXiv 2601.00482), Claude Code fan-out patterns.

**Scope strategies:**
- Low-risk (type renames, import fixes): up to 200 files per session
- Medium-risk (logic-adjacent changes): up to 50 files, review every 25
- High-risk (framework migrations, API changes): up to 20 files, review every 10
- Pilot batch first regardless of risk level: 10–20 files to surface edge cases before full rollout

### 2.3 Data Format Conversion

**Inputs:** Structured data files (CSV, JSON, XML, YAML, Parquet, fixed-width, EDI)
**Rule description:** Schema mapping — either visual drag-and-drop (NE2NE, Vern Curator) or a natural language prompt template with `{{variable}}` placeholders (BatchForge, Row Sherpa)
**Key pattern:** Split ingestion from processing. Upload the data, create a job, then process in background with concurrency caps and retries. Do not "upload + process" in one synchronous request.
**Observed at:** BatchForge (CSV/JSON batch LLM processing), Row Sherpa (CSV classification), Vern (B2B data migration), NE2NE (36-path no-code conversion), Datafold DMA (SQL dialect translation).

**Chunking heuristics:**
- 25–100 rows/chunk for web-enriched or complex classification
- 100–500 rows/chunk for pure field classification
- Smaller chunks → faster partial results + cheaper retries
- Concurrent chunks: 3–10 depending on API quota

### 2.4 Configuration and Document Batch Transformation

**Inputs:** Config files (YAML, JSON, TOML, HCL), documents, schema definitions
**Rule description:** "Update parameter X to value Y while preserving schema and formatting conventions"
**Key pattern:** Config transformations require schema awareness — the agent must not produce output that violates the target schema even if the literal rule is satisfied.
**Observed at:** Spotify Honk config updates, Atlas schema-as-code migrations, Liquibase/Alembic schema migrations.

### 2.5 Schema / Database Migrations

**Inputs:** SQL schema files, ORM models, migration scripts
**Rule description:** Source dialect → target dialect, or model version → next model version
**Key pattern:** Correctness validation requires data-level diffing (row counts, column distributions, sample row comparisons), not just compilation. Datafold DMA validates at dataset, column, and row levels.
**Observed at:** Datafold DMA, AWS DMS + Bedrock, Atlas, Alembic + AI review, Bytebase.

---

## 3. Scope and Safety Controls

### 3.1 File Scope Controls

**Allowlist approach** (OpenSite AI large-scale-refactor skill): Generate an explicit allowlist of in-scope files before the agent begins. Files not on the list are protected. A separate `generate_allowlist.py` script or similar pre-step produces this from the task spec.

**Protected path declarations** (Windsurf Cascade, Cursor Composer): Prompt must explicitly name files/directories the agent must not touch, e.g., `"Do NOT change: src/db/schema.ts, src/api/v1/types.ts, *.gen.ts"`.

**Drift detection** (OpenSite AI): A "Substitution Test" checks whether each proposed change is a direct substitution of the stated rule or introduces novel logic. If a change introduces more than ~50 lines of net-new logic, the agent stops and requests review.

**Context path narrowing** (Windsurf `cascade.config`, Claude Code `CLAUDE.md`): Restrict which directories the agent indexes and considers. Without this, agents on large monorepos attempt to touch the whole codebase.

### 3.2 Batch / Session Size Controls

| Risk Level | Max Files/Session | Review Cadence |
|---|---|---|
| Low (type renames, import fixes) | 200 | End of session |
| Medium (logic-adjacent refactors) | 50 | Every 25 files |
| High (framework migrations, API changes) | 20 | Every 10 files |

**Turn limits:** Spotify's homegrown loop capped at 10 turns per session, 3 session retries total before surfacing the failure to a human.

**Pilot batch:** Always process 10–20 files first (regardless of risk level) to surface edge cases in the rule before fleet-wide application.

### 3.3 Scope Creep Prevention

The most common failure mode observed across all sources: agents "going rogue" — refactoring code unrelated to the stated rule, disabling flaky tests to make the build pass, reorganizing folder structures, installing dependencies not requested.

**Controls:**
- Explicit preconditions in the prompt ("only attempt if repo uses Java 17+")
- Out-of-scope guards in the prompt ("do not modify files unrelated to the migration")
- LLM-as-judge post-hoc evaluation of the diff against the original prompt (Spotify: ~25% of sessions rejected by the judge)
- Diff budget limits (stop if changed file count exceeds threshold)
- Scope allowlist enforced at the file access layer, not just the prompt

### 3.4 Protected Paths Pattern

```
Scope:
  include:
    - src/services/**/*.ts
    - src/routes/**/*.ts
    - tests/**/*.test.ts
  exclude:
    - src/db/schema.ts          # DB column names - do not rename
    - src/api/v1/types.ts       # External API contract - frozen
    - "**/*.gen.ts"             # Generated files - hands off
    - src/vendor/**
```

---

## 4. Validation Strategies

Validation is the highest-leverage investment for transformer agents. Without it, errors compound silently across the corpus.

### 4.1 Deterministic Verifiers (Inner Loop)

Run automatically after every file or batch:
- **Syntax / parse check:** Does the output parse correctly in the target language/format?
- **Compilation / type check:** `tsc --noEmit`, `javac`, `go build`, etc.
- **Linter / formatter:** `eslint`, `spotless`, `gofmt` — ensures the agent hasn't drifted from style conventions
- **Unit tests:** Run the existing test suite. Failed tests are fed back to the agent as error context for self-correction.

Spotify's `verify` tool bundles formatter + linter + test runner into a single agent-callable tool. The agent can invoke it mid-session and incorporate the output before finalizing the diff.

**Key design:** Verifiers parse complex test output and extract only the relevant error messages before feeding back to the agent. Raw test output is often too noisy.

### 4.2 LLM-as-Judge (Outer Loop)

After all deterministic verifiers pass, an LLM judge evaluates the diff against the original prompt:

```
Judge receives: (original_prompt, produced_diff)
Judge answers: Did the agent do only what was asked? Did it stay in scope?
              Were there any suspicious changes (disabled tests, unrelated refactors)?
```

**Spotify results:** Judge rejects ~25% of sessions. Of those, ~50% self-correct successfully after the rejection. Most common trigger: agent straying beyond instruction scope.

**Important limitation:** Spotify admits they have not yet invested in formal evaluations (evals) of the judge itself. The judge is deployed pragmatically — it provides measurable value even without formal validation of the judge's accuracy.

### 4.3 Data-Level Diffing (for data format transformations)

For schema migrations and data format conversions, syntactic and compilation checks are insufficient. Required:
- Row count parity between source and target
- Column distribution comparison (null rates, value ranges, cardinalities)
- Sample row-level comparison at dataset, column, and row levels
- Datafold DMA provides a comprehensive parity report linking data diffs at all three levels

### 4.4 Git-Based Diff Review

- Every transformer session operates on a clean git branch
- The diff is the reviewable artifact — agents propose changes, humans review diffs before merge
- Automated PR creation with generated description of what was changed and why
- GitHub/GitLab CI checks run as a "complementary outer loop" to the agent's inner verification loop

### 4.5 Regression / Rollback Strategy

**Auto-rollback on test failure:** Git-aware tooling can revert files or state if tests fail or errors exceed thresholds. The Replit incident (AI wiped production data) is cited across multiple sources as the canonical warning for systems lacking this.

**Write/delete staging:** High-risk changes (deletes, schema drops) require explicit approval before execution, even if the agent generates them correctly.

**Commit granularity:** Atomic subtask commits rather than one mega-commit for the whole corpus. This enables partial rollback to the last known-good state mid-migration.

**Session handoff:** For migrations spanning multiple sessions, a handoff file records which files have been processed, their status (success/skipped/failed), and any edge cases encountered. The next session picks up without reprocessing completed files.

### 4.6 Validation Stack Summary

```
Level 1 (per file, synchronous):   syntax check, type check
Level 2 (per batch, synchronous):  linter, formatter, unit tests
Level 3 (per session, async):      LLM-as-judge evaluates diff vs. prompt
Level 4 (per PR, CI):              full test suite, security scan, PR review
Level 5 (for data transforms):     row-count parity, column diff, sample rows
```

---

## 5. File Handling Patterns

### 5.1 Git Repo Mount

For code transformations: mount the git repository inside a sandboxed container. The agent reads files directly, makes changes in-place, and the host system runs formatters, builds, and tests using the local toolchain. Spotify runs agents in GKE containers with:
- Limited file system permissions
- Scoped bash (only specific allowed commands)
- Git tool for standardized commit/branch operations
- Verify tool for format + lint + test

### 5.2 File List Scoping

The orchestrator provides the agent with an explicit list of files in scope. The agent does not discover scope on its own. This is the primary mechanism preventing scope creep in Spotify's system. The file list is generated by the Fleet Management system from metadata in Backstage (ownership, dependency graph, component catalog).

### 5.3 Batch File Processing (Data)

For data format transformations:
1. `POST /jobs` → returns `job_id` + `upload_url`
2. Upload file to `upload_url` (separate from processing)
3. `POST /jobs/{id}/start` → server validates, splits into chunks, enqueues
4. Process chunks in background with concurrency cap (3–10 parallel)
5. Stream partial results as they arrive
6. Download merged output on completion

Skip logic: track completed files/chunks so interrupted jobs can resume without reprocessing.

### 5.4 Context Window Management

For large corpora:
- Process 20–40 files reliably per session; beyond that, split into phases
- Commit after each phase to preserve progress
- Use `CLAUDE.md` or equivalent persistent plan file to carry context across sessions
- For mechanical parts (simple renames), use headless/fan-out mode; save interactive sessions for complex reasoning

---

## 6. Model Selection Rationale

| Task | Recommended Model | Rationale |
|---|---|---|
| Complex framework migration (Spring Boot, Java Records) | Sonnet or Opus | Multi-file reasoning, understanding dependency graphs, handling edge cases in the rule |
| Simple mechanical transforms (rename, import fix, format) | Haiku or Sonnet | Pattern is fully specified; model needs execution, not reasoning |
| Config/YAML parameter updates | Haiku or Sonnet | Low reasoning complexity; schema awareness from context |
| LLM-as-judge evaluation | Sonnet | Evaluating diffs for scope adherence is a mid-complexity reasoning task |
| Pilot batch (first 10–20 files) | Sonnet or Opus | Surface edge cases; quality matters more than cost at this stage |
| Full fleet rollout (post-pilot) | Sonnet or Haiku | Rule is validated; optimize for throughput and cost |
| Orchestrator planning phase | Opus | Architectural decisions about chunking strategy, protected paths, rule formulation |

**Spotify's approach:** Claude Code (Sonnet-class model) as the top-performing agent across ~50 migrations. The model is not cited as the differentiating factor — the verification loop, context engineering, and prompt quality are.

**Cost optimization pattern (two-pass):**
- Pass 1: Sonnet drafts the transformation
- Pass 2: Opus reviews only when Sonnet's output fails validation or quality checks
- Result: 60–80% cost reduction in CI pipelines vs. Opus-for-everything

**Three-tier model strategy:**
- Haiku: high-volume, purely mechanical transforms (adding TypeScript types to 50 utility functions: ~$0.50 vs $3 with Sonnet)
- Sonnet: default for most transformer workloads (multi-file context, moderate reasoning)
- Opus: architectural decisions about the rule itself, novel edge cases, security-sensitive transforms

---

## 7. Error Recovery

### 7.1 Partial Completion

Track per-file/per-chunk status in a job manifest:
```
file: src/services/user.ts      status: complete  commit: abc123
file: src/services/payment.ts   status: failed    error: "Cannot use records with @Memoized"
file: src/services/auth.ts      status: skipped   reason: "Java 11 repo, records unavailable"
```

Failed files surface to a human queue for manual handling. Skipped files are expected and documented.

### 7.2 Precondition Failures

Agents must state preconditions explicitly and check them before acting. Spotify's lesson: an agent reusing a migration prompt across hundreds of repos will encounter repos where the migration is impossible (wrong Java version, different framework). The agent should detect this and exit cleanly rather than attempting the impossible and producing broken output.

**Precondition pattern:**
```
Before attempting the migration, verify:
1. The repository uses Java 17 or higher (check pom.xml or build.gradle)
2. AutoValue is present as a dependency
3. The build system is Bazel or Maven (not Gradle)
If any precondition fails, output a single line explaining which precondition failed and stop.
```

### 7.3 Rollback Triggers

- Test suite regresses: auto-revert the batch, log which files caused failures
- Judge veto: agent attempts self-correction (up to N retries), then surfaces to human
- Turn limit exceeded: commit progress so far, hand off to next session
- Diff budget exceeded: stop, request human review before continuing

### 7.4 Context Degradation

For long-running sessions, agent context degrades — it forgets earlier changes when working on later files. Mitigations:
- Context flush protocol: commit and start a fresh session after N files
- Session handoff document: written at end of each session, read at start of next
- Persist the transformation rule in a versioned prompt file (not embedded in conversation)

---

## 8. Recommended Default Configuration

```yaml
pattern: transformer

# Scope
scope:
  include_globs:
    - "src/**/*.ts"
    - "tests/**/*.test.ts"
  exclude_globs:
    - "**/*.gen.ts"
    - "src/vendor/**"
    - "src/api/v1/types.ts"   # example: frozen external contract
  max_files_per_session: 50   # medium-risk default
  pilot_batch_size: 15        # always run pilot first

# Transformation
transformation:
  rule_file: ".claude/migration-rule.md"  # versioned, not inline
  preconditions_check: true
  one_change_per_session: true            # do not combine multiple rules

# Model
model:
  pilot_phase: claude-sonnet-4-6
  fleet_phase: claude-sonnet-4-6         # escalate to opus only for novel edge cases
  judge: claude-sonnet-4-6

# Validation (inner loop)
validation:
  run_formatter: true
  run_linter: true
  run_tests: true
  max_turns_per_file: 10
  max_session_retries: 3
  llm_judge: true                         # outer loop after deterministic checks pass

# Git / file handling
git:
  branch_prefix: "transform/"
  atomic_commits: true                    # one commit per file or small batch
  pr_auto_create: true
  require_green_ci: true

# Error recovery
recovery:
  on_precondition_fail: skip_and_log
  on_test_regression: revert_batch
  on_judge_veto: retry_then_human         # retry up to 2x, then queue for human
  on_turn_limit: commit_progress_and_handoff
  track_job_manifest: true               # resume interrupted jobs without reprocessing

# Batch processing (data transforms only)
batch:
  chunk_size_rows: 100                   # adjust based on row complexity
  concurrent_chunks: 5
  retry_on_failure: 2
  output_schema_validation: true
```

---

## 9. Pattern-Specific Questions

These are the questions an orchestrator should ask the user (or resolve from context) before launching a transformer agent session:

### Rule Definition
1. What is the transformation rule? Can it be stated as a before/after example pair?
2. Are there preconditions that determine whether the rule applies to a given file/record?
3. What should the agent do when it encounters a file where the precondition fails — skip silently, skip with log, or abort the session?
4. Are there known edge cases in the rule (e.g., the `@Memoized` + Records incompatibility in the AutoValue migration)?

### Scope
5. Which files/directories are in scope? Which are explicitly protected?
6. Are there protected symbols, column names, or API contracts that must not be renamed even if they match the pattern?
7. What is the estimated file count? Should we run a pilot batch first?
8. Is this a one-repo operation or a fleet-wide migration across many repositories?

### Validation
9. Does the repository have a test suite? Is it reliable enough to use as the primary correctness signal?
10. Should we use an LLM judge on the diff, or is deterministic verification sufficient?
11. For data transforms: do we have a sample of the expected output to validate against?

### Recovery
12. What should happen if a file fails validation after N retries — skip and log, halt, or queue for human review?
13. Is rollback required to be automatic, or is manual git revert acceptable?
14. For fleet-wide migrations: how do we track which repositories have been processed?

### Model and Cost
15. Is this a mechanical transform (Haiku/Sonnet) or does it require deep multi-file reasoning (Sonnet/Opus)?
16. What is the cost budget for this transformation run?
17. Should we use a two-pass strategy (Sonnet drafts, Opus reviews failures only)?

---

## Key Sources

- Spotify Engineering Blog — Honk series (Parts 1, 2, 3): fleet-wide refactoring, context engineering, verification loops (2025-11)
- Spotify Fleet Management Part 3 — fleet-wide refactoring infrastructure (2023-05)
- AutoValue to Records migration prompt gist — mbruggmann (2025-10): full example production prompt
- OpenSite AI large-scale-refactor skill — scope controls, drift detection, risk-tiered file budgets (2026-03)
- Datafold Migration Agent docs — SQL codebase translation with LLM feedback loop and data parity validation
- Row Sherpa guide — batch CSV + LLM processing architecture: jobs, chunks, streaming, retries
- arXiv 2601.00482 — Multi-Agent Coordinated Rename Refactoring: scope inference agent, planned execution agent, replication agent
- AgentMastered model selection guide — Opus vs Sonnet cost matrix for refactoring tasks
- AI-assisted Java + Spring Boot migration (rmadabusiml) — 8-phase migration with specialized subagents

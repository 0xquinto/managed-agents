# Actor-prompt schema

Required structure for every actor-style managed-agent system prompt
(prompts that drive an agent's runtime behavior, as opposed to expert
prompts in `.claude/agents/*-expert.md` which are documentation for the
orchestrator).

## Why a schema

Lint catches *known* failure modes (R001–R005). The schema catches
*structural* gaps — sections an actor prompt forgot to include. A prompt
without an `Output` section will produce free-form responses that break
strict downstream parsers; a prompt without a `Rules` section gives the
model no guardrails. These omissions wouldn't trip any content-based rule
but they're as load-bearing as the wrong mount path.

## Required sections (in order)

| Section | Purpose | Required |
|---|---|---|
| Opening sentence | "You are the `<role>` agent for ..." establishes role + scope | yes |
| `## Inputs you receive` | Names every field the agent reads from the user message | yes |
| `## Your job` | Numbered steps describing what the agent does | yes |
| `## Output` (or `## Output (returned to coordinator)`) | Declares the exact JSON envelope the agent must return, with a no-prose / no-fences clause | yes |
| `## Rules` | Hard constraints (paths it must not write, things it must not guess, etc.) | yes |
| `## Identity discipline` | One-paragraph reminder of what the agent is NOT (prevents scope creep) | recommended |
| Trailing `Tools:` line | Lists the bash/read/write/edit tools and skills the agent has | recommended |

## Required clauses inside the `Output` section

The Output section MUST contain ALL of:

- A fenced JSON block showing the envelope shape
- The literal phrase **"no surrounding prose, no markdown code fences"** (or equivalent — see `R005`)
- The status discriminant if the envelope has one (e.g. `"status": "ok" | "blocked" | "failed"`)

## Required clauses inside `Rules` (when applicable)

Only required IF the prompt drives bash file extraction:

- A `/mnt/session/uploads/` mount-path note (R001)
- A `/tmp/<contract_id>/` persistence note (R004) explaining bash is stateless
- A "do NOT copy outputs to `/mnt/session/outputs/`" note IF the prompt has a custom out dir (R003)

## Reference template

```markdown
You are the `<role>` agent for the `<pipeline>` pipeline. <one-sentence scope>.

## Inputs you receive

- `<field>` — <description>
- ...

## Your job

1. **<verb>.** <step description>
2. ...

## Output (returned to coordinator)

```json
{ "status": "ok" | "blocked" | "failed", ... }
```

Your final response MUST be a single JSON object matching the envelope above —
no surrounding prose, no markdown code fences.

## Rules

- <constraint>
- ...

## Identity discipline

You are <X>, not <Y>. <one-paragraph guardrail>.

Tools: `bash`, `read`, `write`, `edit` + `<skill>`, `<skill>` skills.
```

## Compliance

Lint rule `R006` checks every actor prompt for the required-section list.
Severity starts as `warn` so existing prompts don't break CI on day one;
will be promoted to `error` once the repo is clean.

## Adding a new actor prompt

1. Copy the reference template above
2. Fill in role / inputs / steps / envelope
3. Run `python lint/prompt_lint.py --paths <your-prompt-file>` to check
4. Commit only when R001–R005 are clean and R006 has no missing sections

#!/usr/bin/env python3
"""Convert a behavior-auditor drift report into proposed lint rules.

Pipeline:
  1. behavior-auditor (.claude/agents/behavior-auditor.md) probes the live
     platform on a weekly schedule, writes reports to runs/behavior-drift/.
  2. This script reads one of those reports, finds probes with `Verdict: DRIFT`,
     and emits a Python rule scaffold for each drift not already covered by an
     existing R0NN rule in lint/prompt_lint.py.
  3. The scaffold is written to `lint/proposed/<probe_id>__<slug>.py` —
     a human reviews, edits the regex / heuristic, then moves it into
     prompt_lint.py's RULES list.

Why a scaffold and not auto-injection: the lint regex needs human judgment
(what's the false-positive surface? what's a documentation context vs an
instruction?). Auto-injection would produce noisy or wrong rules. The
scaffold removes the boilerplate so the reviewer focuses on the heuristic.

Usage:
  python lint/from_audit.py runs/behavior-drift/2026-05-06T14-07-00Z.md
  python lint/from_audit.py <report> --dry-run     # print scaffolds, write nothing
  python lint/from_audit.py <report> --output-dir lint/proposed
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_PATH = REPO_ROOT / "lint" / "prompt_lint.py"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "lint" / "proposed"

# Match a probe section: "## Behavior probe: <id> — <claim>"
PROBE_HEADER_RE = re.compile(
    r"^##\s+Behavior\s+probe:\s+(P-[a-z]+-\d+)\s+[—-]\s+(.+?)$",
    re.MULTILINE,
)
# Match the "Local source" line: "**Local source:** .claude/agents/<file>.md (lines a-b)"
LOCAL_SOURCE_RE = re.compile(
    r"\*\*Local source:\*\*\s*(.+?)(?:\n|$)",
)
# Match the verdict line: "DRIFT | NO DRIFT | INCONCLUSIVE — reason"
VERDICT_RE = re.compile(r"###\s+Verdict\s*\n+([^\n]+)", re.IGNORECASE)
# Match the observed block
OBSERVED_RE = re.compile(r"###\s+Observed\s*\n+(.+?)(?=^###\s+|^##\s+|\Z)", re.DOTALL | re.MULTILINE)
# Match the claimed block
CLAIMED_RE = re.compile(r"###\s+Claimed.*?\n+(.+?)(?=^###\s+|^##\s+|\Z)", re.DOTALL | re.MULTILINE)


@dataclass
class ProbeFinding:
    probe_id: str
    claim: str
    local_source: str
    claimed: str
    observed: str
    verdict: str  # raw verdict line

    @property
    def is_drift(self) -> bool:
        return self.verdict.upper().startswith("DRIFT")


def parse_report(report: str) -> list[ProbeFinding]:
    """Walk the markdown report, splitting on `## Behavior probe:` headers."""
    findings: list[ProbeFinding] = []
    headers = list(PROBE_HEADER_RE.finditer(report))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(report)
        section = report[start:end]
        local_source_m = LOCAL_SOURCE_RE.search(section)
        verdict_m = VERDICT_RE.search(section)
        observed_m = OBSERVED_RE.search(section)
        claimed_m = CLAIMED_RE.search(section)
        findings.append(ProbeFinding(
            probe_id=h.group(1),
            claim=h.group(2).strip(),
            local_source=local_source_m.group(1).strip() if local_source_m else "",
            claimed=claimed_m.group(1).strip() if claimed_m else "",
            observed=observed_m.group(1).strip() if observed_m else "",
            verdict=verdict_m.group(1).strip() if verdict_m else "(no verdict)",
        ))
    return findings


def existing_rule_ids(lint_py: str) -> list[str]:
    return sorted(set(re.findall(r'Rule\(\s*id="(R\d+)"', lint_py)))


def existing_probe_citations(lint_py: str) -> set[str]:
    """Set of probe IDs already cited by some rule."""
    return set(re.findall(r"\bP-[a-z]+-\d+\b", lint_py))


def next_rule_id(existing: list[str]) -> str:
    nums = [int(r[1:]) for r in existing]
    nxt = (max(nums) + 1) if nums else 1
    return f"R{nxt:03d}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


def render_scaffold(finding: ProbeFinding, rule_id: str) -> str:
    slug = slugify(finding.claim) or finding.probe_id.lower().replace("-", "_")
    func_name = f"rule_{rule_id.lower()}_{slug}"
    title = slug.replace("_", "-")
    # Trim observed/claimed blocks for readable docstring
    observed_short = finding.observed.replace("```", "'''")[:400]
    claimed_short = finding.claimed.replace("```", "'''")[:400]
    return f'''# Proposed lint rule from behavior-auditor probe {finding.probe_id}.
# Reviewer: edit the regex / heuristic below, then MOVE this rule's body
# into lint/prompt_lint.py and add a Rule(...) entry to RULES.

import re
from pathlib import Path
# from prompt_lint import Violation, relpath, is_actor_prompt  # uncomment when moved


def {func_name}(path: Path, content: str):
    """{rule_id}: {finding.claim}.

    Source: behavior-auditor probe {finding.probe_id}.
    Local source under probe: {finding.local_source}
    Verdict at scaffold time: {finding.verdict}

    Claimed:
        {claimed_short}

    Observed:
        {observed_short}

    TODO(reviewer):
    - Decide what string pattern in a prompt is evidence of the bad behavior.
    - Replace `PATTERN_THAT_INDICATES_DRIFT` with that pattern.
    - Decide severity (error|warn|info).
    - Decide which prompts this applies to (actor only? any prompt?).
    """
    pattern = re.compile(r"PATTERN_THAT_INDICATES_DRIFT")
    violations = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if pattern.search(line):
            violations.append(Violation(  # type: ignore[name-defined]
                rule_id="{rule_id}",
                severity="warn",
                file=relpath(path),  # type: ignore[name-defined]
                line=lineno,
                message=(
                    "{finding.claim} "
                    "(source: behavior-auditor probe {finding.probe_id})."
                ),
                snippet=line.strip()[:200],
            ))
    return violations


# After moving the function above into lint/prompt_lint.py, add this to RULES:
#
#     Rule(
#         id="{rule_id}",
#         severity="warn",
#         title="{title}",
#         description="{finding.claim} (probe {finding.probe_id})",
#         check={func_name},
#     ),
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Path to a behavior-auditor markdown report")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Where to write proposed rule scaffolds (default: lint/proposed/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print scaffolds; write nothing")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"Report not found: {report_path}", file=sys.stderr)
        return 2
    if not LINT_PATH.exists():
        print(f"prompt_lint.py not found at {LINT_PATH}", file=sys.stderr)
        return 2

    report = report_path.read_text(encoding="utf-8")
    lint_py = LINT_PATH.read_text(encoding="utf-8")

    findings = parse_report(report)
    drifts = [f for f in findings if f.is_drift]
    cited = existing_probe_citations(lint_py)
    new_drifts = [f for f in drifts if f.probe_id not in cited]
    rule_ids = existing_rule_ids(lint_py)

    print(f"Report: {report_path}")
    print(f"Findings parsed: {len(findings)} (DRIFT: {len(drifts)})")
    print(f"Drifts already covered by existing rules: {len(drifts) - len(new_drifts)}")
    print(f"New drifts requiring scaffolds: {len(new_drifts)}")

    if not new_drifts:
        print("Nothing to scaffold.")
        return 0

    out_dir = Path(args.output_dir)
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    next_id = next_rule_id(rule_ids)
    counter = int(next_id[1:])
    for f in new_drifts:
        rid = f"R{counter:03d}"
        counter += 1
        scaffold = render_scaffold(f, rid)
        slug = slugify(f.claim) or f.probe_id.lower().replace("-", "_")
        fname = f"{rid}_{f.probe_id.replace('-', '_')}__{slug}.py"
        target = out_dir / fname
        if args.dry_run:
            print(f"\n--- {target} ---")
            print(scaffold)
        else:
            target.write_text(scaffold, encoding="utf-8")
            print(f"Wrote {target}")

    if not args.dry_run:
        print(f"\nNext step: review each scaffold under {out_dir}, edit the heuristic, then move into lint/prompt_lint.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

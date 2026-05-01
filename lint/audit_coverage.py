#!/usr/bin/env python3
"""Coverage map between behavior-auditor probes and lint rules.

The pipeline:
  1. behavior-auditor probes the live platform → finds drift
  2. drift becomes a lint rule (R0NN) so it can't reappear silently elsewhere
  3. this script verifies every probe has at least one citing lint rule

Usage:
  python lint/audit_coverage.py             # markdown coverage report
  python lint/audit_coverage.py --format json
  python lint/audit_coverage.py --strict    # exit 1 if any probe is uncovered

Coverage = a lint rule's docstring or description mentions the probe ID.
That is the contract: when you write a rule from a drift, cite the probe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDITOR_PATH = REPO_ROOT / ".claude" / "agents" / "behavior-auditor.md"
LINT_PATH = REPO_ROOT / "lint" / "prompt_lint.py"

PROBE_ID_RE = re.compile(r"\bP-[a-z]+-\d+\b")
PROBE_DEF_RE = re.compile(r"\*\*\s*(P-[a-z]+-\d+)\s*:\s*(.+?)\*\*")


def discover_probes(auditor_md: str) -> dict[str, str]:
    """Find probe definitions in behavior-auditor.md.

    Returns {probe_id: short description}.
    """
    out: dict[str, str] = {}
    for m in PROBE_DEF_RE.finditer(auditor_md):
        pid = m.group(1)
        desc = m.group(2).strip()
        out.setdefault(pid, desc)
    # Catch composite definitions like "P-vaults-1, P-skills-1, P-memory-1: list + create..."
    for m in re.finditer(r"\*\*\s*((?:P-[a-z]+-\d+\s*,\s*)+P-[a-z]+-\d+)\s*:\s*(.+?)\*\*", auditor_md):
        ids = [p.strip() for p in m.group(1).split(",")]
        desc = m.group(2).strip()
        for pid in ids:
            out.setdefault(pid, desc)
    return out


def discover_rule_citations(lint_py: str) -> dict[str, list[str]]:
    """Find which probe IDs each lint rule cites.

    Returns {probe_id: [rule_id, ...]}.
    Citation = probe ID appears in a rule docstring or description string.
    """
    citations: dict[str, list[str]] = {}
    # Find all `Rule(id="R0NN", ...)` blocks
    for rule_m in re.finditer(
        r'Rule\(\s*id="(R\d+)".*?(?=Rule\(|\]\s*$)',
        lint_py,
        re.DOTALL,
    ):
        rule_id = rule_m.group(1)
        block = rule_m.group(0)
        for pid in set(PROBE_ID_RE.findall(block)):
            citations.setdefault(pid, []).append(rule_id)
    # Also scan rule docstrings (they live above the RULES list)
    for fn_m in re.finditer(
        r'def (rule_(r\d+)_\w+)\([^)]*\)\s*->\s*list\[Violation\]:\s*"""(.*?)"""',
        lint_py,
        re.DOTALL,
    ):
        rule_id = "R" + fn_m.group(2).lstrip("r").upper()
        # Pyright pattern: function names are rule_r001_..., extract digits
        digits = re.search(r"rule_r(\d+)_", fn_m.group(1))
        if digits:
            rule_id = "R" + digits.group(1)
        docstring = fn_m.group(3)
        for pid in set(PROBE_ID_RE.findall(docstring)):
            existing = citations.setdefault(pid, [])
            if rule_id not in existing:
                existing.append(rule_id)
    return citations


def render_markdown(probes: dict[str, str], citations: dict[str, list[str]]) -> str:
    out = ["# behavior-auditor ↔ lint coverage", ""]
    out.append(f"Probes defined: **{len(probes)}**")
    covered = sum(1 for p in probes if citations.get(p))
    out.append(f"Probes covered by ≥1 lint rule: **{covered}** / {len(probes)}")
    out.append("")
    out.append("| Probe | Description | Citing lint rules |")
    out.append("|---|---|---|")
    for pid, desc in sorted(probes.items()):
        rules = citations.get(pid, [])
        rule_cell = ", ".join(f"`{r}`" for r in sorted(rules)) if rules else "**(none — uncovered)**"
        desc_short = desc if len(desc) <= 60 else desc[:57] + "..."
        out.append(f"| `{pid}` | {desc_short} | {rule_cell} |")
    uncovered = [p for p in probes if not citations.get(p)]
    if uncovered:
        out.append("")
        out.append("## Uncovered probes")
        out.append("")
        out.append("These probes have no lint rule citing them. If a drift is observed against any of them, today there's no rule preventing the same mistake from re-appearing in another prompt.")
        out.append("")
        for pid in sorted(uncovered):
            out.append(f"- **`{pid}`** — {probes[pid]}")
        out.append("")
        out.append("Use `python lint/from_audit.py <auditor-report.md>` to scaffold a rule from a real drift report. Don't pre-write rules speculatively — wait for an observed failure.")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any probe is uncovered")
    args = parser.parse_args()

    if not AUDITOR_PATH.exists():
        print(f"behavior-auditor.md not found at {AUDITOR_PATH}", file=sys.stderr)
        return 2
    if not LINT_PATH.exists():
        print(f"prompt_lint.py not found at {LINT_PATH}", file=sys.stderr)
        return 2

    auditor = AUDITOR_PATH.read_text(encoding="utf-8")
    lint = LINT_PATH.read_text(encoding="utf-8")

    probes = discover_probes(auditor)
    citations = discover_rule_citations(lint)

    if args.format == "json":
        print(json.dumps(
            {
                "probes": probes,
                "citations": citations,
                "uncovered": [p for p in probes if not citations.get(p)],
            },
            indent=2,
        ))
    else:
        print(render_markdown(probes, citations))

    if args.strict and any(not citations.get(p) for p in probes):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

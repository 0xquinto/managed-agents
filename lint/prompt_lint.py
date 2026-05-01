#!/usr/bin/env python3
"""Prompt lint — encode known managed-agent prompt failure modes as rules.

Rules are grounded in observed failures from real session traces, not style
preferences. Each rule cites the originating session / behavior-auditor probe
in its description so a violation is traceable to evidence.

Usage:
  python lint/prompt_lint.py                        # lint default paths
  python lint/prompt_lint.py --paths agents/foo     # lint specific paths
  python lint/prompt_lint.py --format json          # machine-readable
  python lint/prompt_lint.py --severity error       # filter to errors only

Exit code: 1 if any error-severity violations, else 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PATHS = [
    REPO_ROOT / ".claude" / "agents",
    REPO_ROOT / "agents",
    REPO_ROOT / "runs",
]

# Files intentionally preserved as historical artifacts. They MUST trip rules
# (that's the documentation: "this is what the broken version looked like"),
# but CI shouldn't fail on them. Listed by repo-relative path.
DEFAULT_EXCLUDES = [
    "agents/insignia_ingestion/v1_system_prompt.md",  # baseline for v1 vs v2 paired McNemar
    "runs/",  # all captured run snapshots are frozen historical artifacts
]

PROMPT_GLOBS = [
    "*-expert.md",
    "*_system_prompt.md",
    "v*_system_prompt.md",
    "lead-0.md",
    "behavior-auditor.md",
    "docs-auditor.md",
]


def relpath(path: Path) -> str:
    """Path relative to repo root if possible, else absolute string."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass
class Violation:
    rule_id: str
    severity: str  # "error" | "warn" | "info"
    file: str
    line: int
    message: str
    snippet: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet,
        }


@dataclass
class Rule:
    id: str
    severity: str
    title: str
    description: str
    check: Callable[[Path, str], list[Violation]]


def is_actor_prompt(path: Path, content: str) -> bool:
    """Heuristic for 'actor' (non-expert) agent prompts.

    Actor prompts have first-person directives ('You are ...', 'Your job').
    Expert prompts in .claude/agents/*-expert.md are documentation-style.
    """
    if path.name.endswith("-expert.md"):
        return False
    if path.name in {"docs-auditor.md", "behavior-auditor.md"}:
        return False
    return any(
        marker in content
        for marker in ("Your job", "Output (returned to", "## Your job", "Outputs you produce")
    )


def is_session_resources_doc(path: Path, content: str) -> bool:
    """Files that document the sessions API and `mount_path` field."""
    return "mount_path" in content and (
        "sessions" in path.name.lower() or "session_resources" in content
    )


def find_lines(content: str, pattern: re.Pattern) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate(content.splitlines(), start=1):
        if pattern.search(line):
            out.append((i, line))
    return out


def rule_r001_wrong_mount_path(path: Path, content: str) -> list[Violation]:
    """R001: prompt instructs reading from /mnt/session/input/ (no `uploads/` segment).

    Files mounted as `type:file` resources are auto-prefixed with
    `/mnt/session/uploads/`, so `/mnt/session/input/<x>/` does NOT exist on
    the container. Source: behavior-auditor probe P-sessions-1.
    """
    pattern = re.compile(r"/mnt/session/input/")
    has_correct_path = "/mnt/session/uploads/input/" in content
    has_doc_context = any(
        kw in content.lower()
        for kw in ("auto-prefix", "wrong path", "p-sessions-1", "do not exist", "won't find")
    )
    violations = []
    for lineno, line in find_lines(content, pattern):
        # Skip if same line also mentions the correct path (likely contrast)
        if "/mnt/session/uploads/input/" in line:
            continue
        # Skip if file is documentation/probe context AND has correct-path nearby
        if has_correct_path and has_doc_context:
            continue
        # Skip if line itself looks like a probe payload (contains 2>/dev/null or `ls`)
        if "2>/dev/null" in line or re.search(r"\bls\b", line):
            continue
        violations.append(
            Violation(
                rule_id="R001",
                severity="error",
                file=relpath(path),
                line=lineno,
                message=(
                    "Path `/mnt/session/input/` does not exist for type=file resources. "
                    "Files mounted via session_resources are auto-prefixed with "
                    "`/mnt/session/uploads/`. Use `/mnt/session/uploads/input/<id>/...`."
                ),
                snippet=line.strip()[:200],
            )
        )
    return violations


def rule_r002_mount_path_prefix_undocumented(path: Path, content: str) -> list[Violation]:
    """R002: docs that describe `mount_path` without naming the auto-prefix.

    The sessions API silently rewrites `mount_path` for type=file resources by
    prepending `/mnt/session/uploads/`. Any expert prompt that lists `mount_path`
    must explain this so downstream agent prompts use the right absolute path.
    """
    if not is_session_resources_doc(path, content):
        return []
    documented = any(
        kw in content.lower()
        for kw in ("auto-prefix", "auto-prefixed", "uploads/", "prepended", "prepends")
    )
    if documented:
        return []
    pattern = re.compile(r"\bmount_path\b")
    matches = find_lines(content, pattern)
    if not matches:
        return []
    lineno, line = matches[0]
    return [
        Violation(
            rule_id="R002",
            severity="warn",
            file=relpath(path),
            line=lineno,
            message=(
                "Documents `mount_path` without explaining the `/mnt/session/uploads/` "
                "auto-prefix for type=file resources. Downstream prompt authors will "
                "compute wrong container paths."
            ),
            snippet=line.strip()[:200],
        )
    ]


def rule_r003_redundant_output_copy(path: Path, content: str) -> list[Violation]:
    """R003: instruction to copy outputs to /mnt/session/outputs/ in addition to a custom out dir.

    The platform's `/mnt/session/outputs/` is the canonical downloads area. When
    a prompt has the agent write to a custom `/mnt/session/out/<id>/` path AND
    also tells it (or implies) copying to `outputs/`, that copy is wasted I/O
    (~3s per run in the v1 baseline trace).
    """
    if not is_actor_prompt(path, content):
        return []
    has_custom_out = "/mnt/session/out/" in content and "/mnt/session/outputs/" not in content.replace(
        "/mnt/session/out/", "###OUT###"
    ).replace("/mnt/session/outputs/", "/mnt/session/outputs/")
    # Re-do that more carefully: we want both paths to be present.
    has_custom_out = bool(re.search(r"/mnt/session/out/[a-zA-Z<\$\{]", content))
    has_outputs = "/mnt/session/outputs/" in content
    if not (has_custom_out and has_outputs):
        return []
    # Skip if prompt explicitly says "do NOT copy" / "do not copy"
    if re.search(r"do\s*NOT\s*also\s*copy|do not copy", content, re.IGNORECASE):
        return []
    pattern = re.compile(r"/mnt/session/outputs/")
    matches = find_lines(content, pattern)
    if not matches:
        return []
    lineno, line = matches[0]
    return [
        Violation(
            rule_id="R003",
            severity="warn",
            file=relpath(path),
            line=lineno,
            message=(
                "Prompt references both a custom `/mnt/session/out/<id>/` path and "
                "`/mnt/session/outputs/`. v1 trace showed this pattern caused a "
                "redundant `cp -r` step (~3s/run). Either drop the `outputs/` mention "
                "or add an explicit 'do NOT copy' clause."
            ),
            snippet=line.strip()[:200],
        )
    ]


def rule_r004_fresh_interpreter_undocumented(path: Path, content: str) -> list[Violation]:
    """R004: actor prompt directs multi-step bash data extraction without warning that bash is stateless.

    The bash tool spawns a fresh Python interpreter per call — variables do
    not persist. Without a `/tmp/<id>/` persistence convention, agents
    re-extract large artifacts on every step (v1 wasted ~90s re-reading PDF
    pages 27–39 because the agent forgot prior extraction).
    """
    if not is_actor_prompt(path, content):
        return []
    # Does this prompt do heavy data extraction?
    file_kws = ("PDF", "Excel", "CSV", "xlsx", "pdfplumber", "pypdf", "pymupdf")
    if not any(kw in content for kw in file_kws):
        return []
    if "bash" not in content.lower():
        return []
    # Does it document the volatility?
    documented_markers = (
        "/tmp/",
        "fresh interpreter",
        "do not persist",
        "variables do not persist",
        "variables do NOT persist",
        "persist large",
        "single bash call",
        "combine related operations",
    )
    if any(m in content for m in documented_markers):
        return []
    # Find a representative line to anchor the violation
    pattern = re.compile(r"\bbash\b", re.IGNORECASE)
    matches = find_lines(content, pattern)
    lineno, line = matches[0] if matches else (1, "")
    return [
        Violation(
            rule_id="R004",
            severity="warn",
            file=relpath(path),
            line=lineno,
            message=(
                "Actor prompt uses bash for file extraction without warning that the "
                "bash interpreter resets between calls. Add `/tmp/<id>/` persistence "
                "guidance and a 'combine related operations into one bash call' rule. "
                "Source: v1 ingestion trace re-read PDF ~90s wasted."
            ),
            snippet=line.strip()[:200],
        )
    ]


def rule_r005_envelope_unstructured(path: Path, content: str) -> list[Violation]:
    """R005: actor prompt promises a JSON envelope as final response but does not forbid markdown fences / prose.

    Without an explicit 'no markdown fences, no prose' rule, models routinely
    wrap the JSON in ```json ... ``` blocks, breaking strict downstream parsers.
    """
    if not is_actor_prompt(path, content):
        return []
    # Does the prompt declare a JSON-envelope final response?
    if "JSON object" not in content and "json envelope" not in content.lower():
        return []
    # Already forbids fences/prose?
    if re.search(r"no\s+(surrounding\s+)?prose|no\s+markdown(\s+code)?\s+fences", content, re.IGNORECASE):
        return []
    pattern = re.compile(r"JSON object|json envelope", re.IGNORECASE)
    matches = find_lines(content, pattern)
    lineno, line = matches[0] if matches else (1, "")
    return [
        Violation(
            rule_id="R005",
            severity="warn",
            file=relpath(path),
            line=lineno,
            message=(
                "Prompt declares a JSON envelope final response but does not forbid "
                "surrounding prose / markdown fences. Add 'no surrounding prose, no "
                "markdown code fences' to prevent ```json wrapping breakage."
            ),
            snippet=line.strip()[:200],
        )
    ]


REQUIRED_SECTIONS = [
    ("inputs", re.compile(r"^##\s+Inputs?\s+you\s+receive\b", re.IGNORECASE | re.MULTILINE)),
    ("job", re.compile(r"^##\s+Your\s+job\b", re.IGNORECASE | re.MULTILINE)),
    ("output", re.compile(r"^##\s+Output\b", re.IGNORECASE | re.MULTILINE)),
    ("rules", re.compile(r"^##\s+Rules\b", re.IGNORECASE | re.MULTILINE)),
]


def rule_r006_missing_section(path: Path, content: str) -> list[Violation]:
    """R006: actor prompt missing one of the required schema sections.

    See `lint/schema.md` for the full template. Required sections are
    Inputs, Your job, Output, and Rules. Identity discipline + Tools are
    recommended but not enforced (yet).
    """
    if not is_actor_prompt(path, content):
        return []
    missing: list[str] = []
    for label, pattern in REQUIRED_SECTIONS:
        if not pattern.search(content):
            missing.append(label)
    if not missing:
        return []
    return [
        Violation(
            rule_id="R006",
            severity="warn",
            file=relpath(path),
            line=1,
            message=(
                f"Actor prompt missing required section(s): {', '.join(missing)}. "
                "See lint/schema.md for the actor-prompt template."
            ),
            snippet=content.splitlines()[0][:200] if content else "",
        )
    ]


RULES: list[Rule] = [
    Rule(
        id="R001",
        severity="error",
        title="wrong-mount-path",
        description="Reading from /mnt/session/input/ instead of /mnt/session/uploads/input/",
        check=rule_r001_wrong_mount_path,
    ),
    Rule(
        id="R002",
        severity="warn",
        title="mount-path-prefix-undocumented",
        description="`mount_path` documented without auto-prefix explanation",
        check=rule_r002_mount_path_prefix_undocumented,
    ),
    Rule(
        id="R003",
        severity="warn",
        title="redundant-output-copy",
        description="Both /mnt/session/out/ and /mnt/session/outputs/ referenced without 'do not copy' clause",
        check=rule_r003_redundant_output_copy,
    ),
    Rule(
        id="R004",
        severity="warn",
        title="fresh-interpreter-undocumented",
        description="Actor prompt does bash file extraction without /tmp/ persistence guidance",
        check=rule_r004_fresh_interpreter_undocumented,
    ),
    Rule(
        id="R005",
        severity="warn",
        title="json-envelope-unguarded",
        description="JSON envelope declared without no-prose/no-fences clause",
        check=rule_r005_envelope_unstructured,
    ),
    Rule(
        id="R006",
        severity="warn",
        title="missing-required-section",
        description="Actor prompt missing required schema section (see lint/schema.md)",
        check=rule_r006_missing_section,
    ),
]


def is_excluded(path: Path, excludes: Iterable[str]) -> bool:
    rp = relpath(path)
    for ex in excludes:
        if ex.endswith("/"):
            if rp.startswith(ex):
                return True
        elif rp == ex:
            return True
    return False


def discover_files(paths: Iterable[Path], excludes: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            out.append(root)
            continue
        for glob in PROMPT_GLOBS:
            out.extend(root.rglob(glob))
        # Captured prompts often live in `system_prompts/*.md` directories.
        for md in root.rglob("*.md"):
            if "system_prompts" in md.parts:
                out.append(md)
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for p in out:
        rp = p.resolve()
        if rp not in seen and not is_excluded(p, excludes):
            seen.add(rp)
            uniq.append(p)
    return sorted(uniq)


def lint_file(path: Path) -> list[Violation]:
    content = path.read_text(encoding="utf-8")
    violations: list[Violation] = []
    for rule in RULES:
        violations.extend(rule.check(path, content))
    return violations


def render_markdown(violations: list[Violation], scanned: list[Path]) -> str:
    out = ["# Prompt lint report", ""]
    out.append(f"Scanned **{len(scanned)}** prompt files.")
    out.append("")
    by_severity = {"error": [], "warn": [], "info": []}
    for v in violations:
        by_severity.setdefault(v.severity, []).append(v)
    out.append(
        f"Found **{len(by_severity['error'])} error**, "
        f"**{len(by_severity['warn'])} warn**, "
        f"**{len(by_severity['info'])} info** violations."
    )
    out.append("")
    if not violations:
        out.append("All checked prompts pass.")
        return "\n".join(out)
    out.append("## Rules")
    out.append("")
    out.append("| Rule | Severity | Title |")
    out.append("|---|---|---|")
    for r in RULES:
        out.append(f"| `{r.id}` | {r.severity} | {r.title} |")
    out.append("")
    out.append("## Violations")
    out.append("")
    by_file: dict[str, list[Violation]] = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)
    for fname in sorted(by_file):
        out.append(f"### `{fname}`")
        out.append("")
        for v in sorted(by_file[fname], key=lambda x: (x.line, x.rule_id)):
            out.append(f"- **`{v.rule_id}`** ({v.severity}) line {v.line} — {v.message}")
            out.append(f"  - `{v.snippet}`")
        out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Override paths to scan (defaults: .claude/agents, agents, runs)",
    )
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument(
        "--severity",
        choices=["error", "warn", "info"],
        default=None,
        help="Filter violations to this severity or higher",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Repo-relative path to exclude (suffix '/' for directory). Repeatable. "
        "Default excludes are skipped if any --exclude is passed; use --no-default-excludes "
        "with empty --exclude to scan everything.",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Drop the built-in DEFAULT_EXCLUDES (frozen v1 prompt + runs/).",
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths] if args.paths else DEFAULT_PATHS
    if args.no_default_excludes:
        excludes = list(args.exclude or [])
    elif args.exclude is not None:
        excludes = list(DEFAULT_EXCLUDES) + list(args.exclude)
    else:
        excludes = list(DEFAULT_EXCLUDES)
    files = discover_files(paths, excludes)
    violations: list[Violation] = []
    for f in files:
        violations.extend(lint_file(f))

    severity_rank = {"error": 0, "warn": 1, "info": 2}
    if args.severity is not None:
        threshold = severity_rank[args.severity]
        violations = [v for v in violations if severity_rank[v.severity] <= threshold]

    if args.format == "json":
        print(json.dumps(
            {
                "scanned": [relpath(f) for f in files],
                "violations": [v.to_dict() for v in violations],
            },
            indent=2,
        ))
    else:
        print(render_markdown(violations, files))

    has_errors = any(v.severity == "error" for v in violations)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())

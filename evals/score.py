#!/usr/bin/env python3
"""
Score a captured agent run against an eval case's expected.json.

Usage:
    score.py <case_path> --run <run_dir> [--manifest <path>]

<case_path>    e.g. ingestion/tafi_2025
<run_dir>      directory containing the captured envelope + (optionally) the manifest
                — for replay mode this is typically runs/<id>/smoke/

The scorer looks for these files inside <run_dir>:
    ingestion_final_envelope.json   the agent's final user-message JSON
    manifest.json                   (optional) the manifest the agent wrote
    events.json                     (optional) full event stream for discipline checks

Exit code = number of failed assertions (0 = pass).
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):
    with path.open() as fp:
        return json.load(fp)


def get_field(obj, dotted_path: str):
    """Walk a.b.c into a nested dict; return (found, value)."""
    cur = obj
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def score_envelope(expected, envelope, results):
    for a in expected.get("envelope", []):
        field, kind = a["field"], a["type"]
        found, val = get_field(envelope, field)
        if not found:
            results.append(("FAIL", f"envelope.{field}", f"missing field"))
            continue
        if kind == "exact":
            ok = val == a["value"]
            results.append(("PASS" if ok else "FAIL", f"envelope.{field}",
                            f"expected={a['value']!r} actual={val!r}"))
        else:
            results.append(("ERROR", f"envelope.{field}", f"unsupported assertion type {kind!r}"))


def score_envelope_format(expected, envelope_str, results):
    for a in expected.get("envelope_format", []):
        kind = a["type"]
        if kind == "no_markdown_fences":
            ok = "```" not in envelope_str
            results.append(("PASS" if ok else "FAIL", "envelope_format.no_markdown_fences",
                            "envelope is raw JSON" if ok else "envelope wraps JSON in ``` fences"))
        elif kind == "no_surrounding_prose":
            stripped = envelope_str.strip()
            ok = stripped.startswith("{") and stripped.endswith("}")
            results.append(("PASS" if ok else "FAIL", "envelope_format.no_surrounding_prose",
                            "envelope is a single JSON object" if ok else "envelope has surrounding prose"))
        else:
            results.append(("ERROR", "envelope_format", f"unsupported assertion type {kind!r}"))


def score_outputs(expected, run_dir: Path, results, manifest):
    """File-exists assertions can be checked two ways: against locally-mirrored files OR
    against a 'outputs' field in the manifest if the agent recorded one. Both modes are accepted."""
    declared_outputs = set()
    if manifest and isinstance(manifest.get("outputs"), list):
        for o in manifest["outputs"]:
            if isinstance(o, dict) and "path" in o:
                declared_outputs.add(o["path"])
            elif isinstance(o, str):
                declared_outputs.add(o)

    for a in expected.get("outputs", []):
        if a["type"] != "file_exists":
            results.append(("ERROR", f"outputs", f"unsupported type {a['type']!r}"))
            continue
        path = a["path"]
        local = run_dir / path.lstrip("/")
        ok = local.exists() or path in declared_outputs
        results.append(("PASS" if ok else "FAIL", f"outputs.file_exists",
                        f"{path} {'(local mirror)' if local.exists() else '(via manifest.outputs)' if ok else '(missing)'}"))


def score_manifest(expected, manifest, results):
    spec = expected.get("manifest")
    if spec is None:
        return
    if manifest is None:
        results.append(("SKIP", "manifest", "manifest.json not present in run dir; skipping all manifest assertions"))
        return

    for k in spec.get("required_keys", []):
        ok = k in manifest
        results.append(("PASS" if ok else "FAIL", f"manifest.required_keys.{k}",
                        "present" if ok else "missing"))

    for a in spec.get("field_assertions", []):
        field, kind = a["field"], a["type"]
        found, val = get_field(manifest, field)
        if not found:
            results.append(("FAIL", f"manifest.{field}", "missing field"))
            continue
        if kind == "exact":
            ok = val == a["value"]
            results.append(("PASS" if ok else "FAIL", f"manifest.{field}",
                            f"expected={a['value']!r} actual={val!r}"))
        elif kind == "range":
            if val is None:
                results.append(("FAIL", f"manifest.{a['field']}", "value is null"))
                continue
            try:
                num = float(val)  # type: ignore[arg-type]
                ok = a.get("min", float("-inf")) <= num <= a.get("max", float("inf"))
                results.append(("PASS" if ok else "FAIL", f"manifest.{field}",
                                f"in [{a.get('min')}, {a.get('max')}] actual={val}"))
            except (TypeError, ValueError):
                results.append(("FAIL", f"manifest.{field}", f"not numeric: {val!r}"))
        elif kind == "contains_one_of":
            sval = str(val).lower()
            ok = any(opt.lower() in sval for opt in a["values"])
            results.append(("PASS" if ok else "FAIL", f"manifest.{field}",
                            f"one of {a['values']!r} actual={val!r}"))
        else:
            results.append(("ERROR", f"manifest.{field}", f"unsupported type {kind!r}"))


def score_quality_flags(expected, manifest, results):
    spec = expected.get("quality_flags")
    if spec is None:
        return
    if manifest is None:
        results.append(("SKIP", "quality_flags", "manifest.json not present"))
        return

    flags = manifest.get("quality_flags", [])
    if not isinstance(flags, list):
        results.append(("FAIL", "quality_flags", "manifest.quality_flags is not a list"))
        return

    n = len(flags)
    if "count_at_least" in spec:
        ok = n >= spec["count_at_least"]
        results.append(("PASS" if ok else "FAIL", "quality_flags.count_at_least",
                        f"n={n} bound>={spec['count_at_least']}"))
    if "count_at_most" in spec:
        ok = n <= spec["count_at_most"]
        results.append(("PASS" if ok else "FAIL", "quality_flags.count_at_most",
                        f"n={n} bound<={spec['count_at_most']}"))

    if "all_severities_in" in spec:
        allowed = set(s.lower() for s in spec["all_severities_in"])
        actual = set(str(f.get("severity", "")).lower() for f in flags if isinstance(f, dict))
        bad = actual - allowed
        ok = not bad
        results.append(("PASS" if ok else "FAIL", "quality_flags.all_severities_in",
                        f"actual={sorted(actual)} allowed={sorted(allowed)}"
                        + (f" unexpected={sorted(bad)}" if bad else "")))

    flag_text_blob = " ".join(
        " ".join(str(v) for v in f.values()) if isinstance(f, dict) else str(f)
        for f in flags
    ).lower()
    for cat in spec.get("categories_include", []):
        ok = any(token.lower() in flag_text_blob for token in cat["must_match_any"])
        results.append(("PASS" if ok else "FAIL", f"quality_flags.category.{cat['category']}",
                        f"matched any of {cat['must_match_any']!r}"))


def score_reconciliations(expected, manifest, results):
    if manifest is None:
        if expected.get("reconciliations"):
            results.append(("SKIP", "reconciliations", "manifest.json not present"))
        return
    for a in expected.get("reconciliations", []):
        field = a["field"]
        kind = a["type"]
        found, val = get_field(manifest, field)
        if not found:
            results.append(("FAIL", f"reconciliations.{a['name']}", f"missing {field}"))
            continue
        if kind == "exact":
            ok = val == a["value"]
            results.append(("PASS" if ok else "FAIL", f"reconciliations.{a['name']}",
                            f"expected={a['value']!r} actual={val!r}"))
        elif kind == "range":
            if val is None:
                results.append(("FAIL", f"reconciliations.{a['name']}", "value is null"))
                continue
            try:
                num = float(val)  # type: ignore[arg-type]
                ok = a.get("min", float("-inf")) <= num <= a.get("max", float("inf"))
                results.append(("PASS" if ok else "FAIL", f"reconciliations.{a['name']}",
                                f"in [{a.get('min')}, {a.get('max')}] actual={val}"))
            except (TypeError, ValueError):
                results.append(("FAIL", f"reconciliations.{a['name']}", f"not numeric: {val!r}"))


def parse_event_stream(path: Path):
    """The platform's events.json / raw_stream.json is concatenated JSON objects,
    not a JSON array and not strict JSONL. Walk with raw_decode."""
    text = path.read_text()
    dec = json.JSONDecoder()
    pos = 0
    out = []
    n = len(text)
    while pos < n:
        while pos < n and text[pos] in " \t\n\r":
            pos += 1
        if pos >= n:
            break
        try:
            obj, end = dec.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        out.append(obj)
        pos = end
    return out


def normalize_stop_reason(val):
    """stop_reason can be either a string ('end_turn') or {'type': 'end_turn'}."""
    if isinstance(val, dict):
        return val.get("type")
    return val


def score_discipline(expected, run_dir: Path, results):
    events_path = run_dir / "events.json"
    if not events_path.exists():
        events_path = run_dir / "raw_stream.json"
    events = parse_event_stream(events_path) if events_path.exists() else None

    for a in expected.get("discipline", []):
        kind = a["type"]
        if kind == "no_error_events":
            if events is None:
                results.append(("SKIP", "discipline.no_error_events", "no events.json or raw_stream.json"))
                continue
            errs = [e for e in events if isinstance(e, dict) and e.get("is_error") is True]
            ok = not errs
            results.append(("PASS" if ok else "FAIL", "discipline.no_error_events",
                            f"errors={len(errs)}"))
        elif kind == "stop_reason":
            if events is None:
                results.append(("SKIP", "discipline.stop_reason", "no event stream"))
                continue
            stops = [normalize_stop_reason(e.get("stop_reason"))
                     for e in events if isinstance(e, dict) and e.get("stop_reason")]
            stops = [s for s in stops if s]
            ok = a["value"] in stops if stops else False
            results.append(("PASS" if ok else "FAIL", "discipline.stop_reason",
                            f"expected={a['value']!r} observed={stops!r}"))


def render_scorecard(results, case_id, run_dir, manifest_present):
    out = []
    out.append(f"# Eval scorecard: `{case_id}`")
    out.append("")
    out.append(f"**Run directory:** `{run_dir}`")
    out.append(f"**Manifest:** {'present' if manifest_present else 'absent (manifest assertions skipped)'}")
    out.append("")
    n_pass = sum(1 for r in results if r[0] == "PASS")
    n_fail = sum(1 for r in results if r[0] == "FAIL")
    n_err = sum(1 for r in results if r[0] == "ERROR")
    n_skip = sum(1 for r in results if r[0] == "SKIP")
    verdict = "PASS" if n_fail == 0 and n_err == 0 else "FAIL"
    out.append(f"**Verdict:** {verdict} — {n_pass} pass / {n_fail} fail / {n_err} error / {n_skip} skip")
    out.append("")
    out.append("| Status | Assertion | Detail |")
    out.append("|---|---|---|")
    for status, name, detail in results:
        out.append(f"| {status} | `{name}` | {detail} |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("case", help="Eval case path, e.g. ingestion/tafi_2025")
    p.add_argument("--run", required=True, help="Directory containing the captured run")
    p.add_argument("--manifest", help="Override manifest path (defaults to <run>/manifest.json)")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent
    case_dir = repo_root / args.case
    if not case_dir.is_dir():
        print(f"ERROR: case dir not found: {case_dir}", file=sys.stderr)
        return 2

    expected = load_json(case_dir / "expected.json")
    run_dir = Path(args.run).resolve()

    envelope_path = run_dir / "ingestion_final_envelope.json"
    if not envelope_path.exists():
        print(f"ERROR: envelope not found at {envelope_path}", file=sys.stderr)
        return 2
    envelope_str = envelope_path.read_text()
    envelope = json.loads(envelope_str)

    manifest_path = Path(args.manifest) if args.manifest else (run_dir / "manifest.json")
    manifest = load_json(manifest_path) if manifest_path.exists() else None

    results = []
    score_envelope(expected, envelope, results)
    score_envelope_format(expected, envelope_str, results)
    score_outputs(expected, run_dir, results, manifest)
    score_manifest(expected, manifest, results)
    score_quality_flags(expected, manifest, results)
    score_reconciliations(expected, manifest, results)
    score_discipline(expected, run_dir, results)

    scorecard = render_scorecard(results, expected["case_id"], run_dir, manifest is not None)
    print(scorecard)

    n_fail = sum(1 for r in results if r[0] in ("FAIL", "ERROR"))
    return 0 if n_fail == 0 else min(n_fail, 1)


if __name__ == "__main__":
    sys.exit(main())

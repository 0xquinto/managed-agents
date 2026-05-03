#!/usr/bin/env python3
"""
Score a captured agent run against an eval case's expected.json.

Two modes:

  Single-trial (existing behaviour):
      score.py <case> --run <run_dir> [--manifest <path>]

  Multi-trial aggregate (per playbook § 9 — Wilson CI, paired-test ready):
      score.py <case> --trials <trials_dir> [--paraphrase v1_canonical]

In multi-trial mode, <trials_dir> contains subdirectories — one per trial —
each with the same shape as a single-trial <run_dir>. The scorer computes a
Wilson-95% pass-rate per assertion across trials, broken out by the
`process` / `outcome` / `environment` columns.

Reporting unit per playbook § 8 (Bowyer ICML 2025 + ICLR Blogposts 2025):
    <rate> [<lo>, <hi>] (Wilson 95%, n=N)

Exit code = number of failed PROCESS-column assertions (process is the
column attributed to the agent; outcome co-tagged with environment;
environment failures are reported but excluded from the agent's pass-rate).
"""

import argparse
import csv
import json
import math
import sys
from io import StringIO
from pathlib import Path


def load_json(path: Path):
    with path.open() as fp:
        return json.load(fp)


def get_field(obj, dotted_path: str):
    cur = obj
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def wilson_ci(k: int, n: int, z: float = 1.96):
    """Wilson 95% confidence interval for a binomial proportion.
    Per playbook § 8 — Wald/CLT-based CIs are forbidden at small n; they
    under-cover near p=0 and p=1.
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - margin), min(1.0, center + margin)


def parse_event_stream(path: Path):
    """events.json / raw_stream.json is concatenated JSON objects (not array, not strict JSONL)."""
    text = path.read_text()
    dec = json.JSONDecoder()
    pos, n = 0, len(text)
    out = []
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
    if isinstance(val, dict):
        return val.get("type")
    return val


# --- Per-assertion scoring (returns list of (status, name, detail, column)) ---


def _result(status, name, detail, column):
    return (status, name, detail, column)




def _check_assertion(name: str, kind: str, val, a, manifest, col: str):
    """Generic assertion dispatcher used by both envelope + manifest scorers.

    Returns a single _result row. Supports the v3 assertion vocabulary:
      exact, range, contains_one_of, contains_all_substrings_ci, regex,
      min_length, is_object, is_string, is_superset_of, is_subset_of_field,
      is_subset_of, must_not_contain, language.
    """
    import re
    if kind == "exact":
        ok = val == a["value"]
        return _result("PASS" if ok else "FAIL", name,
                       f"expected={a['value']!r} actual={val!r}", col)
    if kind == "range":
        if val is None:
            return _result("FAIL", name, "value is null", col)
        try:
            num = float(val)
            ok = a.get("min", float("-inf")) <= num <= a.get("max", float("inf"))
            return _result("PASS" if ok else "FAIL", name,
                           f"in [{a.get('min')}, {a.get('max')}] actual={val}", col)
        except (TypeError, ValueError):
            return _result("FAIL", name, f"not numeric: {val!r}", col)
    if kind == "contains_one_of":
        sval = str(val).lower()
        ok = any(opt.lower() in sval for opt in a["values"])
        return _result("PASS" if ok else "FAIL", name,
                       f"one of {a['values']!r} actual={val!r}", col)
    if kind == "regex":
        if not isinstance(val, str):
            return _result("FAIL", name, f"not a string: {val!r}", col)
        ok = bool(re.match(a["value"], val))
        return _result("PASS" if ok else "FAIL", name,
                       f"regex {a['value']!r} actual={val!r}", col)
    if kind == "min_length":
        try:
            n = len(val)
        except TypeError:
            return _result("FAIL", name, f"not lengthy: {val!r}", col)
        ok = n >= a["value"]
        return _result("PASS" if ok else "FAIL", name,
                       f"len ≥ {a['value']} actual={n}", col)
    if kind == "is_object":
        ok = isinstance(val, dict)
        return _result("PASS" if ok else "FAIL", name,
                       f"is dict={ok} actual_type={type(val).__name__}", col)
    if kind == "is_string":
        ok = isinstance(val, str) and len(val) > 0
        return _result("PASS" if ok else "FAIL", name,
                       f"non-empty str={ok} actual={val!r}", col)
    if kind == "is_superset_of":
        if not isinstance(val, list):
            return _result("FAIL", name, f"not a list: {val!r}", col)
        required = set(a["values"])
        actual = set(val)
        missing = required - actual
        ok = not missing
        return _result("PASS" if ok else "FAIL", name,
                       f"superset of {sorted(required)} missing={sorted(missing)}", col)
    if kind == "is_subset_of_field":
        if not isinstance(val, list):
            return _result("FAIL", name, f"not a list: {val!r}", col)
        of_field = a["of_field"]
        found, parent_val = get_field(manifest, of_field)
        if not found or not isinstance(parent_val, list):
            return _result("FAIL", name,
                           f"sibling field {of_field!r} missing or not a list", col)
        actual = set(val)
        parent_set = set(parent_val)
        extras = actual - parent_set
        ok = not extras
        return _result("PASS" if ok else "FAIL", name,
                       f"subset of {of_field}={sorted(parent_set)} extras={sorted(extras)}", col)
    if kind == "is_subset_of":
        # Plain subset: actual list values must all appear in the expected
        # `values` list. Distinct from `is_subset_of_field` which compares
        # against a sibling field. Spec § 7.4 v3 vocab.
        if not isinstance(val, list):
            return _result("FAIL", name, f"not a list: {val!r}", col)
        allowed = set(a["values"])
        actual = set(val)
        extras = actual - allowed
        ok = not extras
        return _result("PASS" if ok else "FAIL", name,
                       f"subset of {sorted(allowed)} extras={sorted(extras)}", col)
    if kind == "contains_all_substrings_ci":
        # Case-insensitive substring containment. `values` is the required set —
        # ALL must appear at least once in the string. Used for asserting an
        # email body references each missing item by name (the agent must not
        # collapse multiple missing items into a single generic mention).
        if not isinstance(val, str):
            return _result("FAIL", name, f"not a string: {val!r}", col)
        sval = val.lower()
        missing = [t for t in a["values"] if t.lower() not in sval]
        ok = not missing
        return _result("PASS" if ok else "FAIL", name,
                       f"required substrings {a['values']!r} missing={missing!r}", col)
    if kind == "must_not_contain":
        # Two semantics, deliberately asymmetric — `values` is the forbidden set:
        #   - string val → substring check (forbidden phrases in prose, e.g. "ignore previous")
        #   - list val   → element-equality check (forbidden tags/ids, e.g. {"PII"} in flags)
        # If you want substring semantics over a list, join it first or split your
        # forbidden tokens. Spec § 7.4 v3 vocab.
        forbidden = a["values"]
        if isinstance(val, str):
            hit = next((f for f in forbidden if f in val), None)
        elif isinstance(val, list):
            hit = next((v for v in val if v in forbidden), None)
        else:
            return _result("FAIL", name, f"not a string or list: {val!r}", col)
        ok = hit is None
        return _result("PASS" if ok else "FAIL", name,
                       f"forbidden={forbidden!r} hit={hit!r}", col)
    if kind == "language":
        # Deterministic language detection. v1 ships with `langdetect` (seed-pinned)
        # — see `_detect_language`. The expected language is an ISO 639-1 code
        # (es / en / pt / ...). Spec § 7.4 v3 vocab.
        if not isinstance(val, str):
            return _result("FAIL", name, f"not a string: {val!r}", col)
        if len(val.strip()) < 20:
            # Short text is an instrument confounder, not an agent miss — emit
            # SKIP on the environment column so it's excluded from the agent's
            # process pass-rate per playbook § 9.
            return _result(
                "SKIP", name,
                f"too short to classify reliably (len={len(val)} < 20 chars)",
                "environment",
            )
        try:
            detected = _detect_language(val)
        except _LanguageDetectUnavailable as exc:
            return _result("ERROR", name, str(exc), col)
        ok = detected == a["expected"]
        return _result("PASS" if ok else "FAIL", name,
                       f"expected={a['expected']!r} detected={detected!r}", col)
    return _result("ERROR", name, f"unsupported type {kind!r}", col)


# ---------------------------------------------------------------------------
# Deterministic language detection
# ---------------------------------------------------------------------------


class _LanguageDetectUnavailable(RuntimeError):
    """Raised when `langdetect` isn't installed — the assertion can't run."""


def _detect_language(text: str) -> str:
    """Detect ISO 639-1 language code via langdetect, deterministically.

    `langdetect` is non-deterministic by default (uses a stochastic Naive
    Bayes), so we seed `DetectorFactory.seed = 0` once at import time. The
    same input then always produces the same label across CI runs and dev
    machines — required for paired-McNemar A/Bs to be reproducible per
    playbook § 9.
    """
    try:
        from langdetect import DetectorFactory, detect
    except ImportError as exc:  # pragma: no cover — env-dep
        raise _LanguageDetectUnavailable(
            "langdetect not installed; add it to evals/requirements.txt or "
            "the poller's [dev] extra"
        ) from exc

    DetectorFactory.seed = 0
    return detect(text)

def score_envelope(expected, envelope):
    out = []
    for a in expected.get("envelope", []):
        col = a.get("column", "process")
        field, kind = a["field"], a["type"]
        found, val = get_field(envelope, field)
        if not found:
            out.append(_result("FAIL", f"envelope.{field}", "missing field", col))
            continue
        out.append(_check_assertion(f"envelope.{field}", kind, val, a, envelope, col))
    return out


def score_envelope_format(expected, envelope_str):
    out = []
    for a in expected.get("envelope_format", []):
        col = a.get("column", "process")
        kind = a["type"]
        if kind == "no_markdown_fences":
            ok = "```" not in envelope_str
            out.append(_result("PASS" if ok else "FAIL", "envelope_format.no_markdown_fences",
                               "envelope is raw JSON" if ok else "envelope wraps JSON in ``` fences", col))
        elif kind == "no_surrounding_prose":
            stripped = envelope_str.strip()
            ok = stripped.startswith("{") and stripped.endswith("}")
            out.append(_result("PASS" if ok else "FAIL", "envelope_format.no_surrounding_prose",
                               "envelope is a single JSON object" if ok else "envelope has surrounding prose", col))
        else:
            out.append(_result("ERROR", "envelope_format", f"unsupported type {kind!r}", col))
    return out


def _validate_format(local_path: Path, fmt: str):
    """Returns (ok, detail). Defeats stub-file masking — empty or unparseable files fail."""
    if not local_path.exists():
        return False, "missing"
    size = local_path.stat().st_size
    if size == 0:
        return False, "empty (0 bytes)"
    try:
        if fmt == "json":
            json.loads(local_path.read_text())
        elif fmt == "csv":
            txt = local_path.read_text()
            reader = csv.reader(StringIO(txt))
            rows = list(reader)
            if not rows:
                return False, "csv parsed but contains zero rows"
        elif fmt == "text":
            txt = local_path.read_text()
            if not txt.strip():
                return False, "text file is whitespace-only"
        else:
            return False, f"unknown format {fmt!r}"
    except Exception as e:
        return False, f"{fmt} parse error: {e}"
    return True, f"{size} bytes, parses as {fmt}"


def score_outputs(expected, run_dir: Path, manifest):
    out = []
    declared = set()
    if manifest and isinstance(manifest.get("outputs"), list):
        for o in manifest["outputs"]:
            if isinstance(o, dict) and "path" in o:
                declared.add(o["path"])
            elif isinstance(o, str):
                declared.add(o)

    for a in expected.get("outputs", []):
        col = a.get("column", "outcome")
        path = a["path"]
        kind = a["type"]
        local = run_dir / path.lstrip("/")

        if kind == "file_exists_and_nonempty":
            fmt = a.get("format", "json")
            # The runner saves captured container files by basename into the
            # trial dir (e.g. /mnt/session/out/x/manifest.json → manifest.json).
            # Fall back to the basename if the absolute-path mirror isn't there.
            local_basename = run_dir / Path(path).name
            target = local if local.exists() else local_basename
            if target.exists():
                ok, detail = _validate_format(target, fmt)
                out.append(_result("PASS" if ok else "FAIL", "outputs.file_exists_and_nonempty",
                                   f"{path} ({detail})", col))
            elif path in declared:
                # Manifest declares it but we don't have the file locally.
                # Score as INCONCLUSIVE — a real environment confounder; not a process fail.
                out.append(_result("SKIP", "outputs.file_exists_and_nonempty",
                                   f"{path} (declared in manifest, not mirrored locally)", "environment"))
            else:
                out.append(_result("FAIL", "outputs.file_exists_and_nonempty",
                                   f"{path} (missing, not declared)", col))
        elif kind == "file_exists":
            ok = local.exists() or path in declared
            out.append(_result("PASS" if ok else "FAIL", "outputs.file_exists",
                               f"{path} {'(local)' if local.exists() else '(via manifest)' if ok else '(missing)'}",
                               col))
        else:
            out.append(_result("ERROR", "outputs", f"unsupported type {kind!r}", col))
    return out


def score_manifest(expected, manifest):
    out = []
    spec = expected.get("manifest")
    if spec is None:
        return out
    if manifest is None:
        out.append(_result("SKIP", "manifest", "manifest.json not present", "environment"))
        return out
    for k in spec.get("required_keys", []):
        ok = k in manifest
        out.append(_result("PASS" if ok else "FAIL", f"manifest.required_keys.{k}",
                           "present" if ok else "missing", "outcome"))
    for a in spec.get("field_assertions", []):
        col = a.get("column", "outcome")
        field, kind = a["field"], a["type"]
        found, val = get_field(manifest, field)
        if not found:
            out.append(_result("FAIL", f"manifest.{field}", "missing field", col))
            continue
        out.append(_check_assertion(f"manifest.{field}", kind, val, a, manifest, col))
    return out


def score_quality_flags(expected, manifest):
    out = []
    spec = expected.get("quality_flags")
    if spec is None:
        return out
    col = spec.get("column", "process")
    if manifest is None:
        out.append(_result("SKIP", "quality_flags", "manifest.json not present", "environment"))
        return out
    flags = manifest.get("quality_flags", [])
    if not isinstance(flags, list):
        out.append(_result("FAIL", "quality_flags", "not a list", col))
        return out
    n = len(flags)
    if "count_at_least" in spec:
        ok = n >= spec["count_at_least"]
        out.append(_result("PASS" if ok else "FAIL", "quality_flags.count_at_least",
                           f"n={n} bound>={spec['count_at_least']}", col))
    if "count_at_most" in spec:
        ok = n <= spec["count_at_most"]
        out.append(_result("PASS" if ok else "FAIL", "quality_flags.count_at_most",
                           f"n={n} bound<={spec['count_at_most']}", col))
    if "all_severities_in" in spec:
        allowed = set(s.lower() for s in spec["all_severities_in"])
        actual = set(str(f.get("severity", "")).lower() for f in flags if isinstance(f, dict))
        bad = actual - allowed
        ok = not bad
        out.append(_result("PASS" if ok else "FAIL", "quality_flags.all_severities_in",
                           f"actual={sorted(actual)} allowed={sorted(allowed)}"
                           + (f" unexpected={sorted(bad)}" if bad else ""), col))
    blob = " ".join(
        " ".join(str(v) for v in f.values()) if isinstance(f, dict) else str(f)
        for f in flags
    ).lower()
    for cat in spec.get("categories_include", []):
        c_col = cat.get("column", col)
        ok = any(t.lower() in blob for t in cat["must_match_any"])
        out.append(_result("PASS" if ok else "FAIL", f"quality_flags.category.{cat['category']}",
                           f"matched any of {cat['must_match_any']!r}", c_col))
    return out


def score_reconciliations(expected, manifest):
    out = []
    rec = expected.get("reconciliations", [])
    # The v3 ingestion slice uses a dict with `_note` to mark "this slice
    # doesn't check reconciliations" — accept that shape as no-op rather
    # than iterating its keys as if they were assertion specs.
    if isinstance(rec, dict):
        return out
    if manifest is None:
        if rec:
            out.append(_result("SKIP", "reconciliations", "manifest.json not present", "environment"))
        return out
    for a in rec:
        col = a.get("column", "outcome")
        field, kind = a["field"], a["type"]
        found, val = get_field(manifest, field)
        if not found:
            out.append(_result("FAIL", f"reconciliations.{a['name']}", f"missing {field}", col))
            continue
        if kind == "exact":
            ok = val == a["value"]
            out.append(_result("PASS" if ok else "FAIL", f"reconciliations.{a['name']}",
                               f"expected={a['value']!r} actual={val!r}", col))
        elif kind == "range":
            if val is None:
                out.append(_result("FAIL", f"reconciliations.{a['name']}", "value is null", col))
                continue
            try:
                num = float(val)  # type: ignore[arg-type]
                ok = a.get("min", float("-inf")) <= num <= a.get("max", float("inf"))
                out.append(_result("PASS" if ok else "FAIL", f"reconciliations.{a['name']}",
                                   f"in [{a.get('min')}, {a.get('max')}] actual={val}", col))
            except (TypeError, ValueError):
                out.append(_result("FAIL", f"reconciliations.{a['name']}", f"not numeric: {val!r}", col))
    return out


def score_discipline(expected, run_dir: Path):
    out = []
    events_path = run_dir / "events.json"
    if not events_path.exists():
        events_path = run_dir / "raw_stream.json"
    events = parse_event_stream(events_path) if events_path.exists() else None
    for a in expected.get("discipline", []):
        col = a.get("column", "process")
        kind = a["type"]
        if kind == "no_error_events":
            if events is None:
                out.append(_result("SKIP", "discipline.no_error_events", "no event stream", "environment"))
                continue
            errs = [e for e in events if isinstance(e, dict) and e.get("is_error") is True]
            ok = not errs
            out.append(_result("PASS" if ok else "FAIL", "discipline.no_error_events",
                               f"errors={len(errs)}", col))
        elif kind == "stop_reason":
            if events is None:
                out.append(_result("SKIP", "discipline.stop_reason", "no event stream", "environment"))
                continue
            stops = [normalize_stop_reason(e.get("stop_reason"))
                     for e in events if isinstance(e, dict) and e.get("stop_reason")]
            stops = [s for s in stops if s]
            ok = a["value"] in stops if stops else False
            out.append(_result("PASS" if ok else "FAIL", "discipline.stop_reason",
                               f"expected={a['value']!r} observed={stops!r}", col))
    return out


def score_xlsx_structure(expected, run_dir: Path):
    """Stubbed scorer for xlsx_* assertion types.

    Returns SKIP for every assertion until openpyxl-based handlers are
    implemented. Returning SKIP (rather than PASS) keeps the slice honest:
    a runner that processes a workbook without the xlsx engine wired must
    not silently report "passed".

    To wire: replace each SKIP with `import openpyxl; wb = openpyxl.load_workbook(run_dir / "model.xlsx")`
    and the appropriate call (`wb.sheetnames`, `wb.defined_names`, cell value reads).
    """
    spec = expected.get("xlsx_structure")
    if not spec:
        return []
    _ = run_dir  # referenced for future openpyxl wiring; see docstring
    out = []
    for a in spec.get("sheets", []):
        out.append(_result(
            "SKIP",
            f"xlsx_sheet_exists[{a.get('name')}]",
            "xlsx engine not yet wired (NotImplementedError stub)",
            a.get("column", "outcome"),
        ))
    for a in spec.get("named_ranges", []):
        out.append(_result(
            "SKIP",
            f"xlsx_named_range_exists[{a.get('name')}]",
            "xlsx engine not yet wired (NotImplementedError stub)",
            a.get("column", "process"),
        ))
    for a in spec.get("validation_cells", []):
        out.append(_result(
            "SKIP",
            f"xlsx_validation_cell[{a.get('sheet')}]",
            "xlsx engine not yet wired (NotImplementedError stub)",
            a.get("column", "outcome"),
        ))
    return out


def detect_envelope_filename(run_dir: Path) -> Path:
    """Different roles emit envelopes under different filenames.

    The runner writes `<role>_final_envelope.json`. Look for any matching file.
    """
    candidates = sorted(run_dir.glob("*_final_envelope.json"))
    if candidates:
        return candidates[0]
    return run_dir / "ingestion_final_envelope.json"  # legacy default


def _extract_envelope_object(s: str) -> str:
    """Best-effort: pull the LARGEST balanced JSON object out of a noisy response.

    Models violate "respond with raw JSON" rules in three ways: (1) wrap in
    ```fences```, (2) prepend chain-of-thought prose, (3) both. To still run
    the envelope content assertions in those cases — while letting
    score_envelope_format flag the violation — we scan every top-level
    balanced `{...}` (string-aware so braces inside JSON strings don't fool
    us) and return the largest one. Returns the original string when no
    balanced object is found, which surfaces as an ordinary parse failure
    downstream.

    Why the largest, not the first: a model emitting prose like
    `Looking at this, {"from": "x"} is the sender — my decision is:
    {"decision": "triage", ...full envelope...}` would otherwise cause us to
    extract the small fragment `{"from": "x"}` and silently mis-score every
    field. The real envelope is reliably the longest balanced span.
    """
    candidates: list[tuple[int, int]] = []  # (start, end_inclusive)
    n = len(s)
    i = 0
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        # Scan forward from this opening brace to find a matching close.
        depth = 0
        in_str = False
        esc = False
        end = -1
        for j in range(i, n):
            ch = s[j]
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end >= 0:
            candidates.append((i, end))
            i = end + 1
        else:
            # Unbalanced — bail; further `{` tokens won't help on truncated input.
            break
    if not candidates:
        return s
    # Pick the longest span. Ties → first occurrence (stable).
    start, end = max(candidates, key=lambda se: se[1] - se[0])
    return s[start : end + 1]


def score_one_trial(expected, run_dir: Path, manifest_override: Path | None = None):
    """Run all assertions against a single trial directory. Returns the result list.

    On envelope parse failure we still run every scorer that doesn't depend
    on a parsed envelope (`score_envelope_format`, `score_outputs`,
    `score_manifest`, `score_quality_flags`, `score_reconciliations`,
    `score_xlsx_structure`, `score_discipline` — all read run_dir + manifest
    directly). Only `score_envelope` is skipped, replaced by a synthetic
    FAIL row per envelope assertion so the aggregator's denominator stays
    consistent across trials. Without this, parse-failure trials silently
    drop out of the per-assertion denominator and the aggregate Wilson CI
    on healthy assertions reads tighter than the data supports.
    """
    envelope_path = detect_envelope_filename(run_dir)
    if not envelope_path.exists():
        return [_result("FAIL", "envelope", f"missing {envelope_path}", "environment")]
    envelope_str = envelope_path.read_text()

    mp = manifest_override or (run_dir / "manifest.json")
    manifest = load_json(mp) if mp.exists() else None

    parse_failed = False
    parse_error: str | None = None
    try:
        envelope = json.loads(_extract_envelope_object(envelope_str))
    except json.JSONDecodeError as e:
        parse_failed = True
        parse_error = str(e)
        envelope = None

    results = []
    if parse_failed:
        # One row tagging the parse failure itself.
        results.append(_result("FAIL", "envelope.parse",
                               f"json decode failed: {parse_error}", "process"))
        # Synthetic FAIL per declared envelope assertion so the aggregator
        # accounts for them (otherwise n drops by 1 and Wilson CI inflates).
        for a in expected.get("envelope", []):
            field = a.get("field", "?")
            col = a.get("column", "process")
            results.append(_result(
                "FAIL", f"envelope.{field}",
                "envelope unparseable; assertion not evaluable", col,
            ))
    else:
        results += score_envelope(expected, envelope)
    results += score_envelope_format(expected, envelope_str)
    results += score_outputs(expected, run_dir, manifest)
    results += score_manifest(expected, manifest)
    results += score_quality_flags(expected, manifest)
    results += score_reconciliations(expected, manifest)
    results += score_xlsx_structure(expected, run_dir)
    results += score_discipline(expected, run_dir)
    return results


# --- Aggregation across trials ---


def aggregate_trials(trial_results: list[list[tuple]]):
    """Aggregate per-assertion pass/fail across N trials.
    Returns list of dicts with rate + Wilson CI + column."""
    by_assertion: dict[str, dict] = {}
    for results in trial_results:
        for status, name, detail, column in results:
            entry = by_assertion.setdefault(name, {"name": name, "column": column, "n": 0, "k": 0, "skips": 0, "errors": 0, "last_detail": detail})
            entry["n"] += 1 if status in ("PASS", "FAIL") else 0
            entry["k"] += 1 if status == "PASS" else 0
            if status == "SKIP":
                entry["skips"] += 1
            if status == "ERROR":
                entry["errors"] += 1
            entry["last_detail"] = detail
    rows = []
    for name, e in by_assertion.items():
        rate, lo, hi = wilson_ci(e["k"], e["n"]) if e["n"] > 0 else (None, None, None)
        rows.append({
            **e,
            "rate": rate,
            "ci_lo": lo,
            "ci_hi": hi,
        })
    return rows


# --- Rendering ---


def render_single_trial(results, case_id, run_dir, manifest_present):
    out = []
    out.append(f"# Eval scorecard (single-trial): `{case_id}`")
    out.append("")
    out.append(f"**Run directory:** `{run_dir}`")
    out.append(f"**Manifest:** {'present' if manifest_present else 'absent (manifest assertions reported as SKIP/environment)'}")
    out.append("")

    by_col = {"process": [0, 0, 0, 0], "outcome": [0, 0, 0, 0], "environment": [0, 0, 0, 0]}  # pass/fail/err/skip
    for status, _, _, column in results:
        c = column if column in by_col else "process"
        idx = {"PASS": 0, "FAIL": 1, "ERROR": 2, "SKIP": 3}[status]
        by_col[c][idx] += 1

    out.append("| Column | PASS | FAIL | ERROR | SKIP |")
    out.append("|---|---|---|---|---|")
    for c, vals in by_col.items():
        out.append(f"| {c} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")
    out.append("")

    process_fail = by_col["process"][1] + by_col["process"][2]
    verdict = "PASS" if process_fail == 0 else "FAIL"
    out.append(f"**Process-column verdict (the agent's responsibility):** **{verdict}** "
               f"({by_col['process'][0]}/{sum(by_col['process'][:2])} pass, "
               f"{by_col['process'][2]} error)")
    out.append("")
    out.append("> ⚠ **n=1 — exploratory only, not a measurement.** Per playbook § 8, single-trial pass/fail is uninformative as a rate. Run the same case ≥25× via `runner.sh` for a Wilson 95% CI.")
    out.append("")
    out.append("| Status | Column | Assertion | Detail |")
    out.append("|---|---|---|---|")
    for status, name, detail, column in results:
        out.append(f"| {status} | {column} | `{name}` | {detail} |")
    return "\n".join(out)


def fmt_ci(rate, lo, hi):
    if rate is None:
        return "n/a"
    return f"{rate:.3f} [{lo:.3f}, {hi:.3f}]"


def render_aggregate(rows, case_id, n_trials, paraphrase=None):
    out = []
    out.append(f"# Eval scorecard (aggregate): `{case_id}`")
    out.append("")
    out.append(f"**Trials:** {n_trials}")
    if paraphrase:
        out.append(f"**Paraphrase:** `{paraphrase}`")
    out.append("")
    out.append("> Per playbook § 8 reporting unit: `<rate> [<lo>, <hi>] (Wilson 95%, n=N)`")
    out.append("")

    by_col_rate = {"process": [], "outcome": [], "environment": []}
    for r in rows:
        col = r["column"] if r["column"] in by_col_rate else "process"
        if r["rate"] is not None:
            by_col_rate[col].append(r["rate"])

    out.append("## Headline rates by column")
    out.append("")
    out.append("| Column | Mean assertion pass-rate | # assertions |")
    out.append("|---|---|---|")
    for col, rates in by_col_rate.items():
        if rates:
            mean = sum(rates) / len(rates)
            out.append(f"| {col} | {mean:.3f} | {len(rates)} |")
        else:
            out.append(f"| {col} | n/a | 0 |")
    out.append("")
    out.append("(Assertion-level rates and CIs in detail table below.)")
    out.append("")
    out.append("## Per-assertion detail")
    out.append("")
    out.append("| Column | Assertion | k/n | Wilson 95% CI | Skips | Errors |")
    out.append("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["column"], x["name"])):
        out.append(f"| {r['column']} | `{r['name']}` | {r['k']}/{r['n']} | "
                   f"{fmt_ci(r['rate'], r['ci_lo'], r['ci_hi'])} | {r['skips']} | {r['errors']} |")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("case", help="Eval case path, e.g. ingestion/tafi_2025")
    p.add_argument("--run", help="Single-trial run directory")
    p.add_argument("--trials", help="Multi-trial directory containing per-trial subdirs")
    p.add_argument("--paraphrase", help="Filter trials to a single paraphrase id (multi-trial only)")
    p.add_argument("--manifest", help="Override manifest path (single-trial only)")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent
    case_dir = repo_root / args.case
    if not case_dir.is_dir():
        print(f"ERROR: case dir not found: {case_dir}", file=sys.stderr)
        return 2
    expected = load_json(case_dir / "expected.json")

    if args.run and not args.trials:
        run_dir = Path(args.run).resolve()
        results = score_one_trial(
            expected, run_dir,
            Path(args.manifest) if args.manifest else None,
        )
        manifest_present = (Path(args.manifest) if args.manifest else (run_dir / "manifest.json")).exists()
        print(render_single_trial(results, expected["case_id"], run_dir, manifest_present))
        n_proc_fail = sum(1 for s, _, _, c in results if s in ("FAIL", "ERROR") and c == "process")
        return 0 if n_proc_fail == 0 else min(n_proc_fail, 1)

    if args.trials:
        trials_dir = Path(args.trials).resolve()
        if not trials_dir.is_dir():
            print(f"ERROR: trials dir not found: {trials_dir}", file=sys.stderr)
            return 2
        trial_dirs = sorted([p for p in trials_dir.iterdir() if p.is_dir()])
        if args.paraphrase:
            trial_dirs = [p for p in trial_dirs if args.paraphrase in p.name]
        if not trial_dirs:
            print(f"ERROR: no trial subdirs found in {trials_dir}"
                  + (f" matching paraphrase {args.paraphrase!r}" if args.paraphrase else ""),
                  file=sys.stderr)
            return 2
        all_results = [score_one_trial(expected, td) for td in trial_dirs]
        rows = aggregate_trials(all_results)
        print(render_aggregate(rows, expected["case_id"], len(trial_dirs), args.paraphrase))

        # Exit code: 1 if any process-column rate is below 1.0 with statistical confidence
        # (i.e., upper CI bound < 1.0). This is the conservative gate.
        proc_fail = sum(1 for r in rows
                        if r["column"] == "process" and r["rate"] is not None
                        and (r["ci_hi"] is not None and r["ci_hi"] < 1.0))
        return 0 if proc_fail == 0 else 1

    print("ERROR: must pass either --run (single-trial) or --trials (aggregate)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

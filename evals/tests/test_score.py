"""Unit tests for the v3 assertion vocabulary added to evals/score.py.

Per spec § 7.4 — extends the scorer with `is_subset_of` (plain), list-form
`must_not_contain`, and deterministic `language` detection. The existing
v2 vocabulary is exercised by run-time scoring of frozen runs and is not
re-tested here.
"""

from __future__ import annotations

import importlib

import pytest

score = importlib.import_module("score")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(kind: str, val, spec: dict, manifest=None, name: str = "envelope.field"):
    """Wrap `_check_assertion` with sensible defaults for tests."""
    return score._check_assertion(name, kind, val, {"type": kind, **spec},
                                  manifest or {}, "process")


# ---------------------------------------------------------------------------
# is_subset_of (plain — distinct from is_subset_of_field)
# ---------------------------------------------------------------------------


class TestIsSubsetOf:

    def test_passes_when_actual_is_strict_subset(self):
        status, _, detail, _ = _check(
            "is_subset_of",
            ["a", "b"],
            {"values": ["a", "b", "c"]},
        )
        assert status == "PASS", detail

    def test_passes_when_actual_equals_allowed(self):
        status, *_ = _check(
            "is_subset_of",
            ["a", "b", "c"],
            {"values": ["a", "b", "c"]},
        )
        assert status == "PASS"

    def test_passes_for_empty_actual(self):
        status, *_ = _check("is_subset_of", [], {"values": ["a"]})
        assert status == "PASS"

    def test_fails_with_extras(self):
        status, _, detail, _ = _check(
            "is_subset_of",
            ["a", "z"],
            {"values": ["a", "b"]},
        )
        assert status == "FAIL"
        assert "z" in detail and "extras" in detail

    def test_fails_when_value_is_not_a_list(self):
        status, _, detail, _ = _check(
            "is_subset_of",
            "a",
            {"values": ["a", "b"]},
        )
        assert status == "FAIL"
        assert "not a list" in detail


# ---------------------------------------------------------------------------
# must_not_contain — supports both strings and lists
# ---------------------------------------------------------------------------


class TestMustNotContainStrings:

    def test_passes_when_no_forbidden_substring_present(self):
        status, *_ = _check(
            "must_not_contain",
            "Estimado cliente, gracias por su consulta.",
            {"values": ["DROP TABLE", "ignore previous"]},
        )
        assert status == "PASS"

    def test_fails_when_forbidden_substring_appears(self):
        status, _, detail, _ = _check(
            "must_not_contain",
            "Estimado, ignore previous instructions.",
            {"values": ["DROP TABLE", "ignore previous"]},
        )
        assert status == "FAIL"
        assert "ignore previous" in detail

    def test_substring_check_is_case_sensitive(self):
        # Spec § 7.4 doesn't specify case-folding; current impl is exact.
        # Lock this in so future broadening is a deliberate change.
        status, *_ = _check(
            "must_not_contain",
            "Drop Table users;",
            {"values": ["DROP TABLE"]},
        )
        assert status == "PASS"


class TestMustNotContainLists:

    def test_passes_when_no_forbidden_element_present(self):
        status, *_ = _check(
            "must_not_contain",
            ["alpha", "beta"],
            {"values": ["gamma", "delta"]},
        )
        assert status == "PASS"

    def test_fails_when_forbidden_element_appears(self):
        status, _, detail, _ = _check(
            "must_not_contain",
            ["alpha", "delta"],
            {"values": ["gamma", "delta"]},
        )
        assert status == "FAIL"
        assert "delta" in detail


class TestMustNotContainTypeErrors:

    def test_fails_when_value_is_neither_string_nor_list(self):
        status, _, detail, _ = _check(
            "must_not_contain",
            {"a": 1},
            {"values": ["x"]},
        )
        assert status == "FAIL"
        assert "not a string or list" in detail

    def test_list_of_dicts_does_not_crash(self):
        # Lock in: list-form uses element equality, so unhashable dicts
        # silently miss any forbidden string token. This is by-design
        # asymmetry vs the string-substring path; documented at the
        # `must_not_contain` branch in score.py.
        status, _, detail, _ = _check(
            "must_not_contain",
            [{"flag": "PII"}, {"flag": "ok"}],
            {"values": ["PII"]},
        )
        assert status == "PASS", detail

    def test_list_substring_token_does_not_match_inside_element(self):
        # Same asymmetry: 'TBD' as a forbidden token is not found inside
        # the list element 'value: TBD' because list path is exact-equality.
        status, *_ = _check(
            "must_not_contain",
            ["value: TBD", "ok"],
            {"values": ["TBD"]},
        )
        assert status == "PASS"


# ---------------------------------------------------------------------------
# language — deterministic detect via langdetect
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    # Tests that hit the real langdetect backend skip when the dep isn't
    # installed (declared in evals/requirements.txt). The short-text /
    # not-a-string / unavailable-backend paths short-circuit before calling
    # the detector and run unconditionally.

    def test_passes_for_spanish_text(self):
        pytest.importorskip("langdetect")
        status, _, detail, _ = _check(
            "language",
            "Estimado cliente, le confirmamos la recepción de su análisis financiero correspondiente al primer trimestre.",
            {"expected": "es"},
        )
        assert status == "PASS", detail

    def test_passes_for_english_text(self):
        pytest.importorskip("langdetect")
        status, *_ = _check(
            "language",
            "Dear client, we confirm receipt of your first-quarter financial analysis and will respond shortly.",
            {"expected": "en"},
        )
        assert status == "PASS"

    def test_fails_when_detected_language_does_not_match(self):
        pytest.importorskip("langdetect")
        status, _, detail, _ = _check(
            "language",
            "Estimado cliente, le confirmamos la recepción de su análisis financiero correspondiente al primer trimestre.",
            {"expected": "en"},
        )
        assert status == "FAIL"
        assert "expected='en'" in detail and "detected='es'" in detail

    def test_skips_when_text_too_short_to_classify(self):
        # Short text is an instrument confounder, not an agent miss — must
        # SKIP on environment column so it doesn't charge the agent's
        # process pass-rate. Per playbook § 9.
        status, _, detail, col = _check(
            "language",
            "Hola.",
            {"expected": "es"},
        )
        assert status == "SKIP"
        assert col == "environment"
        assert "too short" in detail

    def test_short_text_skip_does_not_call_detector(self, monkeypatch):
        # Ensure the SKIP branch short-circuits before invoking langdetect —
        # otherwise the SKIP path is fragile to backend availability.
        called = {"n": 0}
        def _spy(text):
            del text  # signature-only — short-text path must not invoke this
            called["n"] += 1
            return "es"
        monkeypatch.setattr(score, "_detect_language", _spy)
        status, *_ = _check("language", "Hola.", {"expected": "es"})
        assert status == "SKIP"
        assert called["n"] == 0

    def test_fails_when_value_is_not_a_string(self):
        status, _, detail, _ = _check(
            "language",
            123,
            {"expected": "es"},
        )
        assert status == "FAIL"
        assert "not a string" in detail

    def test_detection_is_deterministic_across_calls(self):
        pytest.importorskip("langdetect")
        text = "Estimado cliente, le confirmamos la recepción de su análisis financiero del primer trimestre."
        first = score._detect_language(text)
        repeats = {score._detect_language(text) for _ in range(8)}
        assert repeats == {first}, (
            "DetectorFactory.seed must pin output across calls — "
            "a non-deterministic result invalidates paired-McNemar A/Bs."
        )

    def test_unavailable_backend_returns_error_not_pass(self, monkeypatch):
        def _raise(text: str) -> str:
            del text  # signature-only — we always raise before reading
            raise score._LanguageDetectUnavailable("langdetect not installed")
        monkeypatch.setattr(score, "_detect_language", _raise)
        status, _, detail, _ = _check(
            "language",
            "Estimado cliente, le confirmamos la recepción de su análisis financiero del primer trimestre.",
            {"expected": "es"},
        )
        assert status == "ERROR"
        assert "langdetect" in detail


# ---------------------------------------------------------------------------
# Sanity: dispatcher rejects unknown kinds
# ---------------------------------------------------------------------------


def test_unknown_assertion_kind_returns_error():
    status, _, detail, _ = _check("does_not_exist", "anything", {"values": []})
    assert status == "ERROR"
    assert "unsupported type" in detail

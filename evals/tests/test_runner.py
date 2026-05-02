"""Unit tests for the role-aware helpers added to evals/runner.py.

Per spec § 7.4 — runner.py learns to spin a resolver session, which has
different shape than ingestion (single inline kickoff, no resources.json,
no container artifacts to capture). The branching helpers tested here
are the contract surface; the per-trial network flow is covered by
end-to-end smoke runs against a deployed resolver agent.
"""

from __future__ import annotations

import importlib
import json

import pytest

runner = importlib.import_module("runner")


# ---------------------------------------------------------------------------
# detect_role
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case,expected", [
    ("resolver/new_contract", "resolver"),
    ("resolver/continuation", "resolver"),
    ("ingestion/tafi_2025", "ingestion"),
    ("transversal_modeler/tafi_2025", "ingestion"),  # default fallback
    ("foo", "ingestion"),
])
def test_detect_role(case, expected):
    assert runner.detect_role(case) == expected


# ---------------------------------------------------------------------------
# kickoff_path — picks the right filename per role
# ---------------------------------------------------------------------------


def test_kickoff_path_resolver_uses_singular_kickoff(tmp_path):
    p = runner.kickoff_path(tmp_path, "canonical", "resolver")
    assert p.name == "kickoff.json"


def test_kickoff_path_ingestion_includes_paraphrase(tmp_path):
    p = runner.kickoff_path(tmp_path, "v1_canonical", "ingestion")
    assert p.name == "kickoff_v1_canonical.json"


# ---------------------------------------------------------------------------
# list_paraphrases — resolver branch
# ---------------------------------------------------------------------------


class TestListParaphrasesResolver:

    @pytest.fixture
    def case_dir(self, tmp_path):
        (tmp_path / "kickoff.json").write_text("{}")
        return tmp_path

    def test_returns_canonical_with_no_request(self, case_dir):
        assert runner.list_paraphrases(case_dir, None, "resolver") == ["canonical"]

    def test_returns_canonical_with_all(self, case_dir):
        assert runner.list_paraphrases(case_dir, "all", "resolver") == ["canonical"]

    def test_accepts_explicit_canonical(self, case_dir):
        assert runner.list_paraphrases(case_dir, "canonical", "resolver") == ["canonical"]

    def test_rejects_unknown_paraphrase(self, case_dir):
        with pytest.raises(RuntimeError, match="no paraphrase fan-out"):
            runner.list_paraphrases(case_dir, "v1_canonical", "resolver")

    def test_fails_when_kickoff_missing(self, tmp_path):
        with pytest.raises(RuntimeError, match="No kickoff.json"):
            runner.list_paraphrases(tmp_path, None, "resolver")


# ---------------------------------------------------------------------------
# list_paraphrases — ingestion branch (regression-only)
# ---------------------------------------------------------------------------


class TestListParaphrasesIngestion:

    @pytest.fixture
    def case_dir(self, tmp_path):
        (tmp_path / "kickoff_v1_canonical.json").write_text("{}")
        (tmp_path / "kickoff_v2_directive.json").write_text("{}")
        return tmp_path

    def test_returns_all_sorted_with_none(self, case_dir):
        assert runner.list_paraphrases(case_dir, None, "ingestion") == [
            "v1_canonical", "v2_directive",
        ]

    def test_filters_to_selected(self, case_dir):
        assert runner.list_paraphrases(case_dir, "v2_directive", "ingestion") == [
            "v2_directive",
        ]

    def test_rejects_unknown(self, case_dir):
        with pytest.raises(RuntimeError, match="Unknown paraphrase"):
            runner.list_paraphrases(case_dir, "v7_does_not_exist", "ingestion")

    def test_fails_when_no_kickoffs(self, tmp_path):
        with pytest.raises(RuntimeError, match="No kickoff_"):
            runner.list_paraphrases(tmp_path, None, "ingestion")


# ---------------------------------------------------------------------------
# Resolver slice fixture: shape of the canonical kickoff
# ---------------------------------------------------------------------------


def test_resolver_kickoff_is_serializable_json():
    """Sanity: every resolver slice's kickoff parses cleanly. Catches a
    common authoring foot-gun (smart-quote substitution from chat clients).
    """
    from pathlib import Path
    runner_file = runner.__file__
    assert runner_file is not None  # for pyright — script modules have __file__
    evals_dir = Path(runner_file).resolve().parent
    for kickoff in (evals_dir / "resolver").glob("*/kickoff.json"):
        json.loads(kickoff.read_text())  # raises if malformed

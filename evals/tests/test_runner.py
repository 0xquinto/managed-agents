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


# ---------------------------------------------------------------------------
# _to_api_event_shape — translation + strict validation
# ---------------------------------------------------------------------------


class TestToApiEventShape:

    def test_sdk_string_content_translates_to_api_shape(self):
        out = runner._to_api_event_shape({
            "type": "user",
            "message": {"role": "user", "content": "hello"},
        })
        assert out == {
            "type": "user.message",
            "content": [{"type": "text", "text": "hello"}],
        }

    def test_sdk_list_content_keeps_blocks_swaps_wrapper(self):
        blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        out = runner._to_api_event_shape({
            "type": "user",
            "message": {"role": "user", "content": blocks},
        })
        assert out == {"type": "user.message", "content": blocks}

    def test_already_api_shape_is_identity(self):
        ev = {"type": "user.message", "content": [{"type": "text", "text": "hi"}]}
        assert runner._to_api_event_shape(ev) is ev

    def test_non_user_event_is_identity(self):
        ev = {"type": "user.tool_confirmation", "tool_use_id": "x"}
        assert runner._to_api_event_shape(ev) is ev

    def test_sdk_with_string_message_raises(self):
        # Earlier code would silently forward this and the CLI would 400 with
        # an opaque "invalid event type" message far from the source.
        with pytest.raises(RuntimeError, match="missing dict 'message'"):
            runner._to_api_event_shape({"type": "user", "message": "wrong"})

    def test_sdk_with_dict_content_raises(self):
        with pytest.raises(RuntimeError, match="must be str or list"):
            runner._to_api_event_shape({
                "type": "user",
                "message": {"role": "user", "content": {"text": "wrong"}},
            })

    def test_sdk_with_none_content_raises(self):
        with pytest.raises(RuntimeError, match="must be str or list"):
            runner._to_api_event_shape({
                "type": "user",
                "message": {"role": "user", "content": None},
            })


# ---------------------------------------------------------------------------
# _normalize_stop_reason + poll_until_idle
# ---------------------------------------------------------------------------


class TestNormalizeStopReason:

    def test_dict_form_unwraps_type_field(self):
        # The SDK wire shape — verified against captured trial events on
        # 2026-05-02. Earlier `f"idle:{stop}"` produced literal
        # "idle:{'type': 'end_turn'}" garbage strings.
        assert runner._normalize_stop_reason({"type": "end_turn"}) == "end_turn"

    def test_string_form_passthrough(self):
        assert runner._normalize_stop_reason("end_turn") == "end_turn"

    def test_none_returns_none(self):
        assert runner._normalize_stop_reason(None) is None

    def test_dict_without_type_returns_none(self):
        assert runner._normalize_stop_reason({"reason": "x"}) is None

    def test_unexpected_shape_returns_none(self):
        assert runner._normalize_stop_reason(42) is None


class TestPollUntilIdle:

    @pytest.fixture(autouse=True)
    def _patch_sleep(self, monkeypatch):
        # Tests must not actually sleep.
        def _no_sleep(s):
            del s
        monkeypatch.setattr(runner.time, "sleep", _no_sleep)

    def _patch_events(self, monkeypatch, events_seq):
        """events_seq is a list of event-lists, one per poll iteration."""
        it = iter(events_seq)
        def _list(sid):
            del sid
            return next(it)
        monkeypatch.setattr(runner, "list_events", _list)

    def test_clean_end_turn_returns_true_idle_end_turn(self, monkeypatch):
        self._patch_events(monkeypatch, [[
            {"type": "user.message"},
            {"type": "agent.message"},
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
        ]])
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=10)
        assert ok is True
        assert status == "idle:end_turn"

    def test_requires_action_is_NOT_clean(self, monkeypatch):
        # The bug class C1 surfaced: requires_action means the agent halted
        # needing tool confirmation it can't take. NOT a clean trial.
        self._patch_events(monkeypatch, [[
            {"type": "session.status_idle", "stop_reason": {"type": "requires_action"}},
        ]])
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=10)
        assert ok is False
        assert status == "idle:requires_action"

    def test_retries_exhausted_is_NOT_clean(self, monkeypatch):
        self._patch_events(monkeypatch, [[
            {"type": "session.status_idle",
             "stop_reason": {"type": "retries_exhausted"}},
        ]])
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=10)
        assert ok is False
        assert status == "idle:retries_exhausted"

    def test_terminated_is_NOT_clean(self, monkeypatch):
        self._patch_events(monkeypatch, [[
            {"type": "session.status_terminated"},
        ]])
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=10)
        assert ok is False
        assert status == "terminated"

    def test_timeout_returns_false(self, monkeypatch):
        # Empty event stream every poll → never sees terminal event.
        ticks = {"n": 0}
        def fake_time():
            ticks["n"] += 1
            return float(ticks["n"]) * 1000.0  # blow past any deadline
        monkeypatch.setattr(runner.time, "time", fake_time)
        def _empty_list(sid):
            del sid
            return []
        monkeypatch.setattr(runner, "list_events", _empty_list)
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=0)
        assert ok is False
        assert status == "timeout"

    def test_skips_non_dict_events(self, monkeypatch):
        # Defensive — list_events occasionally returns garbage shapes.
        self._patch_events(monkeypatch, [[
            "garbage",
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
        ]])
        ok, status = runner.poll_until_idle("sesn_x", timeout_seconds=10)
        assert ok is True
        assert status == "idle:end_turn"


# ---------------------------------------------------------------------------
# run_ant beta-header injection
# ---------------------------------------------------------------------------


class TestRunAntBetaInjection:

    def _run(self, monkeypatch, args):
        captured: list[list[str]] = []

        class _FakeResult:
            returncode = 0
            stdout = "{}"
            stderr = ""

        def fake_run(cmd, capture_output=True, text=True):
            del capture_output, text
            captured.append(list(cmd))
            return _FakeResult()

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        runner.run_ant(args)
        assert captured, "subprocess.run was never invoked"
        return captured[-1]

    def test_beta_subcommand_gets_header_injected(self, monkeypatch):
        cmd = self._run(monkeypatch, ["beta:agents", "list"])
        assert "--beta" in cmd
        assert "managed-agents-2026-04-01" in cmd

    def test_explicit_beta_is_respected(self, monkeypatch):
        cmd = self._run(monkeypatch, ["beta:agents", "list", "--beta", "managed-agents-2026-04-01-research-preview"])
        # No double-injection.
        assert cmd.count("--beta") == 1
        assert "managed-agents-2026-04-01-research-preview" in cmd
        assert "managed-agents-2026-04-01" not in cmd

    def test_non_beta_subcommand_gets_no_injection(self, monkeypatch):
        cmd = self._run(monkeypatch, ["messages", "create"])
        assert "--beta" not in cmd


# ---------------------------------------------------------------------------
# Resolver kickoff fixtures sanity
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# build_resources — memory_store branch
# ---------------------------------------------------------------------------


class TestBuildResourcesMemoryStores:

    def _write_resources(self, tmp_path, spec):
        (tmp_path / "resources.json").write_text(json.dumps(spec))
        return tmp_path

    def test_files_only_keeps_legacy_shape(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "files": [
                {"file_id_param": "tafi_pdf", "mount_path": "input/x.pdf",
                 "default_file_id": "file_aaa"},
            ],
        })
        resources, files, memory = runner.build_resources(case_dir, {}, {})
        assert resources == [{"type": "file", "file_id": "file_aaa", "mount_path": "input/x.pdf"}]
        assert files == {"tafi_pdf": "file_aaa"}
        assert memory == {}

    def test_memory_store_default_id_picked_up(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [
                {"memory_store_id_param": "insignia_memory",
                 "default_memory_store_id": "mem_aaa",
                 "access": "read_only"},
            ],
        })
        resources, files, memory = runner.build_resources(case_dir, {}, {})
        assert files == {}
        assert memory == {"insignia_memory": "mem_aaa"}
        assert resources == [{
            "type": "memory_store",
            "memory_store_id": "mem_aaa",
            "access": "read_only",
        }]

    def test_memory_store_override_wins_over_default(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [
                {"memory_store_id_param": "insignia_memory",
                 "default_memory_store_id": "mem_aaa"},
            ],
        })
        resources, _, memory = runner.build_resources(
            case_dir, {}, {"insignia_memory": "mem_zzz"},
        )
        assert memory == {"insignia_memory": "mem_zzz"}
        assert resources[0]["memory_store_id"] == "mem_zzz"

    def test_memory_store_default_access_is_read_only(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [
                {"memory_store_id_param": "x", "default_memory_store_id": "mem_aaa"},
            ],
        })
        resources, _, _ = runner.build_resources(case_dir, {}, {})
        assert resources[0]["access"] == "read_only"

    def test_memory_store_invalid_access_raises(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [
                {"memory_store_id_param": "x", "default_memory_store_id": "mem_aaa",
                 "access": "owner"},
            ],
        })
        with pytest.raises(RuntimeError, match="access='owner'"):
            runner.build_resources(case_dir, {}, {})

    def test_memory_store_missing_id_raises(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [{"memory_store_id_param": "x"}],
        })
        with pytest.raises(RuntimeError, match="No memory_store_id"):
            runner.build_resources(case_dir, {}, {})

    def test_optional_prompt_passes_through(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "memory_stores": [
                {"memory_store_id_param": "x", "default_memory_store_id": "mem_aaa",
                 "prompt": "Check priors before reading uploads."},
            ],
        })
        resources, _, _ = runner.build_resources(case_dir, {}, {})
        assert resources[0]["prompt"] == "Check priors before reading uploads."

    def test_files_and_memory_emit_in_order(self, tmp_path):
        case_dir = self._write_resources(tmp_path, {
            "files": [{"file_id_param": "p", "mount_path": "x", "default_file_id": "file_a"}],
            "memory_stores": [{"memory_store_id_param": "m", "default_memory_store_id": "mem_a"}],
        })
        resources, _, _ = runner.build_resources(case_dir, {}, {})
        assert [r["type"] for r in resources] == ["file", "memory_store"]


class TestParseMemoryOverrides:

    def test_parses_kv_pairs(self):
        assert runner.parse_memory_overrides(["a=mem_aa", "b=mem_bb"]) == {
            "a": "mem_aa", "b": "mem_bb",
        }

    def test_rejects_missing_equals(self):
        with pytest.raises(ValueError, match="--memory-store"):
            runner.parse_memory_overrides(["bad"])


def test_resolver_kickoff_is_serializable_json():
    """Sanity: every resolver slice's kickoff parses cleanly. Catches a
    common authoring foot-gun (smart-quote substitution from chat clients).
    """
    from pathlib import Path
    runner_file = runner.__file__
    assert runner_file is not None  # for pyright — script modules have __file__
    evals_dir = Path(runner_file).resolve().parent
    kickoffs = list((evals_dir / "resolver").glob("*/kickoff.json"))
    assert kickoffs, "expected ≥1 resolver kickoff under evals/resolver/*/kickoff.json"
    for kickoff in kickoffs:
        json.loads(kickoff.read_text())  # raises if malformed

"""Scheduler entrypoint tests — smoke + CLI exit-code contract.

Asserts:
  - `run_one_cycle` against an empty inbox + LocalFilesystemBackend memory +
    a nop sessions backend produces a CycleSummary with `errors == []`.
  - `cli_main` returns 0 on a clean cycle, 1 when summary has errors, 2 when
    Settings.from_env raises on missing env vars.
  - `python -m poller` imports cleanly (the __main__.py shim).

The orchestrator-level integration test in `test_orchestrator.py` already
covers the per-component wiring; this file covers the scheduler + CLI shell
layer that actually ships as `python -m poller`.
"""

from __future__ import annotations

import importlib
import io
import json
import os
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from poller.adapters.anthropic_sessions import SessionResult
from poller.adapters.memory import LocalFilesystemBackend
from poller.config import Settings
from poller.orchestrator import CycleSummary
from poller.scheduler import (
    _build_orchestrator,
    cli_main,
    run_one_cycle,
)


class _EmptyInboxGraph:
    """Graph fake whose inbox is always empty; raises on any other Graph op.

    Anything beyond mail-list / replies-list reaching this fake means the
    orchestrator did MORE than it should have for an empty inbox — the test
    surfaces that loudly via NotImplementedError.
    """

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[Any], str]:
        return [], delta_link or "delta-token-init"

    async def list_channel_replies(
        self, *, team_id: str, channel_id: str, message_id: str
    ) -> list[Any]:
        return []

    async def download_attachment(
        self, *, message_id: str, attachment_id: str
    ) -> bytes:
        raise NotImplementedError

    async def list_message_attachments(
        self, *, message_id: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def upload_to_onedrive_via_session(
        self,
        *,
        drive_item_path: str,
        content: bytes,
        chunk_size_bytes: int = 5 * 1024 * 1024,
    ) -> str:
        raise NotImplementedError

    async def post_channel_message(
        self, *, team_id: str, channel_id: str, body_text: str
    ) -> str:
        raise NotImplementedError

    async def send_mail(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body_text: str,
        in_reply_to_message_id: str | None = None,
    ) -> None:
        raise NotImplementedError


class _SentinelSessionsBackend:
    """Sessions backend that fails loudly if invoked — no emails ⇒ no calls."""

    async def run_session(
        self,
        *,
        agent_id: str,
        environment_id: str | None,
        kickoff_text: str,
        cache_control_blocks: list[dict[str, Any]] | None = None,
        capture_files: list[str] | None = None,
        beta_headers: list[str] | None = None,
    ) -> SessionResult:
        del agent_id, environment_id, kickoff_text
        del cache_control_blocks, capture_files, beta_headers
        raise AssertionError(
            "smoke test invoked sessions backend on an empty inbox — "
            "orchestrator wiring leaked work past EmailGate"
        )


@pytest.fixture
def _smoke_settings(tmp_path: Path) -> Iterator[Settings]:
    """A complete Settings instance for the smoke path."""
    yield Settings(
        graph_tenant_id="t",
        graph_client_id="c",
        graph_client_secret="s",
        watched_inbox="contracts@insignia-test.com",
        anthropic_api_key="sk-ant-test",
        insignia_resolver_agent_id="agent_resolver_test",
        insignia_ingestion_v3_agent_id="agent_ingestion_test",
        insignia_memory_store_id="mem_test",
        insignia_environment_id="env_test",
    )


async def test_run_one_cycle_with_empty_inbox_yields_clean_summary(
    _smoke_settings: Settings, tmp_path: Path
) -> None:
    orchestrator = _build_orchestrator(
        settings=_smoke_settings,
        graph=_EmptyInboxGraph(),
        memory_backend=LocalFilesystemBackend(root=tmp_path),
        sessions_backend=_SentinelSessionsBackend(),
        clock=lambda: 1_700_000_000.0,
    )
    summary = await orchestrator.run_cycle()

    assert summary.errors == []
    assert summary.emails_seen == 0
    assert summary.decisions_applied == 0
    assert summary.triage_cards_posted == 0
    assert summary.draft_cards_posted == 0


async def test_run_one_cycle_helper_threads_settings_through(
    _smoke_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_one_cycle(settings=...) bypasses Settings.from_env."""
    captured: dict[str, Any] = {}

    def _spy_build(*, settings: Settings, **kwargs: Any) -> Any:
        captured["settings"] = settings
        # Inject the test fakes for the smoke path.
        kwargs.update(
            graph=_EmptyInboxGraph(),
            memory_backend=LocalFilesystemBackend(root=tmp_path),
            sessions_backend=_SentinelSessionsBackend(),
            clock=lambda: 1_700_000_000.0,
        )
        return _build_orchestrator(settings=settings, **kwargs)

    monkeypatch.setattr("poller.scheduler._build_orchestrator", _spy_build)

    summary = await run_one_cycle(settings=_smoke_settings)

    assert captured["settings"] is _smoke_settings
    assert summary.errors == []


def test_cli_main_returns_zero_on_clean_cycle(
    fake_env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cli_main exits 0 when run_one_cycle returns a no-error summary."""
    del fake_env  # patched into os.environ by the fixture

    async def _fake_run_one_cycle(*, settings: Settings) -> CycleSummary:
        del settings
        return CycleSummary(emails_seen=0, errors=[])

    monkeypatch.setattr("poller.scheduler.run_one_cycle", _fake_run_one_cycle)

    out = io.StringIO()
    with redirect_stdout(out):
        rc = cli_main([])

    assert rc == 0
    payload = json.loads(out.getvalue())
    assert payload["errors"] == []
    assert payload["emails_seen"] == 0


def test_cli_main_returns_one_when_summary_has_errors(
    fake_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cycle errors are operational failures, not configuration errors → exit 1."""
    del fake_env

    async def _fake_run_one_cycle(*, settings: Settings) -> CycleSummary:
        del settings
        return CycleSummary(emails_seen=1, errors=["resolver session timed out"])

    monkeypatch.setattr("poller.scheduler.run_one_cycle", _fake_run_one_cycle)

    with redirect_stdout(io.StringIO()):
        rc = cli_main([])

    assert rc == 1


def test_cli_main_returns_two_on_missing_env_vars() -> None:
    """Missing env vars are configuration errors — distinct exit code so an
    Azure Function host can alert on them differently from cycle errors."""
    err = io.StringIO()
    with patch.dict(os.environ, {}, clear=True), redirect_stderr(err):
        rc = cli_main([])

    assert rc == 2
    assert "configuration error" in err.getvalue()
    assert "GRAPH_TENANT_ID" in err.getvalue()  # surfaces the missing var name


def test_main_module_imports_cleanly() -> None:
    """`python -m poller` resolves to poller/__main__.py — verify it imports."""
    mod = importlib.import_module("poller.__main__")
    # The module re-exports cli_main from scheduler; confirm it's reachable.
    assert mod.cli_main is cli_main

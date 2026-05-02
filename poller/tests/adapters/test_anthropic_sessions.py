"""AnthropicSessionsAdapter tests — protocol shape, beta header pinning, TTL coercion."""

from __future__ import annotations

from typing import Any

from poller.adapters.anthropic_sessions import (
    AnthropicSessionsAdapter,
    AnthropicSessionsBackend,
    SessionResult,
    StubAnthropicSessionsBackend,
)
from poller.config import EXTENDED_CACHE_TTL_BETA_HEADER


def test_backend_is_a_protocol() -> None:
    assert getattr(AnthropicSessionsBackend, '_is_protocol', False)


def test_backend_protocol_declares_run_session() -> None:
    assert hasattr(AnthropicSessionsBackend, "run_session")


class _RecordingBackend:
    """Captures the kwargs passed into run_session."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_result = SessionResult(
            session_id="sess_abc",
            stop_reason="end_turn",
            final_message_text='{"hello": "world"}',
            captured_files={},
            is_error=False,
        )

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
        self.calls.append(
            {
                "agent_id": agent_id,
                "environment_id": environment_id,
                "kickoff_text": kickoff_text,
                "cache_control_blocks": cache_control_blocks,
                "capture_files": capture_files,
                "beta_headers": beta_headers,
            }
        )
        return self.next_result


async def test_adapter_pins_extended_cache_ttl_beta_header() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id="env_y",
        kickoff_text="hi",
    )

    assert len(backend.calls) == 1
    headers = backend.calls[0]["beta_headers"]
    assert EXTENDED_CACHE_TTL_BETA_HEADER in headers


async def test_adapter_appends_extra_beta_headers() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
        extra_beta_headers=["managed-agents-2026-04-01"],
    )

    headers = backend.calls[0]["beta_headers"]
    assert EXTENDED_CACHE_TTL_BETA_HEADER in headers
    assert "managed-agents-2026-04-01" in headers


async def test_adapter_coerces_cache_control_to_one_hour_ttl() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
        cache_control_blocks=[{"type": "ephemeral"}],
    )

    blocks = backend.calls[0]["cache_control_blocks"]
    assert blocks == [{"type": "ephemeral", "ttl": "1h"}]


async def test_adapter_preserves_explicit_ttl() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
        cache_control_blocks=[{"type": "ephemeral", "ttl": "5m"}],
    )

    blocks = backend.calls[0]["cache_control_blocks"]
    assert blocks == [{"type": "ephemeral", "ttl": "5m"}]


async def test_adapter_passes_none_when_no_cache_control() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
        cache_control_blocks=None,
    )

    assert backend.calls[0]["cache_control_blocks"] is None


async def test_adapter_forwards_capture_files() -> None:
    backend = _RecordingBackend()
    adapter = AnthropicSessionsAdapter(backend=backend)

    await adapter.run(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
        capture_files=["/mnt/session/out/INS-2026-007/manifest.json"],
    )

    assert backend.calls[0]["capture_files"] == [
        "/mnt/session/out/INS-2026-007/manifest.json"
    ]


async def test_stub_backend_raises_until_gate_0a_resolves() -> None:
    backend = StubAnthropicSessionsBackend(api_key="sk-ant-test")
    import pytest

    with pytest.raises(NotImplementedError, match="Gate 0a"):
        await backend.run_session(
            agent_id="agent_x",
            environment_id=None,
            kickoff_text="hi",
        )

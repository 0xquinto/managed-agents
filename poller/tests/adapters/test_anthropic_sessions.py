"""AnthropicSessionsAdapter tests — protocol shape, beta header pinning, TTL coercion.

Also covers `AnthropicSDKSessionsBackend` — the live SDK-backed implementation
of the protocol. Tests use a hand-rolled fake SDK client (not pytest-mock) so
that the event-stream contract is explicit rather than buried in mock attrs.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest

from poller.adapters.anthropic_sessions import (
    AnthropicSDKSessionsBackend,
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


async def test_stub_backend_is_a_sentinel_that_always_raises() -> None:
    backend = StubAnthropicSessionsBackend(api_key="sk-ant-test")

    with pytest.raises(NotImplementedError, match="sentinel"):
        await backend.run_session(
            agent_id="agent_x",
            environment_id=None,
            kickoff_text="hi",
        )


# ---------------------------------------------------------------------------
# AnthropicSDKSessionsBackend — fake-SDK harness + scenario tests
# ---------------------------------------------------------------------------


def _msg_event(text: str) -> SimpleNamespace:
    """Construct an `agent.message` event mirroring the SDK shape."""
    return SimpleNamespace(
        type="agent.message",
        content=[SimpleNamespace(type="text", text=text)],
    )


def _tool_use_event(*, name: str, **tool_input: object) -> SimpleNamespace:
    """Construct an `agent.tool_use` event."""
    return SimpleNamespace(type="agent.tool_use", name=name, input=tool_input)


def _idle_event(stop_reason_type: str = "end_turn") -> SimpleNamespace:
    """Construct a `session.status_idle` event with the given stop reason."""
    return SimpleNamespace(
        type="session.status_idle",
        stop_reason=SimpleNamespace(type=stop_reason_type),
    )


def _terminated_event() -> SimpleNamespace:
    return SimpleNamespace(type="session.status_terminated")


def _error_event() -> SimpleNamespace:
    return SimpleNamespace(type="session.error")


@dataclass
class _FakeStream:
    """Minimal SDK-compatible stream: iterable + context-manager."""

    events: list[Any]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.events)

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@dataclass
class _FakeSDKClient:
    """Hand-rolled SDK substitute. Records all calls; returns scripted events.

    Each `script` entry is the per-`run_session` event sequence to yield
    from `events.stream`. `create_raises` lets a test trigger the BadRequest
    fallback path on the *first* sessions.create call only.
    """

    script: list[list[Any]] = field(default_factory=list)
    create_raises: list[Exception] = field(default_factory=list)
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    send_calls: list[dict[str, Any]] = field(default_factory=list)
    stream_calls: list[dict[str, Any]] = field(default_factory=list)
    _next_session_index: int = 0

    @property
    def beta(self) -> _FakeSDKClient:
        return self

    @property
    def sessions(self) -> _FakeSDKClient:
        return self

    @property
    def events(self) -> _FakeSDKClient:
        return self

    # --- sessions.create ---
    def create(
        self,
        *,
        agent: str,
        environment_id: str,
        betas: list[str],
    ) -> SimpleNamespace:
        self.create_calls.append(
            {"agent": agent, "environment_id": environment_id, "betas": list(betas)}
        )
        if self.create_raises:
            err = self.create_raises.pop(0)
            raise err
        sid = f"sess_fake_{self._next_session_index:03d}"
        self._next_session_index += 1
        return SimpleNamespace(id=sid)

    # --- sessions.events.send ---
    def send(
        self,
        session_id: str,
        *,
        events: list[Any],
        betas: list[str],
    ) -> None:
        self.send_calls.append(
            {"session_id": session_id, "events": events, "betas": list(betas)}
        )

    # --- sessions.events.stream ---
    @contextmanager
    def stream(
        self, session_id: str, *, betas: list[str]
    ) -> Iterator[_FakeStream]:
        self.stream_calls.append({"session_id": session_id, "betas": list(betas)})
        events = self.script.pop(0) if self.script else []
        yield _FakeStream(events=events)


def _bad_request(message: str) -> anthropic.BadRequestError:
    """Build a real BadRequestError without going over the wire."""
    response = SimpleNamespace(
        request=None,
        status_code=400,
        headers={},
    )
    return anthropic.BadRequestError(
        message=message,
        response=response,  # type: ignore[arg-type]
        body=None,
    )


def _backend(
    fake: _FakeSDKClient,
    *,
    default_environment_id: str | None = None,
) -> AnthropicSDKSessionsBackend:
    """Cast the fake SDK client to satisfy the typed `client=Anthropic` param.

    The fake duck-types every method the backend touches; the cast is purely
    for the type checker.
    """
    return AnthropicSDKSessionsBackend(
        client=cast(anthropic.Anthropic, fake),
        default_environment_id=default_environment_id,
    )


async def test_sdk_backend_happy_path_concatenates_message_text() -> None:
    fake = _FakeSDKClient(
        script=[
            [
                _msg_event("hello "),
                _msg_event("world"),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_resolver",
        environment_id="env_1",
        kickoff_text="kickoff",
        beta_headers=[EXTENDED_CACHE_TTL_BETA_HEADER, "managed-agents-2026-04-01"],
    )

    assert result.session_id == "sess_fake_000"
    assert result.final_message_text == "hello world"
    assert result.stop_reason == "end_turn"
    assert result.is_error is False
    assert result.captured_files == {}

    assert fake.create_calls == [
        {
            "agent": "agent_resolver",
            "environment_id": "env_1",
            "betas": [EXTENDED_CACHE_TTL_BETA_HEADER, "managed-agents-2026-04-01"],
        }
    ]
    assert fake.send_calls[0]["session_id"] == "sess_fake_000"
    assert fake.send_calls[0]["events"] == [
        {"type": "user.message", "content": [{"type": "text", "text": "kickoff"}]}
    ]


async def test_sdk_backend_captures_write_tool_input_for_requested_paths() -> None:
    target = "/mnt/session/out/INS-2026-007/manifest.json"
    other = "/mnt/session/out/INS-2026-007/normalized/pnl_raw.csv"
    fake = _FakeSDKClient(
        script=[
            [
                _tool_use_event(name="write", file_path=target, content='{"ok":true}'),
                _tool_use_event(name="write", file_path=other, content="not requested"),
                _msg_event("done"),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_ingestion",
        environment_id="env_1",
        kickoff_text="kickoff",
        capture_files=[target],
    )

    assert result.captured_files == {target: b'{"ok":true}'}
    assert other not in result.captured_files


async def test_sdk_backend_does_not_capture_edit_tool_events() -> None:
    """Edit events emit `{file_path, old_str, new_str}` not `content` — capturing
    them would clobber the previous Write with an empty `content` default. v3
    ingestion's prompt mandates `write` for files in `capture_files`, so Edit is
    deliberately not in the capture set."""
    target = "/mnt/session/out/INS-2026-007/manifest.json"
    fake = _FakeSDKClient(
        script=[
            [
                _tool_use_event(name="write", file_path=target, content='{"v": 1}'),
                _tool_use_event(
                    name="edit", file_path=target, old_str='"v": 1', new_str='"v": 2'
                ),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="kickoff",
        capture_files=[target],
    )

    # The Write captured; the Edit was ignored — manifest is the original write.
    assert result.captured_files == {target: b'{"v": 1}'}


async def test_sdk_backend_captures_bytes_content_without_re_encoding() -> None:
    """Round-trip a binary content payload to guard against silent str() coercion."""
    target = "/mnt/session/out/INS-2026-007/normalized/data.bin"
    blob = b"\x00\x01\xfe\xff PNG-or-similar-binary"
    fake = _FakeSDKClient(
        script=[
            [
                _tool_use_event(name="write", file_path=target, content=blob),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="kickoff",
        capture_files=[target],
    )

    assert result.captured_files[target] == blob, "bytes must round-trip verbatim"


async def test_sdk_backend_ignores_writes_to_paths_not_in_capture_set() -> None:
    """If capture_files is None or empty, no tool_use writes get captured —
    guards against `set(None)` regressions in the capture-paths branch."""
    fake = _FakeSDKClient(
        script=[
            [
                _tool_use_event(name="write", file_path="/x", content="y"),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="kickoff",
        # capture_files omitted entirely (defaults to None)
    )

    assert result.captured_files == {}


async def test_sdk_backend_marks_requires_action_idle_as_error() -> None:
    """`session.status_idle` with `stop_reason: requires_action` means the agent
    paused for HITL — NOT a clean completion. Backend must surface is_error=True
    while preserving the stop_reason so the caller can distinguish it from
    end_turn or retries_exhausted."""
    fake = _FakeSDKClient(
        script=[
            [
                _msg_event("waiting on confirmation"),
                _idle_event("requires_action"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x", environment_id="env_1", kickoff_text="hi"
    )

    assert result.stop_reason == "requires_action"
    assert result.is_error is True


async def test_sdk_backend_marks_retries_exhausted_idle_as_error() -> None:
    fake = _FakeSDKClient(
        script=[[_idle_event("retries_exhausted")]]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x", environment_id="env_1", kickoff_text="hi"
    )

    assert result.stop_reason == "retries_exhausted"
    assert result.is_error is True


async def test_sdk_backend_treats_terminated_without_idle_as_error() -> None:
    fake = _FakeSDKClient(
        script=[
            [
                _msg_event("partial"),
                _terminated_event(),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="hi",
    )

    assert result.stop_reason == "terminated"
    assert result.is_error is True
    assert result.final_message_text == "partial"


async def test_sdk_backend_propagates_session_error_event() -> None:
    fake = _FakeSDKClient(
        script=[
            [
                _msg_event("partial"),
                _error_event(),
                _idle_event("end_turn"),
            ]
        ]
    )
    backend = _backend(fake, default_environment_id="env_1")

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="hi",
    )

    assert result.is_error is True
    assert result.stop_reason == "end_turn"


async def test_sdk_backend_falls_back_when_extended_cache_ttl_beta_rejected() -> None:
    fake = _FakeSDKClient(
        script=[
            [_msg_event("ok"), _idle_event("end_turn")],
        ],
        create_raises=[_bad_request("Unrecognized beta: extended-cache-ttl-2025-04-11")],
    )
    backend = _backend(fake, default_environment_id="env_1")

    assert backend.extended_cache_ttl_disabled is False

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="hi",
        beta_headers=[EXTENDED_CACHE_TTL_BETA_HEADER, "managed-agents-2026-04-01"],
    )

    assert result.stop_reason == "end_turn"
    assert backend.extended_cache_ttl_disabled is True

    # Two create calls: first with the beta (raised), second without.
    assert len(fake.create_calls) == 2
    assert EXTENDED_CACHE_TTL_BETA_HEADER in fake.create_calls[0]["betas"]
    assert EXTENDED_CACHE_TTL_BETA_HEADER not in fake.create_calls[1]["betas"]
    assert "managed-agents-2026-04-01" in fake.create_calls[1]["betas"]
    # Subsequent send + stream use the trimmed betas too.
    assert EXTENDED_CACHE_TTL_BETA_HEADER not in fake.send_calls[0]["betas"]
    assert EXTENDED_CACHE_TTL_BETA_HEADER not in fake.stream_calls[0]["betas"]


async def test_sdk_backend_entitlement_fallback_is_sticky_across_calls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sticky-fallback contract: the header is dropped on every subsequent call
    AND the warning logs exactly once across N calls (otherwise we drown an
    operator's alert pipeline with the same line per cycle)."""
    fake = _FakeSDKClient(
        script=[
            [_idle_event("end_turn")],
            [_idle_event("end_turn")],
        ],
        create_raises=[_bad_request("Unrecognized beta: extended-cache-ttl-2025-04-11")],
    )
    backend = _backend(fake, default_environment_id="env_1")

    with caplog.at_level("WARNING", logger="poller.adapters.anthropic_sessions"):
        await backend.run_session(
            agent_id="a",
            environment_id="env_1",
            kickoff_text="hi",
            beta_headers=[EXTENDED_CACHE_TTL_BETA_HEADER],
        )
        await backend.run_session(
            agent_id="a",
            environment_id="env_1",
            kickoff_text="hi",
            beta_headers=[EXTENDED_CACHE_TTL_BETA_HEADER],
        )

    # Three create calls: 1st failed (with header), 2nd retry (without), 3rd
    # second-run-session (without). The header is dropped before the SDK is
    # touched on the second run.
    assert len(fake.create_calls) == 3
    assert EXTENDED_CACHE_TTL_BETA_HEADER not in fake.create_calls[2]["betas"]
    # Exactly one warning across both run_session calls.
    fallback_warnings = [
        rec for rec in caplog.records
        if rec.levelname == "WARNING" and "Gate 0a entitlement not" in rec.message
    ]
    assert len(fallback_warnings) == 1, "warning should fire once, not per cycle"


async def test_sdk_backend_does_not_fall_back_for_unrelated_400s() -> None:
    fake = _FakeSDKClient(
        create_raises=[_bad_request("Invalid agent_id")],
    )
    backend = _backend(fake, default_environment_id="env_1")

    with pytest.raises(anthropic.BadRequestError, match="Invalid agent_id"):
        await backend.run_session(
            agent_id="agent_bad",
            environment_id="env_1",
            kickoff_text="hi",
            beta_headers=[EXTENDED_CACHE_TTL_BETA_HEADER],
        )

    assert backend.extended_cache_ttl_disabled is False
    assert len(fake.create_calls) == 1


async def test_sdk_backend_requires_environment_id() -> None:
    fake = _FakeSDKClient()
    backend = _backend(fake)  # no default_environment_id

    with pytest.raises(ValueError, match="environment_id"):
        await backend.run_session(
            agent_id="agent_x",
            environment_id=None,
            kickoff_text="hi",
        )


async def test_sdk_backend_falls_through_default_environment_id() -> None:
    fake = _FakeSDKClient(script=[[_idle_event("end_turn")]])
    backend = _backend(fake, default_environment_id="env_default")

    await backend.run_session(
        agent_id="agent_x",
        environment_id=None,
        kickoff_text="hi",
    )

    assert fake.create_calls[0]["environment_id"] == "env_default"


def test_sdk_backend_requires_client_or_api_key() -> None:
    with pytest.raises(ValueError, match="client.*api_key"):
        AnthropicSDKSessionsBackend()


@dataclass
class _SlowFakeStream:
    """Stream that blocks the worker thread until cancelled — simulates a wedged
    session that emits no idle/terminated event before the timeout fires."""

    def __iter__(self) -> Iterator[Any]:
        # Sleep effectively-forever; asyncio.wait_for cancels the wrapping task,
        # the to_thread future is abandoned, and we return.
        import time

        time.sleep(60)  # well beyond the test's max_session_seconds
        return iter([])

    def __enter__(self) -> _SlowFakeStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        del exc_info


@dataclass
class _WedgedSDKClient(_FakeSDKClient):
    """Fake whose stream blocks instead of yielding events."""

    @contextmanager
    def stream(self, session_id: str, *, betas: list[str]) -> Iterator[_FakeStream]:
        self.stream_calls.append({"session_id": session_id, "betas": list(betas)})
        # Yield the slow stream as if it were a normal _FakeStream (duck-typed).
        yield _SlowFakeStream()  # type: ignore[misc]


async def test_sdk_backend_times_out_on_wedged_stream() -> None:
    """A stream that never sends idle / terminated must surface a TimeoutError as
    `is_error=True, stop_reason="timeout"` rather than block the cron forever."""
    fake = _WedgedSDKClient()
    backend = AnthropicSDKSessionsBackend(
        client=cast(anthropic.Anthropic, fake),
        default_environment_id="env_1",
        max_session_seconds=0.1,
    )

    result = await backend.run_session(
        agent_id="agent_x",
        environment_id="env_1",
        kickoff_text="hi",
    )

    assert result.is_error is True
    assert result.stop_reason == "timeout"
    assert result.captured_files == {}

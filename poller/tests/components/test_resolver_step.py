"""ResolverStep tests — kickoff serialization, cache_control, envelope parsing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from poller.adapters.anthropic_sessions import (
    AnthropicSessionsAdapter,
    SessionResult,
)
from poller.components.resolver_step import ResolverStep
from poller.exceptions import AnthropicError
from poller.schemas import (
    AttachmentMeta,
    EmailMeta,
    RegistryRow,
    ResolverEnvelope,
    ResolverKickoff,
)

_SHA = "9" * 64


class _FakeBackend:
    def __init__(self, *, final_message_text: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self.final_message_text = final_message_text

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
        return SessionResult(
            session_id="sess_resolver_1",
            stop_reason="end_turn",
            final_message_text=self.final_message_text,
            captured_files={},
            is_error=False,
        )


def _kickoff() -> ResolverKickoff:
    return ResolverKickoff(
        email=EmailMeta.model_validate(
            {
                "from": "ana@tafi.com.ar",
                "to": ["contracts@insignia.com"],
                "cc": [],
                "subject": "Análisis Q1",
                "conversationId": "conv-1",
                "messageId": "msg-1",
                "body_text": "Hola",
                "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
            }
        ),
        attachments=[
            AttachmentMeta(
                message_attachment_id="att-1",
                filename="EF.pdf",
                sha256=_SHA,
                size=1234,
                content_type="application/pdf",
            )
        ],
        registry=[
            RegistryRow.model_validate(
                {
                    "contract_id": "INS-2026-007",
                    "client_name": "Tafi",
                    "sender_addresses": ["ana@tafi.com.ar"],
                    "subject_tag": None,
                    "onedrive_path": "/Contracts/Tafi/",
                    "teams_channel_id": "19:abc@thread.tacv2",
                    "status": "open",
                    "opened_at": datetime(2026, 4, 12, 9, 0, 0, tzinfo=UTC),
                }
            )
        ],
        attachment_hashes_seen_for_candidate={"INS-2026-007": []},
    )


async def test_resolver_step_continuation_decision() -> None:
    envelope_json = json.dumps(
        {
            "decision": "continuation",
            "contract_id": "INS-2026-007",
            "confidence": 0.92,
            "rationale_short": "subject + sender match",
        }
    )
    backend = _FakeBackend(final_message_text=envelope_json)
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(
        sessions=adapter,
        agent_id="agent_resolver",
        environment_id="env_resolver",
    )

    outcome = await step.run(_kickoff())

    assert isinstance(outcome.envelope, ResolverEnvelope)
    assert outcome.envelope.decision == "continuation"
    assert outcome.envelope.contract_id == "INS-2026-007"
    assert outcome.session_id == "sess_resolver_1"
    assert outcome.stop_reason == "end_turn"


async def test_resolver_step_sends_cache_control_block() -> None:
    envelope_json = '{"decision": "triage", "confidence": 0.5, "rationale_short": "x"}'
    backend = _FakeBackend(final_message_text=envelope_json)
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    await step.run(_kickoff())

    blocks = backend.calls[0]["cache_control_blocks"]
    assert blocks == [{"type": "ephemeral", "ttl": "1h"}]


async def test_resolver_step_serializes_kickoff_with_alias_from() -> None:
    envelope_json = '{"decision": "triage", "confidence": 0.5, "rationale_short": "x"}'
    backend = _FakeBackend(final_message_text=envelope_json)
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    await step.run(_kickoff())

    body = json.loads(backend.calls[0]["kickoff_text"])
    assert body["email"]["from"] == "ana@tafi.com.ar"
    assert "from_" not in body["email"]


async def test_resolver_step_strips_json_code_fence() -> None:
    envelope_json = (
        "```json\n"
        '{"decision": "triage", "confidence": 0.5, "rationale_short": "x"}\n'
        "```"
    )
    backend = _FakeBackend(final_message_text=envelope_json)
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    outcome = await step.run(_kickoff())

    assert outcome.envelope.decision == "triage"


async def test_resolver_step_raises_on_invalid_json() -> None:
    backend = _FakeBackend(final_message_text="not json")
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    with pytest.raises(AnthropicError, match="non-JSON"):
        await step.run(_kickoff())


async def test_resolver_step_raises_on_invalid_envelope_shape() -> None:
    backend = _FakeBackend(final_message_text='{"foo": "bar"}')
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    with pytest.raises(AnthropicError, match="failed validation"):
        await step.run(_kickoff())


class _ErroredSessionBackend:
    """Backend that returns is_error=True (e.g. session.error mid-stream or
    requires_action / retries_exhausted / timeout). The step must raise."""

    def __init__(self, *, stop_reason: str = "requires_action") -> None:
        self.stop_reason = stop_reason

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
        return SessionResult(
            session_id="sess_errored",
            stop_reason=self.stop_reason,
            final_message_text="",
            captured_files={},
            is_error=True,
        )


async def test_resolver_step_raises_when_session_reports_is_error() -> None:
    """is_error=True must surface as an AnthropicError instead of being silently
    forwarded into ResolverOutcome — otherwise the orchestrator posts a
    status_ok card on a session that never completed cleanly."""
    adapter = AnthropicSessionsAdapter(backend=_ErroredSessionBackend())
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    with pytest.raises(AnthropicError, match="reported errors mid-stream"):
        await step.run(_kickoff())


async def test_resolver_step_error_message_includes_stop_reason() -> None:
    """The stop_reason is non-redundant info — `requires_action` vs `timeout`
    vs `retries_exhausted` are all is_error=True but mean different things."""
    adapter = AnthropicSessionsAdapter(
        backend=_ErroredSessionBackend(stop_reason="timeout")
    )
    step = ResolverStep(sessions=adapter, agent_id="agent_resolver")

    with pytest.raises(AnthropicError, match="timeout"):
        await step.run(_kickoff())

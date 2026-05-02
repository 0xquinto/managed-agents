"""IngestionStep tests — manifest capture path, envelope+manifest parse, error paths."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from poller.adapters.anthropic_sessions import (
    AnthropicSessionsAdapter,
    SessionResult,
)
from poller.components.ingestion_step import IngestionStep
from poller.exceptions import AnthropicError, SchemaValidationError
from poller.schemas import (
    EmailContextExcerpt,
    EmailMeta,
    IngestionKickoff,
    MemoryPaths,
)


def _kickoff(contract_id: str = "INS-2026-007") -> IngestionKickoff:
    email_meta = EmailMeta.model_validate(
        {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Análisis Q1",
            "conversationId": "conv-1",
            "messageId": "msg-1",
            "body_text": "Hola, te envío los EE.FF.",
            "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
        }
    )
    return IngestionKickoff(
        contract_id=contract_id,
        client_name="Tafi",
        input_files=["/mnt/session/uploads/EF.pdf"],
        email_context=EmailContextExcerpt.from_email_meta(email_meta, language="es"),
        memory_paths=MemoryPaths(
            priors="/mnt/memory/priors/INS-2026-007.json",
            tone_examples_dir="/mnt/memory/tone_examples/",
        ),
    )


def _make_manifest_bytes(
    contract_id: str = "INS-2026-007",
    *,
    missing_fields: list[str] | None = None,
    client_email_draft: dict[str, Any] | None = None,
) -> bytes:
    manifest: dict[str, Any] = {
        "contract_id": contract_id,
        "entity": {"name": "Tafi"},
        "periods": ["2024", "2025"],
        "pdf_extraction": {"method": "pdfplumber", "pages": 12, "avg_chars_per_page": 1800},
        "csv_extraction": {"rows": 0, "cols": 0},
        "files_classified": [],
        "normalized_paths": {},
        "quality_flags": [],
        "reconciliations": {
            "balance_sheet_2025": {"diff": 0.0, "balanced": True},
            "balance_sheet_2024": {"diff": 0.0, "balanced": True},
            "cashflow_2025": {"diff": 0.0, "reconciled": True},
            "cashflow_2024": {"diff": 0.0, "reconciled": True},
        },
        "missing_fields": missing_fields or [],
        "outputs": [],
    }
    if client_email_draft is not None:
        manifest["client_email_draft"] = client_email_draft
    return json.dumps(manifest).encode("utf-8")


class _FakeBackend:
    def __init__(
        self,
        *,
        final_message_text: str,
        captured_files: dict[str, bytes],
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.final_message_text = final_message_text
        self.captured_files = captured_files

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
            session_id="sess_ingest_1",
            stop_reason="end_turn",
            final_message_text=self.final_message_text,
            captured_files=self.captured_files,
            is_error=False,
        )


async def test_ingestion_step_happy_path() -> None:
    envelope_json = json.dumps(
        {
            "status": "ok",
            "normalized_dir": "/mnt/session/out/INS-2026-007/normalized",
            "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
            "missing_fields": [],
        }
    )
    captured = {
        "/mnt/session/out/INS-2026-007/manifest.json": _make_manifest_bytes()
    }
    backend = _FakeBackend(
        final_message_text=envelope_json,
        captured_files=captured,
    )
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = IngestionStep(
        sessions=adapter,
        agent_id="agent_ingestion",
        environment_id="env_ingestion",
    )

    outcome = await step.run(_kickoff())

    assert outcome.envelope.status == "ok"
    assert outcome.manifest.contract_id == "INS-2026-007"
    assert outcome.session_id == "sess_ingest_1"
    assert outcome.stop_reason == "end_turn"
    assert backend.calls[0]["capture_files"] == [
        "/mnt/session/out/INS-2026-007/manifest.json"
    ]


async def test_ingestion_step_missing_manifest_raises() -> None:
    envelope_json = json.dumps(
        {
            "status": "ok",
            "normalized_dir": "/mnt/session/out/INS-2026-007/normalized",
            "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
            "missing_fields": [],
        }
    )
    backend = _FakeBackend(
        final_message_text=envelope_json,
        captured_files={},  # manifest missing
    )
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    with pytest.raises(SchemaValidationError, match="did not produce"):
        await step.run(_kickoff())


async def test_ingestion_step_invalid_manifest_json_raises() -> None:
    envelope_json = json.dumps(
        {
            "status": "ok",
            "normalized_dir": "/mnt/session/out/INS-2026-007/normalized",
            "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
            "missing_fields": [],
        }
    )
    backend = _FakeBackend(
        final_message_text=envelope_json,
        captured_files={
            "/mnt/session/out/INS-2026-007/manifest.json": b"not json"
        },
    )
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    with pytest.raises(SchemaValidationError, match="not valid JSON"):
        await step.run(_kickoff())


async def test_ingestion_step_envelope_invalid_raises() -> None:
    backend = _FakeBackend(
        final_message_text="not json at all",
        captured_files={
            "/mnt/session/out/INS-2026-007/manifest.json": _make_manifest_bytes()
        },
    )
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    with pytest.raises(AnthropicError, match="non-JSON"):
        await step.run(_kickoff())


async def test_ingestion_step_blocked_with_email_draft_validates_subset() -> None:
    """missing_fields_referenced ⊆ missing_fields is enforced by ManifestV3."""
    envelope_json = json.dumps(
        {
            "status": "blocked",
            "normalized_dir": "/mnt/session/out/INS-2026-007/normalized",
            "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
            "missing_fields": ["dictamen", "memoria"],
        }
    )
    draft = {
        "to": ["ana@tafi.com.ar"],
        "cc": [],
        "subject": "Faltan documentos para completar el análisis",
        "in_reply_to_message_id": "msg-1",
        "language": "es",
        "body": (
            "Hola Ana, gracias por enviar el balance. Para terminar el análisis "
            "nos falta el dictamen del auditor y la memoria. ¿Podrías enviarlos?"
        ),
        "missing_fields_referenced": ["dictamen", "memoria"],
        "tone_examples_consulted": [],
    }
    captured = {
        "/mnt/session/out/INS-2026-007/manifest.json": _make_manifest_bytes(
            missing_fields=["dictamen", "memoria"],
            client_email_draft=draft,
        )
    }
    backend = _FakeBackend(
        final_message_text=envelope_json, captured_files=captured
    )
    adapter = AnthropicSessionsAdapter(backend=backend)
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    outcome = await step.run(_kickoff())

    assert outcome.envelope.status == "blocked"
    assert outcome.manifest.client_email_draft is not None
    assert outcome.manifest.client_email_draft.language == "es"


class _ErroredSessionBackend:
    """Backend returns is_error=True; step must raise rather than parse."""

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


async def test_ingestion_step_raises_when_session_reports_is_error() -> None:
    """is_error=True must surface as AnthropicError so the orchestrator records
    the failure in summary.errors and skips the status_ok card. Parsing the
    (empty) envelope/manifest is not the right error message — it would point
    a debugger at JSON parsing rather than at the real session failure."""
    adapter = AnthropicSessionsAdapter(backend=_ErroredSessionBackend())
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    with pytest.raises(AnthropicError, match="reported errors mid-stream"):
        await step.run(_kickoff())


async def test_ingestion_step_error_includes_stop_reason() -> None:
    adapter = AnthropicSessionsAdapter(
        backend=_ErroredSessionBackend(stop_reason="timeout")
    )
    step = IngestionStep(sessions=adapter, agent_id="agent_ingestion")

    with pytest.raises(AnthropicError, match="timeout"):
        await step.run(_kickoff())

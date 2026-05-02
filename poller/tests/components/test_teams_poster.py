"""TeamsCardPoster tests — body content, channel routing, callback id propagation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from poller.adapters.graph import ChannelReply
from poller.components.manifest_step import ManifestPost
from poller.components.teams_poster import (
    CardPostResult,
    ChannelRef,
    TeamsCardPoster,
)
from poller.exceptions import SchemaValidationError
from poller.schemas import (
    EmailMeta,
    InferredNewContract,
    ManifestV3,
    ResolverEnvelope,
    TriageCandidate,
    TriagePayload,
)

_TRIAGE = ChannelRef(team_id="team-1", channel_id="chan-triage")
_CONTRACT = ChannelRef(team_id="team-1", channel_id="chan-contract-tafi")


class _FakeGraph:
    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []
        self._next_id = 0

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[Any], str]:
        raise NotImplementedError

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
        self,
        *,
        team_id: str,
        channel_id: str,
        body_text: str,
    ) -> str:
        self._next_id += 1
        msg_id = f"msg-{self._next_id}"
        self.posted.append(
            {
                "team_id": team_id,
                "channel_id": channel_id,
                "body_text": body_text,
                "message_id": msg_id,
            }
        )
        return msg_id

    async def list_channel_replies(
        self, *, team_id: str, channel_id: str, message_id: str
    ) -> list[ChannelReply]:
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


def _manifest(
    *,
    contract_id: str = "INS-2026-007",
    missing_fields: list[str] | None = None,
    client_email_draft: dict[str, Any] | None = None,
) -> ManifestV3:
    payload: dict[str, Any] = {
        "contract_id": contract_id,
        "entity": {"name": "Tafi"},
        "periods": ["2024", "2025"],
        "pdf_extraction": {
            "method": "pdfplumber",
            "pages": 12,
            "avg_chars_per_page": 1800,
        },
        "csv_extraction": {"rows": 0, "cols": 0},
        "files_classified": [],
        "normalized_paths": {},
        "quality_flags": [{"code": "stale", "field": "x"}],
        "reconciliations": {
            "balance_sheet_2025": {"diff": 0.0, "balanced": True},
            "balance_sheet_2024": {"diff": 0.0, "balanced": True},
            "cashflow_2025": {"diff": 0.0, "reconciled": True},
            "cashflow_2024": {"diff": 0.0, "reconciled": True},
        },
        "missing_fields": missing_fields or [],
        "outputs": [{"path": "/x.json"}],
    }
    if client_email_draft is not None:
        payload["client_email_draft"] = client_email_draft
    return ManifestV3.model_validate(payload)


async def test_post_status_ok_routes_to_contract_channel() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)
    post = ManifestPost(
        kind="status_ok",
        contract_id="INS-2026-007",
        summary="Ingestion complete; 0 quality flags",
        manifest=_manifest(),
    )

    result = await poster.post_status_ok(
        post=post, channel=_CONTRACT, callback_id="cb-1"
    )

    assert isinstance(result, CardPostResult)
    assert result.kind == "status_ok"
    assert result.team_id == "team-1"
    assert result.channel_id == "chan-contract-tafi"
    assert result.callback_id == "cb-1"

    assert len(graph.posted) == 1
    body = graph.posted[0]["body_text"]
    assert "Ingestion complete" in body
    assert "INS-2026-007" in body
    assert "cb-1" in body


async def test_post_email_draft_renders_draft_body_and_instructions() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)
    draft = {
        "to": ["ana@tafi.com.ar"],
        "cc": [],
        "subject": "Faltan documentos para completar el análisis",
        "in_reply_to_message_id": "msg-1",
        "language": "es",
        "body": (
            "Hola Ana, gracias por enviar el balance. Para cerrar el análisis "
            "necesitamos el dictamen del auditor."
        ),
        "missing_fields_referenced": ["dictamen"],
        "tone_examples_consulted": [],
    }
    post = ManifestPost(
        kind="client_email_draft",
        contract_id="INS-2026-007",
        summary="Missing fields: dictamen",
        manifest=_manifest(missing_fields=["dictamen"], client_email_draft=draft),
    )

    result = await poster.post_email_draft(
        post=post, channel=_CONTRACT, callback_id="cb-draft-1"
    )

    body = graph.posted[0]["body_text"]
    assert "ana@tafi.com.ar" in body
    assert "Hola Ana" in body
    assert "APPROVE" in body
    assert "EDIT" in body
    assert "REJECT" in body
    assert "cb-draft-1" in body
    assert result.kind == "client_email_draft"


async def test_post_email_draft_requires_draft() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)
    post = ManifestPost(
        kind="client_email_draft",
        contract_id="INS-2026-007",
        summary="Missing fields: dictamen",
        manifest=_manifest(missing_fields=["dictamen"], client_email_draft=None),
    )

    with pytest.raises(SchemaValidationError, match="client_email_draft"):
        await poster.post_email_draft(
            post=post, channel=_CONTRACT, callback_id="cb-x"
        )


async def test_post_triage_routes_to_triage_channel() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)

    envelope = ResolverEnvelope(
        decision="triage",
        contract_id=None,
        confidence=0.45,
        rationale_short="ambiguous sender domain",
        triage_payload=TriagePayload(
            question="Which contract is this?",
            candidates=[
                TriageCandidate(
                    contract_id="INS-2026-007", score=0.62, reason="similar subject"
                ),
            ],
            inferred_new_contract=InferredNewContract(
                client_name_guess="Nuevo SA", sender_domain="nuevo.com"
            ),
        ),
    )
    email = EmailMeta.model_validate(
        {
            "from": "intake@unknown.com",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Documentos",
            "conversationId": "conv-x",
            "messageId": "msg-x",
            "body_text": "Adjunto",
            "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
        }
    )

    result = await poster.post_triage(
        envelope=envelope, email=email, callback_id="cb-triage-1"
    )

    assert result.kind == "triage"
    assert result.team_id == _TRIAGE.team_id
    assert result.channel_id == _TRIAGE.channel_id

    body = graph.posted[0]["body_text"]
    assert "Triage required" in body
    assert "INS-2026-007" in body
    assert "Nuevo SA" in body
    assert "cb-triage-1" in body


async def test_post_degraded_includes_rejection_reason() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)
    post = ManifestPost(
        kind="degraded",
        contract_id="INS-2026-007",
        summary="Draft body too short.",
        manifest=_manifest(),
        rejection_reason="body length 22 < 50",
    )

    result = await poster.post_degraded(
        post=post, channel=_CONTRACT, callback_id="cb-deg"
    )

    body = graph.posted[0]["body_text"]
    assert "Degraded" in body
    assert "body length 22 < 50" in body
    assert result.kind == "degraded"


async def test_post_kind_mismatch_raises() -> None:
    graph = _FakeGraph()
    poster = TeamsCardPoster(graph=graph, triage_channel=_TRIAGE)

    wrong_kind = ManifestPost(
        kind="status_ok",
        contract_id="INS-2026-007",
        summary="ok",
        manifest=_manifest(),
    )

    with pytest.raises(SchemaValidationError, match="status_ok"):
        await poster.post_degraded(
            post=wrong_kind, channel=_CONTRACT, callback_id="cb"
        )

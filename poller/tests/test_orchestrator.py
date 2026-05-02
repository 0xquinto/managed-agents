"""Orchestrator integration test — wires fakes through one full cycle.

Asserts: empty mailbox + no pending cards → CycleSummary with all-zero counters.
The deeper per-component behavior is covered by the per-component test suites;
this file verifies the wiring contract holds.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from poller.adapters.anthropic_sessions import AnthropicSessionsAdapter, SessionResult
from poller.adapters.memory import LocalFilesystemBackend, MemoryStoreClient
from poller.components.attachment_stager import AttachmentStager
from poller.components.email_gate import EmailGate
from poller.components.ingestion_step import IngestionStep
from poller.components.mail_feed import MailFeed
from poller.components.manifest_step import ManifestStep
from poller.components.reply_parser import ChannelReplyPoll
from poller.components.resolver_step import ResolverStep
from poller.components.teams_poster import ChannelRef, TeamsCardPoster
from poller.orchestrator import ContractChannelResolver, Orchestrator
from poller.schemas import EmailMeta


class _NopGraph:
    """All Graph methods raise; the test gives the orchestrator nothing to do."""

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[Any], str]:
        # Empty mailbox; cursor unchanged.
        return [], delta_link or "delta-token-init"

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

    async def list_channel_replies(
        self, *, team_id: str, channel_id: str, message_id: str
    ) -> list[Any]:
        return []

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


class _NopSessionsBackend:
    """Sessions adapter that never gets called; raises if it is."""

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
        raise NotImplementedError


def _clock() -> Callable[[], float]:
    return AsyncMock(return_value=1_700_000_000.0)


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


@pytest.fixture
def orchestrator(memory: MemoryStoreClient) -> Orchestrator:
    graph = _NopGraph()
    sessions = AnthropicSessionsAdapter(backend=_NopSessionsBackend())

    return Orchestrator(
        graph=graph,
        mail_feed=MailFeed(graph=graph, memory=memory),
        email_gate=EmailGate(memory=memory, clock=lambda: 1_700_000_000.0),
        resolver_step=ResolverStep(sessions=sessions, agent_id="agent_resolver"),
        attachment_stager=AttachmentStager(graph=graph, memory=memory),
        ingestion_step=IngestionStep(sessions=sessions, agent_id="agent_ingestion"),
        manifest_step=ManifestStep(),
        teams_poster=TeamsCardPoster(
            graph=graph,
            triage_channel=ChannelRef(team_id="team-1", channel_id="chan-triage"),
        ),
        reply_poll=ChannelReplyPoll(graph=graph, memory=memory),
        memory=memory,
        contract_channel_resolver=ContractChannelResolver(
            memory=memory, default_team_id="team-1"
        ),
    )


async def test_run_cycle_empty_mailbox_no_pending_cards(
    orchestrator: Orchestrator,
) -> None:
    summary = await orchestrator.run_cycle()

    assert summary.emails_seen == 0
    assert summary.decisions_applied == 0
    assert summary.errors == []
    assert summary.triage_cards_posted == 0
    assert summary.draft_cards_posted == 0


async def test_run_cycle_with_pending_card_no_replies(
    orchestrator: Orchestrator, memory: MemoryStoreClient
) -> None:
    """A pending card with no replies in this cycle stays pending."""
    memory.write_json(
        "pending_cards.json",
        [
            {
                "kind": "client_email_draft",
                "team_id": "t",
                "channel_id": "c",
                "message_id": "m-1",
                "contract_id": "INS-2026-007",
                "callback_id": "cb-1",
            }
        ],
    )
    summary = await orchestrator.run_cycle()
    assert summary.decisions_applied == 0
    pending = memory.read_json("pending_cards.json")
    assert len(pending) == 1


class _PopulatedGraph:
    """Graph fake that returns one email with one PDF attachment + accepts posts."""

    def __init__(self) -> None:
        self.posted_messages: list[dict[str, Any]] = []
        self._counter = 0

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[EmailMeta], str]:
        if delta_link is not None:
            return [], delta_link  # subsequent calls return nothing
        msg = EmailMeta.model_validate(
            {
                "from": "ana@tafi.com.ar",
                "to": ["contracts@insignia.com"],
                "cc": [],
                "subject": "Test ingestion",
                "conversationId": "conv-pop-1",
                "messageId": "msg-pop-1",
                "body_text": "test body",
                "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
            }
        )
        return [msg], "delta-token-after"

    async def download_attachment(
        self, *, message_id: str, attachment_id: str
    ) -> bytes:
        return b"%PDF-fake-content"

    async def list_message_attachments(
        self, *, message_id: str
    ) -> list[dict[str, Any]]:
        return [
            {
                "message_attachment_id": "att-pop-1",
                "filename": "EF.pdf",
                "size": 100_000,
                "content_type": "application/pdf",
                "isInline": False,
                "content_bytes": b"%PDF-fake-content",
            }
        ]

    async def upload_to_onedrive_via_session(
        self,
        *,
        drive_item_path: str,
        content: bytes,
        chunk_size_bytes: int = 5 * 1024 * 1024,
    ) -> str:
        return drive_item_path

    async def post_channel_message(
        self, *, team_id: str, channel_id: str, body_text: str
    ) -> str:
        self._counter += 1
        msg_id = f"posted-{self._counter}"
        self.posted_messages.append(
            {"team_id": team_id, "channel_id": channel_id, "body_text": body_text, "id": msg_id}
        )
        return msg_id

    async def list_channel_replies(
        self, *, team_id: str, channel_id: str, message_id: str
    ) -> list[Any]:
        return []

    async def send_mail(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body_text: str,
        in_reply_to_message_id: str | None = None,
    ) -> None:
        pass


class _TriageSessionsBackend:
    """Sessions backend that returns a triage envelope on the first call."""

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        return SessionResult(
            session_id=f"sess-{self.calls}",
            stop_reason="end_turn",
            final_message_text=(
                '{"decision": "triage", "contract_id": null, '
                '"confidence": 0.4, "rationale_short": "ambiguous sender"}'
            ),
            captured_files={},
            is_error=False,
        )


async def test_run_cycle_with_populated_email_reaches_resolver(
    memory: MemoryStoreClient,
) -> None:
    """Regression: orchestrator must fetch attachments + drive an email
    past EmailGate to the resolver (and past the resolver to a Teams post).

    Before fix: _process_email hard-coded raw_attachments=[] so EmailGate
    Stage 1 silently rejected every email and the resolver never ran.
    """
    graph = _PopulatedGraph()
    sessions_be = _TriageSessionsBackend()
    sessions = AnthropicSessionsAdapter(backend=sessions_be)

    orchestrator = Orchestrator(
        graph=graph,
        mail_feed=MailFeed(graph=graph, memory=memory),
        email_gate=EmailGate(memory=memory, clock=lambda: 1_700_000_000.0),
        resolver_step=ResolverStep(sessions=sessions, agent_id="agent_resolver"),
        attachment_stager=AttachmentStager(graph=graph, memory=memory),
        ingestion_step=IngestionStep(sessions=sessions, agent_id="agent_ingestion"),
        manifest_step=ManifestStep(),
        teams_poster=TeamsCardPoster(
            graph=graph,
            triage_channel=ChannelRef(team_id="team-1", channel_id="chan-triage"),
        ),
        reply_poll=ChannelReplyPoll(graph=graph, memory=memory),
        memory=memory,
        contract_channel_resolver=ContractChannelResolver(
            memory=memory, default_team_id="team-1"
        ),
    )

    summary = await orchestrator.run_cycle()

    # Email reached the gate AND the resolver AND the Teams poster.
    assert summary.emails_seen == 1
    assert summary.emails_rejected_by_gate == 0, (
        "regression: email was rejected by gate — dead-path bug returned"
    )
    assert sessions_be.calls == 1, "resolver was not invoked"
    assert summary.triage_cards_posted == 1
    assert len(graph.posted_messages) == 1
    assert summary.errors == []

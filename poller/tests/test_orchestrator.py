"""Orchestrator integration test — wires fakes through one full cycle.

Asserts: empty mailbox + no pending cards → CycleSummary with all-zero counters.
The deeper per-component behavior is covered by the per-component test suites;
this file verifies the wiring contract holds.
"""

from __future__ import annotations

from collections.abc import Callable
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

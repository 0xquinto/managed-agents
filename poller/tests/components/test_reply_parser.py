"""ReplyParser + ChannelReplyPoll tests — APPROVE/EDIT/REJECT + triage routing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from poller.adapters.graph import ChannelReply
from poller.adapters.memory import LocalFilesystemBackend, MemoryStoreClient
from poller.components.reply_parser import (
    ChannelReplyPoll,
    DraftReply,
    TriageReply,
    parse_draft_reply,
    parse_triage_reply,
)
from poller.components.teams_poster import CardPostResult


def _r(body: str, *, ts: float = 1_700_000_000.0, author: str = "u-1") -> ChannelReply:
    return ChannelReply(
        reply_id=f"r-{ts}",
        body_text=body,
        author_id=author,
        author_name="Diego",
        created_at=datetime.fromtimestamp(ts, tz=UTC),
    )


# parse_draft_reply ---------------------------------------------------------


def test_parse_draft_approve_plain() -> None:
    parsed = parse_draft_reply(_r("APPROVE"))
    assert isinstance(parsed, DraftReply)
    assert parsed.decision == "approve"


def test_parse_draft_approve_lowercase() -> None:
    parsed = parse_draft_reply(_r("approve"))
    assert parsed is not None
    assert parsed.decision == "approve"


def test_parse_draft_approve_with_html_tags() -> None:
    parsed = parse_draft_reply(_r("<p>APPROVE</p>"))
    assert parsed is not None
    assert parsed.decision == "approve"


def test_parse_draft_approve_with_trailing_text_ignored() -> None:
    parsed = parse_draft_reply(_r("APPROVE looks good!"))
    assert parsed is not None
    assert parsed.decision == "approve"


def test_parse_draft_edit_with_new_body() -> None:
    parsed = parse_draft_reply(_r("EDIT Hola Ana, faltan los EE.FF. consolidados."))
    assert parsed is not None
    assert parsed.decision == "edit"
    assert parsed.edit_body == "Hola Ana, faltan los EE.FF. consolidados."


def test_parse_draft_edit_bare_returns_none() -> None:
    parsed = parse_draft_reply(_r("EDIT"))
    assert parsed is None  # no body — wait for clarification


def test_parse_draft_reject_with_reason() -> None:
    parsed = parse_draft_reply(_r("REJECT tone is off"))
    assert parsed is not None
    assert parsed.decision == "reject"
    assert parsed.reject_reason == "tone is off"


def test_parse_draft_reject_bare() -> None:
    parsed = parse_draft_reply(_r("REJECT"))
    assert parsed is not None
    assert parsed.decision == "reject"
    assert parsed.reject_reason == "no reason provided"


def test_parse_draft_chatter_returns_none() -> None:
    assert parse_draft_reply(_r("looks pretty good imho")) is None


# parse_triage_reply --------------------------------------------------------


def test_parse_triage_assign_plain() -> None:
    parsed = parse_triage_reply(_r("INS-2026-007"))
    assert isinstance(parsed, TriageReply)
    assert parsed.decision == "assign"
    assert parsed.contract_id == "INS-2026-007"


def test_parse_triage_new_contract() -> None:
    parsed = parse_triage_reply(_r("new Financiera Tafi"))
    assert parsed is not None
    assert parsed.decision == "new_contract"
    assert parsed.new_client_name == "Financiera Tafi"


def test_parse_triage_drop_with_reason() -> None:
    parsed = parse_triage_reply(_r("drop spam"))
    assert parsed is not None
    assert parsed.decision == "drop"
    assert parsed.drop_reason == "spam"


def test_parse_triage_chatter_returns_none() -> None:
    assert parse_triage_reply(_r("not sure")) is None


# ChannelReplyPoll ----------------------------------------------------------


class _FakeGraph:
    def __init__(self, replies_by_msg: dict[str, list[ChannelReply]]) -> None:
        self._replies = replies_by_msg

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[Any], str]:
        raise NotImplementedError

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
    ) -> list[ChannelReply]:
        return list(self._replies.get(message_id, []))

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


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


def _seed_pending(memory: MemoryStoreClient, cards: list[CardPostResult]) -> None:
    memory.write_json(
        "pending_cards.json",
        [card.__dict__ for card in cards],
    )


async def test_collect_resolves_draft_with_first_approve(
    memory: MemoryStoreClient,
) -> None:
    card = CardPostResult(
        kind="client_email_draft",
        team_id="t",
        channel_id="c",
        message_id="m-draft-1",
        contract_id="INS-2026-007",
        callback_id="cb-1",
    )
    _seed_pending(memory, [card])

    graph = _FakeGraph(
        {
            "m-draft-1": [
                _r("looks good", ts=1.0),
                _r("APPROVE", ts=2.0),  # second reply wins because the first
                                       # didn't parse; first parseable wins
            ]
        }
    )
    poll = ChannelReplyPoll(graph=graph, memory=memory)

    result = await poll.collect()

    assert "cb-1" in result.draft_decisions
    assert result.draft_decisions["cb-1"].decision == "approve"
    assert result.still_pending == []
    assert memory.read_json("pending_cards.json") == []


async def test_collect_keeps_card_pending_when_no_command(
    memory: MemoryStoreClient,
) -> None:
    card = CardPostResult(
        kind="client_email_draft",
        team_id="t",
        channel_id="c",
        message_id="m-2",
        contract_id="INS-2026-007",
        callback_id="cb-2",
    )
    _seed_pending(memory, [card])

    graph = _FakeGraph({"m-2": [_r("interesting"), _r("hmm")]})
    poll = ChannelReplyPoll(graph=graph, memory=memory)

    result = await poll.collect()

    assert result.draft_decisions == {}
    assert len(result.still_pending) == 1
    assert result.still_pending[0].callback_id == "cb-2"


async def test_collect_ignores_bot_replies(memory: MemoryStoreClient) -> None:
    memory.write_json("bot_author_ids.json", ["bot-svc-1"])
    card = CardPostResult(
        kind="client_email_draft",
        team_id="t",
        channel_id="c",
        message_id="m-3",
        contract_id="INS-2026-007",
        callback_id="cb-3",
    )
    _seed_pending(memory, [card])

    graph = _FakeGraph(
        {
            "m-3": [
                _r("APPROVE", ts=1.0, author="bot-svc-1"),  # bot — ignored
                _r("REJECT noisy", ts=2.0, author="human-1"),  # human — wins
            ]
        }
    )
    poll = ChannelReplyPoll(graph=graph, memory=memory)

    result = await poll.collect()

    assert result.draft_decisions["cb-3"].decision == "reject"


async def test_collect_handles_triage(memory: MemoryStoreClient) -> None:
    card = CardPostResult(
        kind="triage",
        team_id="t",
        channel_id="c-triage",
        message_id="m-tr",
        contract_id=None,
        callback_id="cb-tr",
    )
    _seed_pending(memory, [card])

    graph = _FakeGraph(
        {"m-tr": [_r("INS-2026-007")]}
    )
    poll = ChannelReplyPoll(graph=graph, memory=memory)

    result = await poll.collect()

    assert "cb-tr" in result.triage_decisions
    assert result.triage_decisions["cb-tr"].contract_id == "INS-2026-007"
    assert result.still_pending == []


async def test_collect_with_empty_pending(memory: MemoryStoreClient) -> None:
    graph = _FakeGraph({})
    poll = ChannelReplyPoll(graph=graph, memory=memory)

    result = await poll.collect()

    assert result.draft_decisions == {}
    assert result.triage_decisions == {}
    assert result.still_pending == []

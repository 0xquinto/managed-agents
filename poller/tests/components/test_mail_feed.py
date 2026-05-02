"""MailFeed tests — cursor persistence + delta-query orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from poller.adapters.memory import LocalFilesystemBackend, MemoryStoreClient
from poller.components.mail_feed import MailFeed
from poller.schemas import EmailMeta


def _email(message_id: str) -> EmailMeta:
    return EmailMeta.model_validate(
        {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Subject",
            "conversationId": "c-1",
            "messageId": message_id,
            "body_text": "body",
            "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
        }
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


async def test_first_run_passes_none_to_graph(memory: MemoryStoreClient) -> None:
    """First call ever (no cursor in memory) calls Graph with delta_link=None."""
    fake_graph = AsyncMock()
    fake_graph.list_new_messages_via_delta = AsyncMock(
        return_value=([_email("m1")], "https://graph.microsoft.com/v1.0/...?$deltaToken=abc")
    )

    feed = MailFeed(graph=fake_graph, memory=memory)
    messages = await feed.fetch_new()

    fake_graph.list_new_messages_via_delta.assert_called_once_with(delta_link=None)
    assert [m.messageId for m in messages] == ["m1"]
    assert memory.read_mail_cursor() == {
        "deltaLink": "https://graph.microsoft.com/v1.0/...?$deltaToken=abc"
    }


async def test_resumes_from_persisted_cursor(memory: MemoryStoreClient) -> None:
    """Second call uses the cursor written by the first call."""
    memory.write_mail_cursor({"deltaLink": "https://graph.microsoft.com/v1.0/...?$deltaToken=abc"})

    fake_graph = AsyncMock()
    fake_graph.list_new_messages_via_delta = AsyncMock(
        return_value=([], "https://graph.microsoft.com/v1.0/...?$deltaToken=def")
    )

    feed = MailFeed(graph=fake_graph, memory=memory)
    messages = await feed.fetch_new()

    fake_graph.list_new_messages_via_delta.assert_called_once_with(
        delta_link="https://graph.microsoft.com/v1.0/...?$deltaToken=abc"
    )
    assert messages == []
    assert memory.read_mail_cursor() == {
        "deltaLink": "https://graph.microsoft.com/v1.0/...?$deltaToken=def"
    }


async def test_cursor_advances_after_successful_fetch(memory: MemoryStoreClient) -> None:
    """Each fetch overwrites the cursor with the latest deltaLink."""
    memory.write_mail_cursor({"deltaLink": "old"})

    fake_graph = AsyncMock()
    fake_graph.list_new_messages_via_delta = AsyncMock(return_value=([_email("m1")], "new"))

    feed = MailFeed(graph=fake_graph, memory=memory)
    await feed.fetch_new()

    assert memory.read_mail_cursor() == {"deltaLink": "new"}


async def test_rejects_non_string_cursor(memory: MemoryStoreClient) -> None:
    memory.write_mail_cursor({"deltaLink": 12345})

    fake_graph = AsyncMock()
    feed = MailFeed(graph=fake_graph, memory=memory)

    with pytest.raises(TypeError, match="must be a string"):
        await feed.fetch_new()

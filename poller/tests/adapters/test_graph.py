"""GraphAdapter tests — protocol shape + delta query against a fake SDK client."""

from datetime import UTC, datetime
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock

import pytest

from poller.adapters.graph import GraphAdapter, GraphAdapterProtocol
from poller.exceptions import GraphError


def test_graph_adapter_protocol_is_a_protocol() -> None:
    assert issubclass(GraphAdapterProtocol, Protocol)


def test_graph_adapter_protocol_declares_list_new_messages_via_delta() -> None:
    assert hasattr(GraphAdapterProtocol, "list_new_messages_via_delta")


def _make_fake_graph_message(
    message_id: str,
    subject: str = "Test",
    from_addr: str = "x@y.com",
) -> MagicMock:
    msg = MagicMock()
    msg.id = message_id
    msg.subject = subject
    msg.from_ = MagicMock()
    msg.from_.email_address.address = from_addr
    msg.to_recipients = [
        MagicMock(email_address=MagicMock(address="contracts@insignia.com"))
    ]
    msg.cc_recipients = []
    msg.conversation_id = "conv-1"
    msg.body = MagicMock(content="Test body")
    msg.received_date_time = datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC)
    return msg


def _build_fake_client_with_delta_response(response: MagicMock) -> MagicMock:
    fake_client = MagicMock()
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.get = AsyncMock(
        return_value=response
    )
    return fake_client


async def test_list_new_messages_via_delta_fresh_start() -> None:
    """First call (delta_link is None) starts a fresh delta sequence."""
    fake_response = MagicMock()
    fake_response.value = [_make_fake_graph_message("msg-1")]
    fake_response.odata_delta_link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages/delta?$deltaToken=abc"
    )
    fake_response.odata_next_link = None

    fake_client = _build_fake_client_with_delta_response(fake_response)

    adapter = GraphAdapter(client=fake_client)

    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=None)

    assert len(messages) == 1
    assert messages[0].messageId == "msg-1"
    assert next_delta == fake_response.odata_delta_link


async def test_list_new_messages_via_delta_resume() -> None:
    """Subsequent call uses the prior delta_link via with_url()."""
    fake_response = MagicMock()
    fake_response.value = []
    fake_response.odata_delta_link = "https://graph.microsoft.com/v1.0/...?$deltaToken=def"
    fake_response.odata_next_link = None

    fake_client = MagicMock()
    fake_request_builder = MagicMock()
    fake_request_builder.get = AsyncMock(return_value=fake_response)
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.return_value = (
        fake_request_builder
    )

    adapter = GraphAdapter(client=fake_client)

    prior_delta = "https://graph.microsoft.com/v1.0/...?$deltaToken=abc"
    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=prior_delta)

    assert messages == []
    assert next_delta == fake_response.odata_delta_link
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.assert_called_once_with(
        prior_delta
    )


async def test_list_new_messages_via_delta_raises_on_missing_delta_link() -> None:
    fake_response = MagicMock()
    fake_response.value = []
    fake_response.odata_delta_link = None  # malformed
    fake_response.odata_next_link = None

    fake_client = _build_fake_client_with_delta_response(fake_response)

    adapter = GraphAdapter(client=fake_client)

    with pytest.raises(GraphError, match="missing both odata_delta_link"):
        await adapter.list_new_messages_via_delta(delta_link=None)


async def test_list_new_messages_via_delta_paginates() -> None:
    """Adapter follows odata_next_link until odata_delta_link is returned."""
    page1 = MagicMock()
    page1.value = [_make_fake_graph_message("msg-1")]
    page1.odata_next_link = "https://graph.microsoft.com/v1.0/...?$skiptoken=p2"
    page1.odata_delta_link = None

    page2 = MagicMock()
    page2.value = [_make_fake_graph_message("msg-2")]
    page2.odata_next_link = None
    page2.odata_delta_link = "https://graph.microsoft.com/v1.0/...?$deltaToken=final"

    fake_client = MagicMock()
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.get = AsyncMock(
        return_value=page1
    )
    fake_next_builder = MagicMock()
    fake_next_builder.get = AsyncMock(return_value=page2)
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.return_value = (
        fake_next_builder
    )

    adapter = GraphAdapter(client=fake_client)
    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=None)

    assert [m.messageId for m in messages] == ["msg-1", "msg-2"]
    assert next_delta == "https://graph.microsoft.com/v1.0/...?$deltaToken=final"


def test_graph_adapter_from_client_credentials() -> None:
    """The adapter exposes a builder that takes (tenant_id, client_id, client_secret)."""
    adapter = GraphAdapter.from_client_credentials(
        tenant_id="tenant-uuid",
        client_id="client-uuid",
        client_secret="secret",
    )

    assert isinstance(adapter, GraphAdapter)
    assert adapter._client is not None

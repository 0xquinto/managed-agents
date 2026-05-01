"""GraphAdapter — wraps Microsoft Graph SDK calls for the poller.

Phase 1 implements list_new_messages_via_delta only. Other methods (download_attachment,
upload_to_onedrive via createUploadSession per spec § 2.5, post_channel_message, send_mail)
ship in Phase 2 alongside live tenant integration tests.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from poller.exceptions import GraphError
from poller.schemas import EmailMeta


@runtime_checkable
class GraphAdapterProtocol(Protocol):
    """Microsoft Graph adapter contract. Phase 1 implements list_new_messages_via_delta only."""

    async def list_new_messages_via_delta(
        self,
        *,
        delta_link: str | None,
    ) -> tuple[list[EmailMeta], str]:
        """Fetch new mail since the last delta_link. Returns (messages, next_delta_link).

        On first run (delta_link is None), starts a fresh delta sequence and consumes
        the entire current state, returning [] and the new delta_link to persist.
        """
        ...


class GraphAdapter:
    """Concrete GraphAdapterProtocol implementation backed by msgraph-sdk-python.

    Phase 1: list_new_messages_via_delta only. Phase 2 adds download_attachment,
    upload_to_onedrive (via createUploadSession per spec § 2.5), post_channel_message,
    send_mail.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def list_new_messages_via_delta(
        self,
        *,
        delta_link: str | None,
    ) -> tuple[list[EmailMeta], str]:
        try:
            delta_endpoint = (
                self._client.me.mail_folders.by_mail_folder_id("Inbox").messages.delta
            )

            if delta_link is None:
                response = await delta_endpoint.get()
            else:
                response = await delta_endpoint.with_url(delta_link).get()

            messages: list[EmailMeta] = [self._convert(m) for m in (response.value or [])]

            # Follow odata_next_link until odata_delta_link arrives.
            while response.odata_delta_link is None:
                if response.odata_next_link is None:
                    raise GraphError(
                        "Graph delta response missing both odata_delta_link "
                        "and odata_next_link"
                    )
                response = await delta_endpoint.with_url(response.odata_next_link).get()
                messages.extend(self._convert(m) for m in (response.value or []))

            return messages, response.odata_delta_link

        except GraphError:
            raise
        except Exception as exc:
            raise GraphError(f"Graph delta query failed: {exc}") from exc

    @classmethod
    def from_client_credentials(
        cls,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> GraphAdapter:
        """Build a GraphAdapter using Azure AD client-credentials flow."""
        from azure.identity.aio import ClientSecretCredential
        from msgraph.graph_service_client import GraphServiceClient

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        client = GraphServiceClient(
            credentials=credential,
            scopes=["https://graph.microsoft.com/.default"],
        )
        return cls(client=client)

    @staticmethod
    def _convert(graph_message: Any) -> EmailMeta:
        """Convert an msgraph Message object to EmailMeta."""
        return EmailMeta.model_validate(
            {
                "from": graph_message.from_.email_address.address,
                "to": [
                    r.email_address.address
                    for r in (graph_message.to_recipients or [])
                ],
                "cc": [
                    r.email_address.address
                    for r in (graph_message.cc_recipients or [])
                ],
                "subject": graph_message.subject or "",
                "conversationId": graph_message.conversation_id,
                "messageId": graph_message.id,
                "body_text": (
                    graph_message.body.content if graph_message.body else ""
                )
                or "",
                "received_at": graph_message.received_date_time,
            }
        )

"""GraphAdapter — wraps Microsoft Graph SDK calls for the poller.

Phase 1 implements list_new_messages_via_delta. Phase 3 adds download_attachment +
upload_to_onedrive_via_session (the createUploadSession path mandated by spec § 2.5).

Phase 4 adds post_channel_message + list_channel_replies + send_mail (per spec
§ 2.3 Option B HITL routing).

The upload helper is intentionally written to use createUploadSession even for small
files. Spec § 2.5 forbids the plain `PUT /drive/items/.../content` path because it
caps at 4MB, and financial-statement PDFs routinely exceed that. One idempotent
code path beats a size-branching code path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import httpx

from poller.exceptions import GraphError
from poller.schemas import EmailMeta


@dataclass(frozen=True)
class ChannelReply:
    """One reply message in a Teams channel thread."""

    reply_id: str
    body_text: str
    author_id: str
    author_name: str
    created_at: datetime


@runtime_checkable
class GraphAdapterProtocol(Protocol):
    """Microsoft Graph adapter contract.

    Phases:
      Phase 1: list_new_messages_via_delta
      Phase 3: download_attachment, upload_to_onedrive_via_session
      Phase 4: post_channel_message, send_mail, list_channel_replies
    """

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

    async def download_attachment(
        self,
        *,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """Download one email attachment by id. Returns the raw bytes."""
        ...

    async def upload_to_onedrive_via_session(
        self,
        *,
        drive_item_path: str,
        content: bytes,
        chunk_size_bytes: int = 5 * 1024 * 1024,
    ) -> str:
        """Upload content to OneDrive at drive_item_path via createUploadSession.

        Returns the final canonical path of the uploaded item (which may differ
        from the requested path if a conflict-rename was applied).

        Per spec § 2.5: this MUST be the only upload path used by the poller.
        Plain `PUT /drive/items/.../content` is forbidden because it caps at 4MB.
        Defaulting to createUploadSession even for small files keeps the code path
        idempotent — no size branching.
        """
        ...

    async def post_channel_message(
        self,
        *,
        team_id: str,
        channel_id: str,
        body_text: str,
    ) -> str:
        """Post a plain-text message to a Teams channel. Returns the new message id.

        Per spec § 2.3 Option B: messages are plain-text (not Adaptive Cards).
        Recipients reply in-thread with APPROVE / EDIT <body> / REJECT <reason>.
        """
        ...

    async def list_channel_replies(
        self,
        *,
        team_id: str,
        channel_id: str,
        message_id: str,
    ) -> list[ChannelReply]:
        """List replies in the thread of a given parent message."""
        ...

    async def send_mail(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body_text: str,
        in_reply_to_message_id: str | None = None,
    ) -> None:
        """Send an email from the watched inbox via Graph /me/sendMail."""
        ...


class GraphAdapter:
    """Concrete GraphAdapterProtocol implementation backed by msgraph-sdk-python.

    The delta + attachment methods use msgraph-sdk-python directly. The
    createUploadSession upload path is implemented as a two-step:

      1. POST /drive/root:/<path>:/createUploadSession  → returns uploadUrl
      2. PUT chunks to uploadUrl with Content-Range headers

    Step 2 is plain HTTPS, not SDK-mediated — Microsoft documents this as the
    expected pattern, and the SDK's wrapper is awkward for our chunking control.
    """

    def __init__(self, client: Any, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._http = http_client

    # ------------------------------------------------------------------ delta

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

    # -------------------------------------------------------- attachment I/O

    async def download_attachment(
        self,
        *,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """Download one email attachment by id.

        Implementation: msgraph-sdk-python returns the attachment as a
        FileAttachment object whose `content_bytes` field holds the raw bytes.
        """
        try:
            attachment = (
                await self._client.me.messages.by_message_id(message_id)
                .attachments.by_attachment_id(attachment_id)
                .get()
            )
            content = getattr(attachment, "content_bytes", None)
            if content is None:
                raise GraphError(
                    f"attachment {attachment_id} on message {message_id} "
                    f"returned no content_bytes (item-attachment or reference?)"
                )
            return bytes(content)
        except GraphError:
            raise
        except Exception as exc:
            raise GraphError(
                f"failed to download attachment {attachment_id}: {exc}"
            ) from exc

    async def upload_to_onedrive_via_session(
        self,
        *,
        drive_item_path: str,
        content: bytes,
        chunk_size_bytes: int = 5 * 1024 * 1024,
    ) -> str:
        """Upload via createUploadSession. Per spec § 2.5: idempotent path, no branching."""
        if not drive_item_path.startswith("/"):
            raise GraphError(
                f"drive_item_path must start with '/'; got {drive_item_path!r}"
            )

        # Step 1: createUploadSession via SDK.
        try:
            upload_session = await self._create_upload_session(drive_item_path)
        except Exception as exc:
            raise GraphError(
                f"createUploadSession failed for {drive_item_path}: {exc}"
            ) from exc

        upload_url = getattr(upload_session, "upload_url", None)
        if not upload_url:
            raise GraphError(
                f"createUploadSession for {drive_item_path} returned no upload_url"
            )

        # Step 2: PUT chunks to the upload URL.
        return await self._put_chunks(
            upload_url=upload_url,
            content=content,
            chunk_size_bytes=chunk_size_bytes,
        )

    async def _create_upload_session(self, drive_item_path: str) -> Any:
        """Wrapper to keep test-time monkeypatching narrow."""
        # SDK shape: client.me.drive.root.item_with_path(path).create_upload_session.post(body)
        # We pass an empty body — defaults give us conflict-rename behavior.
        return (
            await self._client.me.drive.root.item_with_path(drive_item_path)
            .create_upload_session.post(body=None)
        )

    async def _put_chunks(
        self,
        *,
        upload_url: str,
        content: bytes,
        chunk_size_bytes: int,
    ) -> str:
        """PUT bytes in chunks to the upload session URL.

        Per Microsoft Graph docs: each PUT carries a Content-Range header. The final
        response contains the DriveItem JSON; we extract `parentReference.path` +
        `name` and return the canonical path.
        """
        if chunk_size_bytes <= 0 or chunk_size_bytes % (320 * 1024) != 0:
            # Microsoft requires chunks to be multiples of 320 KiB. We don't auto-fix
            # — surface the misconfiguration loudly.
            raise GraphError(
                f"chunk_size_bytes={chunk_size_bytes} must be a positive multiple of 320 KiB"
            )

        total = len(content)
        if total == 0:
            raise GraphError("cannot upload empty content via createUploadSession")

        http = self._http or httpx.AsyncClient()
        owns_http = self._http is None
        try:
            offset = 0
            final_response: httpx.Response | None = None
            while offset < total:
                end = min(offset + chunk_size_bytes, total) - 1
                chunk = content[offset : end + 1]
                headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                }
                resp = await http.put(upload_url, content=chunk, headers=headers)
                if resp.status_code not in (200, 201, 202):
                    raise GraphError(
                        f"upload PUT failed at offset {offset}: "
                        f"status={resp.status_code} body={resp.text[:200]!r}"
                    )
                final_response = resp
                offset = end + 1

            if final_response is None or final_response.status_code not in (200, 201):
                raise GraphError(
                    "upload completed without a terminal 200/201 DriveItem response"
                )

            payload = final_response.json()
            parent_path = (
                (payload.get("parentReference") or {}).get("path") or ""
            )
            name = payload.get("name") or ""
            # parent_path looks like "/drive/root:/Contracts/Tafi/raw/AAMk..."
            # We strip the "/drive/root:" prefix to return a clean OneDrive path.
            clean_parent = parent_path.split(":", 1)[-1] if ":" in parent_path else parent_path
            return f"{clean_parent.rstrip('/')}/{name}"
        finally:
            if owns_http:
                await http.aclose()

    # ------------------------------------------------------- Teams + email

    async def post_channel_message(
        self,
        *,
        team_id: str,
        channel_id: str,
        body_text: str,
    ) -> str:
        try:
            from msgraph.generated.models.chat_message import ChatMessage
            from msgraph.generated.models.item_body import ItemBody

            body = ItemBody(content=body_text)
            payload = ChatMessage(body=body)
            response = await (
                self._client.teams.by_team_id(team_id)
                .channels.by_channel_id(channel_id)
                .messages.post(body=payload)
            )
            if response is None or getattr(response, "id", None) is None:
                raise GraphError(
                    f"post_channel_message returned no message id "
                    f"(team={team_id} channel={channel_id})"
                )
            return str(response.id)
        except GraphError:
            raise
        except Exception as exc:
            raise GraphError(f"post_channel_message failed: {exc}") from exc

    async def list_channel_replies(
        self,
        *,
        team_id: str,
        channel_id: str,
        message_id: str,
    ) -> list[ChannelReply]:
        try:
            response = await (
                self._client.teams.by_team_id(team_id)
                .channels.by_channel_id(channel_id)
                .messages.by_chat_message_id(message_id)
                .replies.get()
            )
            replies_raw = list(getattr(response, "value", []) or [])
            out: list[ChannelReply] = []
            for r in replies_raw:
                body = getattr(r, "body", None)
                content = getattr(body, "content", "") or ""
                user = getattr(getattr(r, "from_", None), "user", None)
                out.append(
                    ChannelReply(
                        reply_id=str(getattr(r, "id", "")),
                        body_text=str(content),
                        author_id=str(getattr(user, "id", "") or ""),
                        author_name=str(getattr(user, "display_name", "") or ""),
                        created_at=getattr(r, "created_date_time", datetime.fromtimestamp(0)),
                    )
                )
            return out
        except Exception as exc:
            raise GraphError(f"list_channel_replies failed: {exc}") from exc

    async def send_mail(
        self,
        *,
        to: list[str],
        cc: list[str],
        subject: str,
        body_text: str,
        in_reply_to_message_id: str | None = None,
    ) -> None:
        try:
            from msgraph.generated.models.body_type import BodyType
            from msgraph.generated.models.email_address import EmailAddress
            from msgraph.generated.models.item_body import ItemBody
            from msgraph.generated.models.message import Message
            from msgraph.generated.models.recipient import Recipient
            from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
                SendMailPostRequestBody,
            )

            def _to_recipients(addrs: list[str]) -> list[Recipient]:
                return [Recipient(email_address=EmailAddress(address=a)) for a in addrs]

            msg = Message(
                subject=subject,
                body=ItemBody(content_type=BodyType.Text, content=body_text),
                to_recipients=_to_recipients(to),
                cc_recipients=_to_recipients(cc),
            )
            if in_reply_to_message_id:
                # Graph supports threading via internetMessageHeaders / conversation_id;
                # for v1 we use replyAll under /me/messages/<id>/replyAll if reply id
                # is set. Defer to a wrapper for cleanliness.
                await (
                    self._client.me.messages.by_message_id(in_reply_to_message_id)
                    .reply.post(
                        body={"comment": body_text, "message": {"subject": subject}}
                    )
                )
                return
            request = SendMailPostRequestBody(message=msg, save_to_sent_items=True)
            await self._client.me.send_mail.post(body=request)
        except Exception as exc:
            raise GraphError(f"send_mail failed: {exc}") from exc

    # ----------------------------------------------------------- credentials

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

    # ------------------------------------------------------- internal helpers

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

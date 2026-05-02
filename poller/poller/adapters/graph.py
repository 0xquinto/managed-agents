"""GraphAdapter — wraps Microsoft Graph SDK calls for the poller.

Phase 1 implements list_new_messages_via_delta. Phase 3 adds download_attachment +
upload_to_onedrive_via_session (the createUploadSession path mandated by spec § 2.5).

Phase 4 will add post_channel_message + send_mail + reply-thread polling alongside
live tenant integration tests.

The upload helper is intentionally written to use createUploadSession even for small
files. Spec § 2.5 forbids the plain `PUT /drive/items/.../content` path because it
caps at 4MB, and financial-statement PDFs routinely exceed that. One idempotent
code path beats a size-branching code path.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx

from poller.exceptions import GraphError
from poller.schemas import EmailMeta


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

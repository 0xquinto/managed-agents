"""AttachmentStager — Phase 3 component per spec § 2.5.

Pipeline per attachment:

  1. Download the bytes via GraphAdapter.download_attachment.
  2. Recompute sha256 and compare to the AttachmentMeta declared hash. Mismatch is
     a hard error — stale/poisoned email metadata, fall through to triage.
  3. Upload to OneDrive at:
        /Contracts/<client>/raw/<message_id>/<filename>
     via createUploadSession (spec § 2.5: idempotent path, no plain PUT).
  4. Append `{contract_id, sha256, message_id, onedrive_path, received_at}` to
     `seen_attachments` in the memory store. The dedup gate (EmailGate stage 3)
     reads from this same key.

Returns StagedAttachments — the bytes are kept in-memory so IngestionStep can hand
them to the Anthropic Files API as session resources without round-tripping
through OneDrive.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from poller.adapters.graph import GraphAdapterProtocol
from poller.adapters.memory import MemoryStoreClient
from poller.exceptions import GraphError, SchemaValidationError
from poller.schemas import AttachmentMeta


@dataclass(frozen=True)
class StagedAttachment:
    """One attachment that's been pulled from email + parked on OneDrive."""

    filename: str
    sha256: str
    size: int
    content_bytes: bytes
    onedrive_path: str
    content_type: str


@dataclass(frozen=True)
class StagedAttachments:
    """Result of staging the full attachment list for one inbound email."""

    items: list[StagedAttachment]
    message_id: str
    contract_id: str

    @property
    def session_resource_paths(self) -> list[str]:
        """Mount paths for IngestionKickoff.input_files.

        Anthropic session resources of type=file mount under
        `/mnt/session/uploads/<filename>` per the global memory note.
        """
        return [f"/mnt/session/uploads/{a.filename}" for a in self.items]


class AttachmentStager:
    """Stages email attachments to OneDrive and updates seen_attachments memory."""

    def __init__(
        self,
        *,
        graph: GraphAdapterProtocol,
        memory: MemoryStoreClient,
    ) -> None:
        self._graph = graph
        self._memory = memory

    async def stage(
        self,
        *,
        contract_id: str,
        client_name: str,
        onedrive_root: str,
        message_id: str,
        attachments: list[AttachmentMeta],
        received_at: datetime | None = None,
    ) -> StagedAttachments:
        """Run the four-step pipeline for every attachment in the list.

        Args:
          contract_id:    INS-YYYY-NNN — used to update seen_attachments + correlate
          client_name:    informational; the OneDrive root is passed explicitly
          onedrive_root:  e.g. "/Contracts/Tafi/" — must end with '/'
          message_id:     RFC822 / Graph message id — used as the raw/<msg_id>/ folder
          attachments:    EmailGate-validated AttachmentMeta list (post-stage-2)
          received_at:    optional override for seen_attachments timestamp; defaults to now

        Returns StagedAttachments with content_bytes held in memory for downstream
        session-resource attachment by IngestionStep.
        """
        if not onedrive_root.startswith("/") or not onedrive_root.endswith("/"):
            raise SchemaValidationError(
                f"onedrive_root must start and end with '/'; got {onedrive_root!r}"
            )

        when = received_at or datetime.now(tz=UTC)
        staged: list[StagedAttachment] = []

        for att in attachments:
            content = await self._graph.download_attachment(
                message_id=message_id,
                attachment_id=att.message_attachment_id,
            )

            # Verify the declared hash matches what we actually downloaded.
            actual_sha = hashlib.sha256(content).hexdigest()
            if actual_sha != att.sha256:
                raise SchemaValidationError(
                    f"sha256 mismatch on attachment {att.filename!r}: "
                    f"declared {att.sha256}, downloaded {actual_sha}"
                )

            # Build the OneDrive target path: <root>raw/<message_id>/<filename>
            target_path = self._build_target_path(
                onedrive_root=onedrive_root,
                message_id=message_id,
                filename=att.filename,
            )

            try:
                final_path = await self._graph.upload_to_onedrive_via_session(
                    drive_item_path=target_path,
                    content=content,
                )
            except GraphError:
                raise
            except Exception as exc:
                raise GraphError(
                    f"upload_to_onedrive_via_session raised for {att.filename!r}: {exc}"
                ) from exc

            staged.append(
                StagedAttachment(
                    filename=att.filename,
                    sha256=att.sha256,
                    size=att.size,
                    content_bytes=content,
                    onedrive_path=final_path,
                    content_type=att.content_type,
                )
            )

            # Update seen_attachments memory after each successful stage so a
            # mid-batch failure leaves a consistent dedup index.
            self._memory.append_seen_attachment(
                {
                    "contract_id": contract_id,
                    "client_name": client_name,
                    "sha256": att.sha256,
                    "filename": att.filename,
                    "size": att.size,
                    "message_id": message_id,
                    "onedrive_path": final_path,
                    "received_at": when.isoformat(),
                }
            )

        return StagedAttachments(
            items=staged,
            message_id=message_id,
            contract_id=contract_id,
        )

    @staticmethod
    def _build_target_path(
        *,
        onedrive_root: str,
        message_id: str,
        filename: str,
    ) -> str:
        # Trim filesystem-hostile chars from the message_id segment (Graph IDs are
        # base64-ish and contain '+' / '/' which OneDrive rejects in path segments).
        safe_msg_id = message_id.replace("/", "_").replace("+", "-").replace("=", "")
        return f"{onedrive_root}raw/{safe_msg_id}/{filename}"

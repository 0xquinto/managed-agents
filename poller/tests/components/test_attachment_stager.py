"""AttachmentStager tests — Graph download → sha256 verify → OneDrive upload → seen_attachments."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from poller.adapters.memory import LocalFilesystemBackend, MemoryStoreClient
from poller.components.attachment_stager import (
    AttachmentStager,
    StagedAttachments,
)
from poller.exceptions import GraphError, SchemaValidationError
from poller.schemas import AttachmentMeta, EmailMeta  # noqa: F401  (EmailMeta used elsewhere)


class _FakeGraph:
    """In-memory GraphAdapter substitute. Records uploads."""

    def __init__(
        self,
        *,
        attachments: dict[str, bytes],
        upload_failure: Exception | None = None,
    ) -> None:
        self._attachments = attachments
        self._upload_failure = upload_failure
        self.uploads: list[dict[str, Any]] = []

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[Any], str]:
        raise NotImplementedError

    async def download_attachment(
        self, *, message_id: str, attachment_id: str
    ) -> bytes:
        if attachment_id not in self._attachments:
            raise GraphError(f"unknown attachment {attachment_id}")
        return self._attachments[attachment_id]

    async def upload_to_onedrive_via_session(
        self,
        *,
        drive_item_path: str,
        content: bytes,
        chunk_size_bytes: int = 5 * 1024 * 1024,
    ) -> str:
        if self._upload_failure is not None:
            raise self._upload_failure
        self.uploads.append(
            {"path": drive_item_path, "size": len(content)}
        )
        return drive_item_path

    async def post_channel_message(
        self, *, team_id: str, channel_id: str, body_text: str
    ) -> str:
        raise NotImplementedError

    async def list_channel_replies(
        self, *, team_id: str, channel_id: str, message_id: str
    ) -> list[Any]:
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


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


def _make_meta(filename: str, sha: str, size: int) -> AttachmentMeta:
    return AttachmentMeta(
        message_attachment_id=f"att-{filename}",
        filename=filename,
        sha256=sha,
        size=size,
        content_type="application/pdf",
    )


async def test_stage_happy_path_writes_seen_attachments(
    memory: MemoryStoreClient,
) -> None:
    content = b"%PDF-1.7 fake bytes"
    sha = hashlib.sha256(content).hexdigest()
    meta = _make_meta("EF.pdf", sha, len(content))

    graph = _FakeGraph(attachments={"att-EF.pdf": content})
    stager = AttachmentStager(graph=graph, memory=memory)

    when = datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC)
    result = await stager.stage(
        contract_id="INS-2026-007",
        client_name="Tafi",
        onedrive_root="/Contracts/Tafi/",
        message_id="AAMk-msg-1",
        attachments=[meta],
        received_at=when,
    )

    assert isinstance(result, StagedAttachments)
    assert len(result.items) == 1
    assert result.items[0].sha256 == sha
    assert result.items[0].onedrive_path == "/Contracts/Tafi/raw/AAMk-msg-1/EF.pdf"
    assert result.items[0].content_bytes == content

    seen = memory.read_seen_attachments()
    assert len(seen) == 1
    assert seen[0]["contract_id"] == "INS-2026-007"
    assert seen[0]["sha256"] == sha
    assert seen[0]["received_at"] == when.isoformat()
    assert graph.uploads == [
        {"path": "/Contracts/Tafi/raw/AAMk-msg-1/EF.pdf", "size": len(content)}
    ]


async def test_stage_rejects_sha256_mismatch(memory: MemoryStoreClient) -> None:
    content = b"actual bytes"
    declared_sha = "f" * 64  # not the actual hash
    meta = _make_meta("EF.pdf", declared_sha, len(content))

    graph = _FakeGraph(attachments={"att-EF.pdf": content})
    stager = AttachmentStager(graph=graph, memory=memory)

    with pytest.raises(SchemaValidationError, match="sha256 mismatch"):
        await stager.stage(
            contract_id="INS-2026-007",
            client_name="Tafi",
            onedrive_root="/Contracts/Tafi/",
            message_id="m",
            attachments=[meta],
        )

    assert memory.read_seen_attachments() == []
    assert graph.uploads == []


async def test_stage_rejects_bad_onedrive_root(memory: MemoryStoreClient) -> None:
    graph = _FakeGraph(attachments={})
    stager = AttachmentStager(graph=graph, memory=memory)

    with pytest.raises(SchemaValidationError, match="onedrive_root"):
        await stager.stage(
            contract_id="INS-2026-007",
            client_name="Tafi",
            onedrive_root="Contracts/Tafi/",  # missing leading /
            message_id="m",
            attachments=[],
        )


async def test_stage_propagates_upload_error(memory: MemoryStoreClient) -> None:
    content = b"bytes"
    sha = hashlib.sha256(content).hexdigest()
    meta = _make_meta("EF.pdf", sha, len(content))

    graph = _FakeGraph(
        attachments={"att-EF.pdf": content},
        upload_failure=GraphError("rate limited", status_code=429),
    )
    stager = AttachmentStager(graph=graph, memory=memory)

    with pytest.raises(GraphError, match="rate limited"):
        await stager.stage(
            contract_id="INS-2026-007",
            client_name="Tafi",
            onedrive_root="/Contracts/Tafi/",
            message_id="m",
            attachments=[meta],
        )

    # No half-written seen_attachments either.
    assert memory.read_seen_attachments() == []


async def test_stage_sanitizes_messy_message_id(memory: MemoryStoreClient) -> None:
    content = b"x"
    sha = hashlib.sha256(content).hexdigest()
    meta = _make_meta("doc.pdf", sha, 1)

    graph = _FakeGraph(attachments={"att-doc.pdf": content})
    stager = AttachmentStager(graph=graph, memory=memory)

    result = await stager.stage(
        contract_id="INS-2026-007",
        client_name="Tafi",
        onedrive_root="/Contracts/Tafi/",
        message_id="AAMk/Foo+Bar=",
        attachments=[meta],
    )

    assert "/" not in result.items[0].onedrive_path.split("/raw/", 1)[1].split("/")[0]
    assert "+" not in result.items[0].onedrive_path
    assert "=" not in result.items[0].onedrive_path


async def test_session_resource_paths_property(memory: MemoryStoreClient) -> None:
    content = b"bytes"
    sha = hashlib.sha256(content).hexdigest()
    meta = _make_meta("EF.pdf", sha, len(content))

    graph = _FakeGraph(attachments={"att-EF.pdf": content})
    stager = AttachmentStager(graph=graph, memory=memory)

    result = await stager.stage(
        contract_id="INS-2026-007",
        client_name="Tafi",
        onedrive_root="/Contracts/Tafi/",
        message_id="m",
        attachments=[meta],
    )

    assert result.session_resource_paths == ["/mnt/session/uploads/EF.pdf"]

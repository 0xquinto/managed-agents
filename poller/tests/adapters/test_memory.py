"""MemoryStoreClient + LocalFilesystemBackend tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from poller.adapters.memory import (
    AnthropicMemoryBackend,
    LocalFilesystemBackend,
    MemoryBackendProtocol,
    MemoryStoreClient,
)
from poller.exceptions import MemoryStoreError


@pytest.fixture
def store(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


def test_local_backend_implements_protocol(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(root=tmp_path)
    assert isinstance(backend, MemoryBackendProtocol)


def test_write_then_read_json_roundtrip(store: MemoryStoreClient) -> None:
    store.write_json("hello.json", {"name": "world", "n": 42})
    assert store.read_json("hello.json") == {"name": "world", "n": 42}


def test_read_json_raises_on_missing(store: MemoryStoreClient) -> None:
    with pytest.raises(MemoryStoreError, match="path not found"):
        store.read_json("nope.json")


def test_read_json_raises_on_malformed(store: MemoryStoreClient) -> None:
    store.write_text("bad.json", "{not valid")
    with pytest.raises(MemoryStoreError, match="invalid JSON"):
        store.read_json("bad.json")


def test_text_roundtrip(store: MemoryStoreClient) -> None:
    store.write_text("tone_examples/2026-q1-followup.md", "Hola, gracias…")
    assert store.read_text("tone_examples/2026-q1-followup.md") == "Hola, gracias…"


def test_exists_and_list_dir(store: MemoryStoreClient) -> None:
    assert store.list_dir("tone_examples") == []
    store.write_text("tone_examples/a.md", "a")
    store.write_text("tone_examples/b.md", "b")
    listing = store.list_dir("tone_examples")
    assert sorted(listing) == ["tone_examples/a.md", "tone_examples/b.md"]
    assert store.exists("tone_examples/a.md")
    assert not store.exists("tone_examples/missing.md")


def test_read_registry_empty_when_absent(store: MemoryStoreClient) -> None:
    assert store.read_registry() == []


def test_registry_roundtrip(store: MemoryStoreClient) -> None:
    rows = [{"contract_id": "INS-2026-007", "client_name": "Tafi"}]
    store.write_registry(rows)
    assert store.read_registry() == rows


def test_registry_rejects_non_array(store: MemoryStoreClient) -> None:
    store.write_json("_registry.json", {"not": "an array"})
    with pytest.raises(MemoryStoreError, match="must be a JSON array"):
        store.read_registry()


def test_mail_cursor_none_when_absent(store: MemoryStoreClient) -> None:
    assert store.read_mail_cursor() is None


def test_mail_cursor_roundtrip(store: MemoryStoreClient) -> None:
    cursor = {"deltaLink": "https://graph.microsoft.com/v1.0/...?$deltaToken=abc"}
    store.write_mail_cursor(cursor)
    assert store.read_mail_cursor() == cursor


def test_seen_attachments_append(store: MemoryStoreClient) -> None:
    assert store.read_seen_attachments() == []
    store.append_seen_attachment(
        {"sha256": "a" * 64, "contract_id": "INS-2026-007", "message_id": "m1"}
    )
    store.append_seen_attachment(
        {"sha256": "b" * 64, "contract_id": "INS-2026-007", "message_id": "m2"}
    )
    seen = store.read_seen_attachments()
    assert len(seen) == 2
    assert seen[0]["sha256"] == "a" * 64
    assert seen[1]["sha256"] == "b" * 64


def test_anthropic_backend_methods_raise_until_implemented() -> None:
    backend = AnthropicMemoryBackend(store_id="mem_test", api_key="sk-ant-test")
    with pytest.raises(NotImplementedError, match="Gate 0b"):
        backend.read_bytes("anything")

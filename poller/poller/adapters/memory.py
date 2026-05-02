"""MemoryStoreClient — reads/writes durable poller state via the Anthropic Memory Stores API.

Per spec § 5.1 layout:

    /mnt/memory/
    ├── _registry.json
    ├── mail_cursor.json
    ├── seen_attachments.json
    ├── graph_token.json
    ├── priors/<contract_id>.json
    └── tone_examples/*.md

The poller writes to this store via the Memory Stores HTTP API; the agents read it
via mounted-filesystem paths inside their sessions. The poller never goes through
the mount.

Implementation note: the real Anthropic Memory Stores REST shape is not pinned down
in this codebase yet (research preview, gated by spec § 8.2 Gate 0b). This module
defines the protocol the rest of the poller depends on and ships a working
local-filesystem backend for tests + dev. The HTTP-backed implementation lives in
`AnthropicMemoryBackend` and uses placeholder paths that MUST be confirmed against
the live API before production deployment — see TODO markers below.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from poller.exceptions import MemoryStoreError


@runtime_checkable
class MemoryBackendProtocol(Protocol):
    """The byte-level read/write surface MemoryStoreClient layers over."""

    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes) -> None: ...
    def exists(self, path: str) -> bool: ...
    def list_dir(self, prefix: str) -> Iterable[str]: ...


class LocalFilesystemBackend:
    """Memory backend that maps store paths onto a local directory.

    Used by tests + local dev. NOT used in production — production uses
    AnthropicMemoryBackend.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _abs(self, path: str) -> Path:
        # Strip any leading slash so path is treated as relative to root.
        return self._root / path.lstrip("/")

    def read_bytes(self, path: str) -> bytes:
        full = self._abs(path)
        if not full.exists():
            raise MemoryStoreError(f"path not found: {path}")
        return full.read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._abs(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def exists(self, path: str) -> bool:
        return self._abs(path).exists()

    def list_dir(self, prefix: str) -> Iterable[str]:
        full = self._abs(prefix)
        if not full.exists() or not full.is_dir():
            return []
        return sorted(
            str(p.relative_to(self._root))
            for p in full.iterdir()
            if p.is_file()
        )


class AnthropicMemoryBackend:
    """Memory backend talking to the Anthropic Memory Stores API.

    TODO (spec § 8.2 Gate 0b): pin the actual REST shape against the live API
    before relying on this in production. Method signatures match
    LocalFilesystemBackend so the upstream MemoryStoreClient is backend-agnostic.
    """

    def __init__(self, *, store_id: str, api_key: str) -> None:
        self._store_id = store_id
        self._api_key = api_key
        # TODO: instantiate the real Anthropic SDK Memory Stores client here once
        # the shape is confirmed. Until then, every call below raises NotImplementedError.

    def read_bytes(self, path: str) -> bytes:  # pragma: no cover — not yet implementable
        raise NotImplementedError(
            "AnthropicMemoryBackend.read_bytes is gated on spec § 8.2 Gate 0b"
        )

    def write_bytes(self, path: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError(
            "AnthropicMemoryBackend.write_bytes is gated on spec § 8.2 Gate 0b"
        )

    def exists(self, path: str) -> bool:  # pragma: no cover
        raise NotImplementedError(
            "AnthropicMemoryBackend.exists is gated on spec § 8.2 Gate 0b"
        )

    def list_dir(self, prefix: str) -> Iterable[str]:  # pragma: no cover
        raise NotImplementedError(
            "AnthropicMemoryBackend.list_dir is gated on spec § 8.2 Gate 0b"
        )


class MemoryStoreClient:
    """High-level reader/writer for the six top-level keys per spec § 5.1.

    Layered over a backend that handles raw bytes. Json/text encoding lives here.
    """

    def __init__(self, backend: MemoryBackendProtocol) -> None:
        self._backend = backend

    # JSON helpers ---------------------------------------------------------

    def read_json(self, path: str) -> Any:
        try:
            raw = self._backend.read_bytes(path)
        except MemoryStoreError:
            raise
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MemoryStoreError(f"invalid JSON at {path}: {exc}") from exc

    def write_json(self, path: str, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        self._backend.write_bytes(path, data)

    # Text helpers ---------------------------------------------------------

    def read_text(self, path: str) -> str:
        return self._backend.read_bytes(path).decode("utf-8")

    def write_text(self, path: str, value: str) -> None:
        self._backend.write_bytes(path, value.encode("utf-8"))

    # Existence + listing --------------------------------------------------

    def exists(self, path: str) -> bool:
        return self._backend.exists(path)

    def list_dir(self, prefix: str) -> list[str]:
        return list(self._backend.list_dir(prefix))

    # Convenience accessors for the six canonical keys ---------------------

    def read_registry(self) -> list[dict[str, Any]]:
        if not self.exists("_registry.json"):
            return []
        result = self.read_json("_registry.json")
        if not isinstance(result, list):
            raise MemoryStoreError("_registry.json must be a JSON array")
        return result

    def write_registry(self, rows: list[dict[str, Any]]) -> None:
        self.write_json("_registry.json", rows)

    def read_mail_cursor(self) -> dict[str, Any] | None:
        if not self.exists("mail_cursor.json"):
            return None
        result = self.read_json("mail_cursor.json")
        if not isinstance(result, dict):
            raise MemoryStoreError("mail_cursor.json must be a JSON object")
        return result

    def write_mail_cursor(self, cursor: dict[str, Any]) -> None:
        self.write_json("mail_cursor.json", cursor)

    def read_seen_attachments(self) -> list[dict[str, Any]]:
        if not self.exists("seen_attachments.json"):
            return []
        result = self.read_json("seen_attachments.json")
        if not isinstance(result, list):
            raise MemoryStoreError("seen_attachments.json must be a JSON array")
        return result

    def append_seen_attachment(self, entry: dict[str, Any]) -> None:
        existing = self.read_seen_attachments()
        existing.append(entry)
        self.write_json("seen_attachments.json", existing)

"""EmailGate — 5-stage pre-spawn filter. Per spec § 2.2.

Each inbound email passes through five stages in order; any rejection short-circuits
the rest. Successful exit produces a ResolverKickoff payload ready for ResolverStep.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from poller.adapters.memory import MemoryStoreClient
from poller.schemas import (
    AttachmentMeta,
    EmailMeta,
    RegistryRow,
    ResolverKickoff,
)

GateOutcome = Literal["spawn", "reject", "defer"]


@dataclass
class GateDecision:
    """The result of running an email through EmailGate."""

    outcome: GateOutcome
    reason: str
    kickoff: ResolverKickoff | None = None
    duplicate_of: str | None = None  # contract_id that already saw all attachments
    attachment_hashes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage configuration
# ---------------------------------------------------------------------------

COSMETIC_BYTE_THRESHOLD = 5 * 1024  # 5 KB
COSMETIC_CONTENT_TYPES = frozenset({"image/png", "image/jpeg"})

THREAD_COOLDOWN_SECONDS = 60
SENDER_HOURLY_CAP = 6


# ---------------------------------------------------------------------------
# Per-thread / per-sender rate-limit ledger
# ---------------------------------------------------------------------------


@dataclass
class _SpawnLedger:
    """In-memory ledger of recent spawns for rate-limit checks.

    Persisted in the memory store between scheduler ticks at
    `email_gate_ledger.json`. Truncated on every read to drop entries older
    than the longest enforced window (1 hour).
    """

    # list of {timestamp_unix: float, conversationId: str, sender: str}
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, *, conversation_id: str, sender: str, when: float) -> None:
        self.entries.append(
            {"timestamp_unix": when, "conversationId": conversation_id, "sender": sender}
        )

    def thread_spawns_within(self, *, conversation_id: str, seconds: int, now: float) -> int:
        cutoff = now - seconds
        return sum(
            1
            for e in self.entries
            if e["conversationId"] == conversation_id and e["timestamp_unix"] >= cutoff
        )

    def sender_spawns_within(self, *, sender: str, seconds: int, now: float) -> int:
        cutoff = now - seconds
        return sum(
            1 for e in self.entries if e["sender"] == sender and e["timestamp_unix"] >= cutoff
        )

    def trim(self, *, now: float, keep_seconds: int = 3600) -> None:
        cutoff = now - keep_seconds
        self.entries = [e for e in self.entries if e["timestamp_unix"] >= cutoff]


# ---------------------------------------------------------------------------
# EmailGate
# ---------------------------------------------------------------------------


class EmailGate:
    """Runs an inbound email through five stages and returns a GateDecision.

    Inputs are an EmailMeta plus the raw attachment metadata from the Graph SDK
    (so the Gate can see `isInline` flags + actual byte sizes, which the
    AttachmentMeta schema does not carry — those flags are gate-only).
    """

    LEDGER_PATH = "email_gate_ledger.json"

    def __init__(self, *, memory: MemoryStoreClient, clock: Callable[[], float] | None = None) -> None:
        self._memory = memory
        # Injectable clock for deterministic testing of rate limits.
        self._clock = clock or (lambda: datetime.now(tz=UTC).timestamp())

    def evaluate(
        self,
        *,
        email: EmailMeta,
        raw_attachments: list[dict[str, Any]],
    ) -> GateDecision:
        # Stage 1
        if not raw_attachments:
            return GateDecision(outcome="reject", reason="no-op email (no attachments)")

        # Stage 2
        substantive = self._strip_cosmetic(raw_attachments)
        if not substantive:
            return GateDecision(outcome="reject", reason="cosmetic-only attachments")

        # Compute sha256 hashes per substantive attachment.
        hashed = self._hash_attachments(substantive)

        # Stage 3
        seen = self._memory.read_seen_attachments()
        dup_contract = self._all_seen_for_same_contract(hashed, seen)
        if dup_contract is not None:
            return GateDecision(
                outcome="reject",
                reason="duplicate-bundle",
                duplicate_of=dup_contract,
                attachment_hashes=[a["sha256"] for a in hashed],
            )

        # Stage 4
        ledger = self._read_ledger()
        now = self._clock()
        ledger.trim(now=now)

        if ledger.thread_spawns_within(
            conversation_id=email.conversationId,
            seconds=THREAD_COOLDOWN_SECONDS,
            now=now,
        ) > 0:
            return GateDecision(
                outcome="defer",
                reason=f"thread cooldown ({THREAD_COOLDOWN_SECONDS}s)",
            )

        if ledger.sender_spawns_within(
            sender=email.from_, seconds=3600, now=now
        ) >= SENDER_HOURLY_CAP:
            return GateDecision(
                outcome="reject",
                reason=f"rate-limit-tripped (sender>{SENDER_HOURLY_CAP}/hr)",
            )

        # Stage 5 — build the kickoff
        registry = self._read_registry()
        candidate_hashes = self._slice_seen_for_candidates(seen, registry)

        kickoff = ResolverKickoff(
            email=email,
            attachments=[AttachmentMeta.model_validate(a) for a in hashed],
            registry=registry,
            attachment_hashes_seen_for_candidate=candidate_hashes,
        )

        # Record the spawn in the ledger.
        ledger.add(conversation_id=email.conversationId, sender=email.from_, when=now)
        self._write_ledger(ledger)

        return GateDecision(
            outcome="spawn",
            reason="ok",
            kickoff=kickoff,
            attachment_hashes=[a["sha256"] for a in hashed],
        )

    # Stage helpers --------------------------------------------------------

    @staticmethod
    def _strip_cosmetic(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            a
            for a in raw
            if not (
                a.get("isInline", False)
                or (
                    a.get("size", 0) < COSMETIC_BYTE_THRESHOLD
                    and a.get("content_type", "") in COSMETIC_CONTENT_TYPES
                )
            )
        ]

    @staticmethod
    def _hash_attachments(attachments: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for a in attachments:
            payload = a.get("content_bytes")
            if payload is None:
                # Allow caller to pre-supply sha256 (e.g., when the bytes are too
                # large to keep in memory and the hash was streamed during download).
                if "sha256" not in a:
                    raise ValueError(
                        f"attachment {a.get('filename')!r} missing both content_bytes and sha256"
                    )
                out.append(a)
                continue
            digest = hashlib.sha256(payload).hexdigest()
            entry = {**a, "sha256": digest}
            entry.pop("content_bytes", None)
            out.append(entry)
        return out

    @staticmethod
    def _all_seen_for_same_contract(
        hashed: list[dict[str, Any]],
        seen: list[dict[str, Any]],
    ) -> str | None:
        """If every hash in `hashed` appears in `seen` under the same contract_id, return it."""
        contracts_per_hash: list[set[str]] = []
        for a in hashed:
            sha = a["sha256"]
            contracts = {e["contract_id"] for e in seen if e["sha256"] == sha}
            if not contracts:
                return None
            contracts_per_hash.append(contracts)

        if not contracts_per_hash:
            return None
        common = set.intersection(*contracts_per_hash)
        if len(common) == 1:
            return next(iter(common))
        return None

    @staticmethod
    def _slice_seen_for_candidates(
        seen: list[dict[str, Any]],
        registry: list[RegistryRow],
    ) -> dict[str, list[str]]:
        """Build the {contract_id: [seen_sha256, ...]} map for resolver kickoff."""
        result: dict[str, list[str]] = {row.contract_id: [] for row in registry}
        for entry in seen:
            cid = entry.get("contract_id")
            if cid in result:
                result[cid].append(entry["sha256"])
        return result

    # Memory I/O -----------------------------------------------------------

    def _read_registry(self) -> list[RegistryRow]:
        raw = self._memory.read_registry()
        return [RegistryRow.model_validate(r) for r in raw]

    def _read_ledger(self) -> _SpawnLedger:
        if not self._memory.exists(self.LEDGER_PATH):
            return _SpawnLedger()
        raw = self._memory.read_json(self.LEDGER_PATH)
        if not isinstance(raw, list):
            return _SpawnLedger()
        return _SpawnLedger(entries=raw)

    def _write_ledger(self, ledger: _SpawnLedger) -> None:
        self._memory.write_json(self.LEDGER_PATH, ledger.entries)

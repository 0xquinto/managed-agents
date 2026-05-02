"""EmailGate tests — exercises all five stages."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from poller.adapters.memory import LocalFilesystemBackend, MemoryStoreClient
from poller.components.email_gate import EmailGate, GateDecision
from poller.schemas import EmailMeta


def _email(conversation_id: str = "conv-1", sender: str = "ana@tafi.com.ar") -> EmailMeta:
    return EmailMeta.model_validate(
        {
            "from": sender,
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Subject",
            "conversationId": conversation_id,
            "messageId": "m-1",
            "body_text": "body",
            "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
        }
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStoreClient:
    return MemoryStoreClient(backend=LocalFilesystemBackend(root=tmp_path))


class Clock:
    """Deterministic clock for rate-limit tests; mutate `.now` to advance."""

    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fixed_clock() -> Clock:
    """Fresh deterministic clock per test."""
    return Clock()


def _gate(memory: MemoryStoreClient, fixed_clock: Clock) -> EmailGate:
    return EmailGate(memory=memory, clock=fixed_clock)


# Stage 1 -------------------------------------------------------------------


def test_stage1_rejects_no_attachments(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    gate = _gate(memory, fixed_clock)
    decision = gate.evaluate(email=_email(), raw_attachments=[])

    assert decision.outcome == "reject"
    assert "no-op email" in decision.reason


# Stage 2 -------------------------------------------------------------------


def test_stage2_rejects_inline_only(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    gate = _gate(memory, fixed_clock)
    inline_signature = {
        "isInline": True,
        "filename": "signature.png",
        "size": 200,
        "content_type": "image/png",
        "content_bytes": b"\x89PNG fake",
        "message_attachment_id": "att_inline",
    }
    decision = gate.evaluate(email=_email(), raw_attachments=[inline_signature])

    assert decision.outcome == "reject"
    assert "cosmetic-only" in decision.reason


def test_stage2_rejects_small_cosmetic_image(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    gate = _gate(memory, fixed_clock)
    tiny_jpeg = {
        "isInline": False,
        "filename": "logo.jpg",
        "size": 1024,  # 1 KB, below 5 KB threshold
        "content_type": "image/jpeg",
        "content_bytes": b"\xff\xd8\xff fake",
        "message_attachment_id": "att_logo",
    }
    decision = gate.evaluate(email=_email(), raw_attachments=[tiny_jpeg])

    assert decision.outcome == "reject"
    assert "cosmetic-only" in decision.reason


def test_stage2_keeps_large_image(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    """An image larger than 5 KB is NOT cosmetic — could be a scanned doc."""
    gate = _gate(memory, fixed_clock)
    big_jpeg = {
        "isInline": False,
        "filename": "scan.jpg",
        "size": 200_000,  # 200 KB
        "content_type": "image/jpeg",
        "content_bytes": b"\xff\xd8\xff" + b"x" * 1024,
        "message_attachment_id": "att_scan",
    }
    decision = gate.evaluate(email=_email(), raw_attachments=[big_jpeg])

    assert decision.outcome == "spawn"


# Stage 3 -------------------------------------------------------------------


def test_stage3_rejects_full_duplicate_bundle(
    memory: MemoryStoreClient,
    fixed_clock: Clock,
) -> None:
    """When all post-cosmetic attachments are already seen for the same contract, reject."""
    gate = _gate(memory, fixed_clock)

    pdf_bytes = b"%PDF-fake-content"
    csv_bytes = b"col1,col2\n1,2\n"
    import hashlib

    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()

    memory.append_seen_attachment(
        {"sha256": pdf_sha, "contract_id": "INS-2026-007", "message_id": "prior-1"}
    )
    memory.append_seen_attachment(
        {"sha256": csv_sha, "contract_id": "INS-2026-007", "message_id": "prior-1"}
    )

    decision = gate.evaluate(
        email=_email(),
        raw_attachments=[
            {
                "isInline": False,
                "filename": "Tafi.pdf",
                "size": len(pdf_bytes),
                "content_type": "application/pdf",
                "content_bytes": pdf_bytes,
                "message_attachment_id": "att_pdf",
            },
            {
                "isInline": False,
                "filename": "Tafi.csv",
                "size": len(csv_bytes),
                "content_type": "text/csv",
                "content_bytes": csv_bytes,
                "message_attachment_id": "att_csv",
            },
        ],
    )

    assert decision.outcome == "reject"
    assert decision.reason == "duplicate-bundle"
    assert decision.duplicate_of == "INS-2026-007"
    assert pdf_sha in decision.attachment_hashes


def test_stage3_passes_when_one_attachment_is_new(
    memory: MemoryStoreClient,
    fixed_clock: Clock,
) -> None:
    """If even one post-cosmetic attachment is new, spawn."""
    gate = _gate(memory, fixed_clock)

    pdf_bytes = b"%PDF-old-content"
    new_csv_bytes = b"col1,col2\n9,9\n"

    import hashlib

    memory.append_seen_attachment(
        {
            "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "contract_id": "INS-2026-007",
            "message_id": "prior-1",
        }
    )

    decision = gate.evaluate(
        email=_email(),
        raw_attachments=[
            {
                "isInline": False,
                "filename": "old.pdf",
                "size": len(pdf_bytes),
                "content_type": "application/pdf",
                "content_bytes": pdf_bytes,
                "message_attachment_id": "att_old",
            },
            {
                "isInline": False,
                "filename": "new.csv",
                "size": len(new_csv_bytes),
                "content_type": "text/csv",
                "content_bytes": new_csv_bytes,
                "message_attachment_id": "att_new",
            },
        ],
    )

    assert decision.outcome == "spawn"


# Stage 4 -------------------------------------------------------------------


def test_stage4_thread_cooldown_defers_back_to_back_emails(
    memory: MemoryStoreClient, fixed_clock: Clock
) -> None:
    """Two spawns on the same conversationId within 60 seconds → second is deferred."""
    gate = _gate(memory, fixed_clock)
    attachment = {
        "isInline": False,
        "filename": "doc.pdf",
        "size": 50_000,
        "content_type": "application/pdf",
        "content_bytes": b"%PDF-content-1",
        "message_attachment_id": "att_1",
    }

    first = gate.evaluate(email=_email("conv-shared"), raw_attachments=[attachment])
    assert first.outcome == "spawn"

    fixed_clock.now += 30  # 30s later, well within 60s cooldown

    attachment2 = {**attachment, "content_bytes": b"%PDF-content-2", "message_attachment_id": "att_2"}
    second = gate.evaluate(email=_email("conv-shared"), raw_attachments=[attachment2])
    assert second.outcome == "defer"
    assert "thread cooldown" in second.reason


def test_stage4_thread_cooldown_clears_after_window(
    memory: MemoryStoreClient, fixed_clock: Clock
) -> None:
    gate = _gate(memory, fixed_clock)
    attachment = {
        "isInline": False,
        "filename": "doc.pdf",
        "size": 50_000,
        "content_type": "application/pdf",
        "content_bytes": b"%PDF-content-3",
        "message_attachment_id": "att_3",
    }

    first = gate.evaluate(email=_email("conv-A"), raw_attachments=[attachment])
    assert first.outcome == "spawn"

    fixed_clock.now += 61  # past 60s cooldown

    attachment2 = {**attachment, "content_bytes": b"%PDF-content-4", "message_attachment_id": "att_4"}
    second = gate.evaluate(email=_email("conv-A"), raw_attachments=[attachment2])
    assert second.outcome == "spawn"


def test_stage4_sender_hourly_cap(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    """7th spawn from the same sender within an hour is rejected."""
    gate = _gate(memory, fixed_clock)

    for i in range(6):
        attachment = {
            "isInline": False,
            "filename": f"doc-{i}.pdf",
            "size": 50_000,
            "content_type": "application/pdf",
            "content_bytes": f"%PDF-{i}".encode(),
            "message_attachment_id": f"att_{i}",
        }
        # Different conversationIds to avoid thread cooldown.
        decision = gate.evaluate(email=_email(f"conv-{i}"), raw_attachments=[attachment])
        assert decision.outcome == "spawn", f"iteration {i} should have spawned"
        fixed_clock.now += 65  # advance past thread cooldown

    seventh = gate.evaluate(
        email=_email("conv-7"),
        raw_attachments=[
            {
                "isInline": False,
                "filename": "doc-7.pdf",
                "size": 50_000,
                "content_type": "application/pdf",
                "content_bytes": b"%PDF-7",
                "message_attachment_id": "att_7",
            }
        ],
    )
    assert seventh.outcome == "reject"
    assert "rate-limit-tripped" in seventh.reason


# Stage 5 -------------------------------------------------------------------


def test_stage5_builds_kickoff_with_registry_and_candidate_slice(
    memory: MemoryStoreClient,
    fixed_clock: Clock,
) -> None:
    gate = _gate(memory, fixed_clock)

    memory.write_registry(
        [
            {
                "contract_id": "INS-2026-007",
                "client_name": "Tafi",
                "sender_addresses": ["ana@tafi.com.ar"],
                "subject_tag": None,
                "onedrive_path": "/Contracts/Tafi/",
                "teams_channel_id": "19:abc",
                "status": "open",
                "opened_at": "2026-04-12T09:00:00Z",
            },
            {
                "contract_id": "INS-2026-008",
                "client_name": "Other",
                "sender_addresses": ["ceo@other.com"],
                "subject_tag": None,
                "onedrive_path": "/Contracts/Other/",
                "teams_channel_id": "19:other",
                "status": "open",
                "opened_at": "2026-04-15T09:00:00Z",
            },
        ]
    )
    import hashlib

    prior_pdf_sha = hashlib.sha256(b"old-pdf").hexdigest()
    memory.append_seen_attachment(
        {"sha256": prior_pdf_sha, "contract_id": "INS-2026-007", "message_id": "prior-007"}
    )

    pdf_bytes = b"%PDF-Tafi-update"
    decision = gate.evaluate(
        email=_email(),
        raw_attachments=[
            {
                "isInline": False,
                "filename": "Tafi-update.pdf",
                "size": len(pdf_bytes),
                "content_type": "application/pdf",
                "content_bytes": pdf_bytes,
                "message_attachment_id": "att_pdf",
            }
        ],
    )

    assert decision.outcome == "spawn"
    assert decision.kickoff is not None
    kickoff = decision.kickoff
    assert len(kickoff.registry) == 2
    assert kickoff.attachment_hashes_seen_for_candidate["INS-2026-007"] == [prior_pdf_sha]
    assert kickoff.attachment_hashes_seen_for_candidate["INS-2026-008"] == []
    assert len(kickoff.attachments) == 1
    assert kickoff.attachments[0].filename == "Tafi-update.pdf"


def test_stage5_records_spawn_in_ledger(memory: MemoryStoreClient, fixed_clock: Clock) -> None:
    gate = _gate(memory, fixed_clock)
    attachment = {
        "isInline": False,
        "filename": "doc.pdf",
        "size": 50_000,
        "content_type": "application/pdf",
        "content_bytes": b"%PDF-record-test",
        "message_attachment_id": "att_rec",
    }

    decision = gate.evaluate(email=_email(), raw_attachments=[attachment])
    assert decision.outcome == "spawn"

    ledger = memory.read_json("email_gate_ledger.json")
    assert len(ledger) == 1
    assert ledger[0]["conversationId"] == "conv-1"
    assert ledger[0]["sender"] == "ana@tafi.com.ar"


# GateDecision shape --------------------------------------------------------


def test_gate_decision_default_attachment_hashes_empty() -> None:
    d = GateDecision(outcome="reject", reason="x")
    assert d.attachment_hashes == []
    assert d.duplicate_of is None
    assert d.kickoff is None

"""Schema tests — validates the contract surfaces between poller and managed agents."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from poller.schemas import (
    EmailContextExcerpt,
    EmailMeta,
    IngestionEnvelope,
    IngestionKickoff,
    ManifestV3,
    ResolverEnvelope,
    ResolverKickoff,
)


def test_resolver_kickoff_accepts_valid_payload() -> None:
    payload = {
        "email": {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Re: Análisis financiero Q1",
            "conversationId": "AAQk-conv-1",
            "messageId": "AAMk-msg-1",
            "body_text": "Hola, te envío…",
            "received_at": datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC),
        },
        "attachments": [
            {
                "message_attachment_id": "att_1",
                "filename": "EF Tafi 2025 v3.pdf",
                "sha256": "a" * 64,
                "size": 1543210,
                "content_type": "application/pdf",
            }
        ],
        "registry": [
            {
                "contract_id": "INS-2026-007",
                "client_name": "Financiera Tafi",
                "sender_addresses": ["ana@tafi.com.ar"],
                "subject_tag": None,
                "onedrive_path": "/Contracts/Tafi/",
                "teams_channel_id": "19:abc@thread.tacv2",
                "status": "open",
                "opened_at": datetime(2026, 4, 12, 9, 0, 0, tzinfo=UTC),
            }
        ],
        "attachment_hashes_seen_for_candidate": {"INS-2026-007": ["b" * 64]},
    }

    result = ResolverKickoff.model_validate(payload)

    assert result.email.from_ == "ana@tafi.com.ar"
    assert result.attachments[0].sha256 == "a" * 64
    assert result.registry[0].contract_id == "INS-2026-007"


def test_resolver_kickoff_rejects_invalid_contract_id() -> None:
    payload = {
        "email": {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Subject",
            "conversationId": "c",
            "messageId": "m",
            "body_text": "body",
            "received_at": "2026-05-01T14:22:11Z",
        },
        "attachments": [],
        "registry": [
            {
                "contract_id": "BAD-FORMAT",
                "client_name": "Tafi",
                "sender_addresses": ["ana@tafi.com.ar"],
                "subject_tag": None,
                "onedrive_path": "/x",
                "teams_channel_id": "19:t",
                "status": "open",
                "opened_at": "2026-04-12T09:00:00Z",
            }
        ],
        "attachment_hashes_seen_for_candidate": {},
    }

    with pytest.raises(ValidationError, match="String should match pattern"):
        ResolverKickoff.model_validate(payload)


def test_resolver_envelope_accepts_continuation() -> None:
    payload = {
        "decision": "continuation",
        "contract_id": "INS-2026-007",
        "confidence": 0.95,
        "rationale_short": "exact sender + thread match",
        "superseded_by_prior": False,
        "superseded_reason": None,
        "triage_payload": None,
        "new_contract_proposal": None,
    }

    result = ResolverEnvelope.model_validate(payload)

    assert result.decision == "continuation"
    assert result.contract_id == "INS-2026-007"
    assert result.confidence == 0.95


def test_resolver_envelope_accepts_triage() -> None:
    payload = {
        "decision": "triage",
        "contract_id": None,
        "confidence": 0.4,
        "rationale_short": "ambiguous consultant forward",
        "superseded_by_prior": False,
        "superseded_reason": None,
        "triage_payload": {
            "question": "Which contract is this?",
            "candidates": [
                {"contract_id": "INS-2026-007", "score": 0.4, "reason": "domain hint"}
            ],
            "inferred_new_contract": {
                "client_name_guess": "XYZ",
                "sender_domain": "advisor.com",
            },
        },
        "new_contract_proposal": None,
    }

    result = ResolverEnvelope.model_validate(payload)

    assert result.decision == "triage"
    assert result.triage_payload is not None
    assert result.triage_payload.candidates[0].contract_id == "INS-2026-007"


def test_ingestion_kickoff_accepts_valid_payload() -> None:
    payload = {
        "contract_id": "INS-2026-007",
        "client_name": "Financiera Tafi",
        "input_files": [
            "input/INS-2026-007/EF Tafi 2025 v3.pdf",
            "input/INS-2026-007/Cartera Total TAFI.csv",
        ],
        "email_context": {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "Re: Q1",
            "conversationId": "c",
            "messageId": "m",
            "body_text_excerpt": "Hola...",
            "received_at": "2026-05-01T14:22:11Z",
            "language": "es",
        },
        "memory_paths": {
            "priors": "/mnt/memory/priors/INS-2026-007.json",
            "tone_examples_dir": "/mnt/memory/tone_examples/",
        },
    }

    result = IngestionKickoff.model_validate(payload)

    assert result.contract_id == "INS-2026-007"
    assert result.email_context.language == "es"
    assert result.memory_paths.priors == "/mnt/memory/priors/INS-2026-007.json"


def test_ingestion_envelope_ok() -> None:
    payload = {
        "status": "ok",
        "normalized_dir": "/mnt/session/out/INS-2026-007/normalized/",
        "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
        "missing_fields": [],
    }

    result = IngestionEnvelope.model_validate(payload)

    assert result.status == "ok"
    assert result.missing_fields == []


def test_ingestion_envelope_blocked() -> None:
    payload = {
        "status": "blocked",
        "normalized_dir": "/mnt/session/out/INS-2026-007/normalized/",
        "manifest_path": "/mnt/session/out/INS-2026-007/manifest.json",
        "missing_fields": ["cashflow_2024"],
    }

    result = IngestionEnvelope.model_validate(payload)

    assert result.status == "blocked"
    assert result.missing_fields == ["cashflow_2024"]


def test_manifest_v3_with_client_email_draft() -> None:
    payload = {
        "contract_id": "INS-2026-007",
        "entity": {"name": "Tafi"},
        "periods": ["2024", "2025"],
        "pdf_extraction": {"method": "pypdf", "pages": 39, "avg_chars_per_page": 2100},
        "csv_extraction": {"rows": 145000, "cols": 24},
        "files_classified": [],
        "normalized_paths": {"pnl": "p", "balance": "b", "cashflow": "c"},
        "quality_flags": [],
        "reconciliations": {
            "balance_sheet_2025": {"diff": 0.0, "balanced": True},
            "balance_sheet_2024": {"diff": 0.0, "balanced": True},
            "cashflow_2025": {"diff": 0.0, "reconciled": True},
            "cashflow_2024": {"diff": 0.0, "reconciled": True},
        },
        "missing_fields": ["cashflow_2024"],
        "outputs": [],
        "client_email_draft": {
            "to": ["ana@tafi.com.ar"],
            "cc": [],
            "subject": "Re: Análisis Q1",
            "in_reply_to_message_id": "AAMk-original",
            "language": "es",
            "body": "Hola Ana, gracias por enviar la información, te escribo "
            "para pedirte algunos datos adicionales que faltan.",
            "missing_fields_referenced": ["cashflow_2024"],
            "tone_examples_consulted": ["tone_examples/2026-q1-followup.md"],
        },
        "triage_request": None,
    }

    result = ManifestV3.model_validate(payload)

    assert result.client_email_draft is not None
    assert result.client_email_draft.language == "es"
    assert "cashflow_2024" in result.client_email_draft.missing_fields_referenced


def test_manifest_v3_rejects_inconsistent_email_draft() -> None:
    payload = {
        "contract_id": "INS-2026-007",
        "entity": {},
        "periods": ["2024", "2025"],
        "pdf_extraction": {"method": "pypdf", "pages": 39, "avg_chars_per_page": 2100},
        "csv_extraction": {"rows": 100, "cols": 24},
        "files_classified": [],
        "normalized_paths": {},
        "quality_flags": [],
        "reconciliations": {
            "balance_sheet_2025": {"diff": 0.0, "balanced": True},
            "balance_sheet_2024": {"diff": 0.0, "balanced": True},
            "cashflow_2025": {"diff": 0.0, "reconciled": True},
            "cashflow_2024": {"diff": 0.0, "reconciled": True},
        },
        "missing_fields": ["cashflow_2024"],
        "outputs": [],
        "client_email_draft": {
            "to": ["ana@tafi.com.ar"],
            "cc": [],
            "subject": "S",
            "in_reply_to_message_id": "m",
            "language": "es",
            "body": "x" * 60,
            "missing_fields_referenced": ["cashflow_2024", "balance_sheet_q4_2024"],
            "tone_examples_consulted": [],
        },
        "triage_request": None,
    }

    with pytest.raises(ValidationError, match="missing_fields_referenced contains items"):
        ManifestV3.model_validate(payload)


def test_email_context_excerpt_trims_long_body() -> None:
    long_body = "a" * 1500
    email = EmailMeta.model_validate(
        {
            "from": "ana@tafi.com.ar",
            "to": ["contracts@insignia.com"],
            "cc": [],
            "subject": "S",
            "conversationId": "c",
            "messageId": "m",
            "body_text": long_body,
            "received_at": "2026-05-01T14:22:11Z",
        }
    )

    excerpt = EmailContextExcerpt.from_email_meta(email, language="es")

    assert len(excerpt.body_text_excerpt) <= 500
    assert excerpt.body_text_excerpt == long_body[:500]
    assert excerpt.from_ == email.from_

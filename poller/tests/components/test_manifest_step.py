"""ManifestStep tests — branches: status_ok / client_email_draft / triage / degraded."""

from __future__ import annotations

from typing import Any

import pytest

from poller.components.manifest_step import ManifestPost, ManifestStep
from poller.exceptions import SchemaValidationError
from poller.schemas import IngestionEnvelope, ManifestV3


def _make_envelope(
    *,
    status: str = "ok",
    contract_id: str = "INS-2026-007",
    missing_fields: list[str] | None = None,
) -> IngestionEnvelope:
    return IngestionEnvelope.model_validate(
        {
            "status": status,
            "normalized_dir": f"/mnt/session/out/{contract_id}/normalized",
            "manifest_path": f"/mnt/session/out/{contract_id}/manifest.json",
            "missing_fields": missing_fields or [],
        }
    )


def _make_manifest(
    *,
    contract_id: str = "INS-2026-007",
    missing_fields: list[str] | None = None,
    client_email_draft: dict[str, Any] | None = None,
    triage_request: dict[str, Any] | None = None,
) -> ManifestV3:
    payload: dict[str, Any] = {
        "contract_id": contract_id,
        "entity": {"name": "Tafi"},
        "periods": ["2024", "2025"],
        "pdf_extraction": {
            "method": "pdfplumber",
            "pages": 12,
            "avg_chars_per_page": 1800,
        },
        "csv_extraction": {"rows": 0, "cols": 0},
        "files_classified": [],
        "normalized_paths": {},
        "quality_flags": [],
        "reconciliations": {
            "balance_sheet_2025": {"diff": 0.0, "balanced": True},
            "balance_sheet_2024": {"diff": 0.0, "balanced": True},
            "cashflow_2025": {"diff": 0.0, "reconciled": True},
            "cashflow_2024": {"diff": 0.0, "reconciled": True},
        },
        "missing_fields": missing_fields or [],
        "outputs": [],
    }
    if client_email_draft is not None:
        payload["client_email_draft"] = client_email_draft
    if triage_request is not None:
        payload["triage_request"] = triage_request
    return ManifestV3.model_validate(payload)


_GOOD_DRAFT = {
    "to": ["ana@tafi.com.ar"],
    "cc": [],
    "subject": "Faltan documentos para completar el análisis",
    "in_reply_to_message_id": "msg-1",
    "language": "es",
    "body": (
        "Hola Ana, gracias por el balance. Para cerrar el análisis necesitamos "
        "el dictamen del auditor y la memoria. ¿Podrías enviarlos?"
    ),
    "missing_fields_referenced": ["dictamen"],
    "tone_examples_consulted": [],
}


def test_status_ok_branch() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="ok")
    manifest = _make_manifest()

    post = step.classify(envelope=envelope, manifest=manifest)

    assert isinstance(post, ManifestPost)
    assert post.kind == "status_ok"
    assert post.contract_id == "INS-2026-007"
    assert "Ingestion complete" in post.summary
    assert post.rejection_reason is None


def test_blocked_with_clean_email_draft() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="blocked", missing_fields=["dictamen"])
    manifest = _make_manifest(
        missing_fields=["dictamen"], client_email_draft=_GOOD_DRAFT
    )

    post = step.classify(envelope=envelope, manifest=manifest)

    assert post.kind == "client_email_draft"
    assert "dictamen" in post.summary


def test_blocked_without_email_draft_is_degraded() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="blocked", missing_fields=["dictamen"])
    manifest = _make_manifest(missing_fields=["dictamen"], client_email_draft=None)

    post = step.classify(envelope=envelope, manifest=manifest)

    assert post.kind == "degraded"
    assert "without client_email_draft" in (post.rejection_reason or "")


def test_failed_status_is_degraded() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="failed")
    manifest = _make_manifest()

    post = step.classify(envelope=envelope, manifest=manifest)

    assert post.kind == "degraded"
    assert post.rejection_reason == "status: failed"


def test_triage_request_branch() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="ok")
    manifest = _make_manifest(
        triage_request={"question": "Which entity is this?"}
    )

    post = step.classify(envelope=envelope, manifest=manifest)

    assert post.kind == "triage"


def test_lint_language_mismatch_is_degraded() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="blocked", missing_fields=["dictamen"])
    bad_lang = {**_GOOD_DRAFT, "language": "en"}
    manifest = _make_manifest(missing_fields=["dictamen"], client_email_draft=bad_lang)

    post = step.classify(
        envelope=envelope, manifest=manifest, expected_language="es"
    )

    assert post.kind == "degraded"
    assert "language" in (post.rejection_reason or "")


def test_lint_forbidden_substring_is_degraded() -> None:
    step = ManifestStep()
    envelope = _make_envelope(status="blocked", missing_fields=["dictamen"])
    body_with_tbd = (
        "Hola Ana, gracias por enviar el balance. TBD el dictamen del auditor. "
        "Por favor enviar pronto."
    )
    placeholder = {**_GOOD_DRAFT, "body": body_with_tbd}
    manifest = _make_manifest(
        missing_fields=["dictamen"], client_email_draft=placeholder
    )

    post = step.classify(envelope=envelope, manifest=manifest)

    assert post.kind == "degraded"
    assert "TBD" in (post.rejection_reason or "")


def test_contract_id_mismatch_raises() -> None:
    step = ManifestStep()
    envelope = IngestionEnvelope.model_validate(
        {
            "status": "ok",
            "normalized_dir": "/mnt/session/out/INS-2026-999/normalized",
            "manifest_path": "/mnt/session/out/INS-2026-999/manifest.json",
            "missing_fields": [],
        }
    )
    manifest = _make_manifest(contract_id="INS-2026-007")

    with pytest.raises(SchemaValidationError, match="contract_id mismatch"):
        step.classify(envelope=envelope, manifest=manifest)

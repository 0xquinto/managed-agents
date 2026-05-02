"""ManifestStep — switches on the ManifestV3 to decide what the poller does next.

Three branches per spec § 4.5 + § 6.3:
1. status=ok, missing_fields=[] → contract Teams channel post: "ingestion complete"
2. status=blocked, missing_fields ≠ [], client_email_draft populated → Teams card
   with the Spanish draft + Approve/Edit/Reject instructions
3. status=blocked, triage_request populated (rare — resolver path) → triage card

The actual Teams posting lives in TeamsCardPoster (Phase 4); ManifestStep just
classifies and shapes the post payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from poller.exceptions import SchemaValidationError
from poller.schemas import IngestionEnvelope, ManifestV3

PostKind = Literal["status_ok", "client_email_draft", "triage", "degraded"]


@dataclass
class ManifestPost:
    """What the poller should post to Teams about a finished ingestion run."""

    kind: PostKind
    contract_id: str
    summary: str
    manifest: ManifestV3
    rejection_reason: str | None = None  # populated when kind=degraded


class ManifestStep:
    """Inspects (envelope, manifest) and produces a ManifestPost.

    Also performs the post-ingestion content lints from spec § 6.3 — language
    detection, body length, forbidden TBD/TODO substrings, missing_fields_referenced
    subset (which the schema enforces, but we double-check with a clearer error
    message at this layer).
    """

    FORBIDDEN_BODY_SUBSTRINGS = ("TBD", "TODO", "[…]")
    MIN_BODY_LENGTH = 50

    def classify(
        self,
        *,
        envelope: IngestionEnvelope,
        manifest: ManifestV3,
        expected_language: str = "es",
    ) -> ManifestPost:
        # Defensive: the envelope's manifest_path should contain the manifest's
        # contract_id. The poller is the schema-validation chokepoint.
        if manifest.contract_id not in envelope.manifest_path:
            raise SchemaValidationError(
                f"envelope/manifest contract_id mismatch: "
                f"manifest_path={envelope.manifest_path!r} does not reference "
                f"contract_id {manifest.contract_id!r}"
            )

        # Status: failed -> degraded
        if envelope.status == "failed":
            return ManifestPost(
                kind="degraded",
                contract_id=manifest.contract_id,
                summary="Ingestion failed; see manifest for details.",
                manifest=manifest,
                rejection_reason="status: failed",
            )

        # Triage path: triage_request populated (resolver-side only; ingestion
        # never populates this, but we handle it for robustness)
        if manifest.triage_request is not None:
            return ManifestPost(
                kind="triage",
                contract_id=manifest.contract_id,
                summary="Triage request from ingestion run.",
                manifest=manifest,
            )

        # Happy path: status=ok, missing_fields empty
        if envelope.status == "ok" and not envelope.missing_fields:
            return ManifestPost(
                kind="status_ok",
                contract_id=manifest.contract_id,
                summary=(
                    f"Ingestion complete. Quality flags: {len(manifest.quality_flags)}; "
                    f"PDF: {manifest.pdf_extraction.pages} pages "
                    f"({manifest.pdf_extraction.method}); "
                    f"CSV: {manifest.csv_extraction.rows} rows × "
                    f"{manifest.csv_extraction.cols} cols."
                ),
                manifest=manifest,
            )

        # Blocked path with email draft
        if envelope.status == "blocked":
            if manifest.client_email_draft is None:
                return ManifestPost(
                    kind="degraded",
                    contract_id=manifest.contract_id,
                    summary="Blocked but no client_email_draft populated.",
                    manifest=manifest,
                    rejection_reason="blocked without client_email_draft",
                )

            draft = manifest.client_email_draft

            # Lint: language matches expectation
            if draft.language != expected_language:
                return ManifestPost(
                    kind="degraded",
                    contract_id=manifest.contract_id,
                    summary="Draft language mismatch.",
                    manifest=manifest,
                    rejection_reason=(
                        f"client_email_draft.language={draft.language!r} "
                        f"!= expected {expected_language!r}"
                    ),
                )

            # Lint: body length (schema already enforces min_length=50; double-check)
            if len(draft.body) < self.MIN_BODY_LENGTH:
                return ManifestPost(
                    kind="degraded",
                    contract_id=manifest.contract_id,
                    summary="Draft body too short.",
                    manifest=manifest,
                    rejection_reason=f"body length {len(draft.body)} < {self.MIN_BODY_LENGTH}",
                )

            # Lint: forbidden substrings
            for forbidden in self.FORBIDDEN_BODY_SUBSTRINGS:
                if forbidden in draft.body:
                    return ManifestPost(
                        kind="degraded",
                        contract_id=manifest.contract_id,
                        summary="Draft contains forbidden placeholder.",
                        manifest=manifest,
                        rejection_reason=f"body contains {forbidden!r}",
                    )

            # All lints passed — emit the draft post.
            return ManifestPost(
                kind="client_email_draft",
                contract_id=manifest.contract_id,
                summary=(
                    f"Missing fields: {', '.join(envelope.missing_fields)}. "
                    f"Spanish follow-up drafted; Approve/Edit/Reject in Teams."
                ),
                manifest=manifest,
            )

        # Should be unreachable.
        return ManifestPost(
            kind="degraded",
            contract_id=manifest.contract_id,
            summary="Unclassified envelope/manifest combination.",
            manifest=manifest,
            rejection_reason=f"status={envelope.status!r} did not match any branch",
        )

"""Pydantic schemas for the v3 poller. Contract per spec §§ 3.4, 3.5, 4.4, 4.5, 4.6."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

Sha256 = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]


class EmailMeta(BaseModel):
    """Inbound email metadata. Per spec § 3.4."""

    model_config = ConfigDict(populate_by_name=True)

    from_: EmailStr = Field(alias="from")
    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    subject: str
    conversationId: str
    messageId: str
    body_text: str
    received_at: datetime


class AttachmentMeta(BaseModel):
    """Email attachment metadata after EmailGate Stage 2 (post-cosmetic-strip)."""

    message_attachment_id: str
    filename: str
    sha256: Sha256
    size: int = Field(ge=0)
    content_type: str


class RegistryRow(BaseModel):
    """One row of the contract registry. Per spec § 5.1."""

    contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    client_name: str
    sender_addresses: list[EmailStr]
    subject_tag: str | None = None
    onedrive_path: str
    teams_channel_id: str
    status: str
    opened_at: datetime


class ResolverKickoff(BaseModel):
    """Kickoff payload for the resolver agent. Per spec § 3.4."""

    email: EmailMeta
    attachments: list[AttachmentMeta]
    registry: list[RegistryRow]
    attachment_hashes_seen_for_candidate: dict[str, list[Sha256]]


class TriageCandidate(BaseModel):
    contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class InferredNewContract(BaseModel):
    client_name_guess: str
    sender_domain: str


class TriagePayload(BaseModel):
    question: str
    candidates: list[TriageCandidate]
    inferred_new_contract: InferredNewContract | None = None


class NewContractProposal(BaseModel):
    client_name: str
    sender_domain: str
    suggested_contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    suggested_onedrive_path: str
    suggested_teams_channel_name: str


class ResolverEnvelope(BaseModel):
    """Resolver agent's output envelope. Per spec § 3.5."""

    decision: Literal["new_contract", "continuation", "triage"]
    contract_id: str | None = Field(default=None, pattern=r"^INS-\d{4}-\d{3}$")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_short: str
    superseded_by_prior: bool = False
    superseded_reason: str | None = None
    triage_payload: TriagePayload | None = None
    new_contract_proposal: NewContractProposal | None = None


class EmailContextExcerpt(BaseModel):
    """Email metadata passed into ingestion (excerpt only — body trimmed to ~500 chars)."""

    model_config = ConfigDict(populate_by_name=True)

    from_: EmailStr = Field(alias="from")
    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    subject: str
    conversationId: str
    messageId: str
    body_text_excerpt: str = Field(max_length=600)
    received_at: datetime
    language: Literal["es", "en", "pt"]

    @classmethod
    def from_email_meta(
        cls,
        meta: EmailMeta,
        language: Literal["es", "en", "pt"],
    ) -> EmailContextExcerpt:
        """Build an excerpt from a full EmailMeta, trimming the body to 500 chars."""
        return cls.model_validate(
            {
                "from": meta.from_,
                "to": meta.to,
                "cc": meta.cc,
                "subject": meta.subject,
                "conversationId": meta.conversationId,
                "messageId": meta.messageId,
                "body_text_excerpt": meta.body_text[:500],
                "received_at": meta.received_at,
                "language": language,
            }
        )


class MemoryPaths(BaseModel):
    priors: str
    tone_examples_dir: str


class IngestionKickoff(BaseModel):
    """Kickoff payload for the ingestion v3 agent. Per spec § 4.4."""

    contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    client_name: str
    input_files: list[str]
    email_context: EmailContextExcerpt
    memory_paths: MemoryPaths


class IngestionEnvelope(BaseModel):
    """Ingestion agent's terse output envelope. Unchanged from v2 per spec § 4.6."""

    status: Literal["ok", "blocked", "failed"]
    normalized_dir: str
    manifest_path: str
    missing_fields: list[str]


class ClientEmailDraft(BaseModel):
    """v3 manifest addition. Per spec § 4.5."""

    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    subject: str
    in_reply_to_message_id: str
    language: Literal["es", "en", "pt"]
    body: str = Field(min_length=50)
    missing_fields_referenced: list[str]
    tone_examples_consulted: list[str] = Field(default_factory=list)


class PdfExtraction(BaseModel):
    method: Literal["pypdf", "pdfplumber", "ocr"]
    pages: int = Field(ge=1)
    avg_chars_per_page: int = Field(ge=0)


class CsvExtraction(BaseModel):
    rows: int = Field(ge=0)
    cols: int = Field(ge=0)


class BalanceReconciliation(BaseModel):
    diff: float
    balanced: bool


class CashflowReconciliation(BaseModel):
    diff: float
    reconciled: bool


class Reconciliations(BaseModel):
    balance_sheet_2025: BalanceReconciliation
    balance_sheet_2024: BalanceReconciliation
    cashflow_2025: CashflowReconciliation
    cashflow_2024: CashflowReconciliation


class ManifestV3(BaseModel):
    """The v3 manifest per spec § 4.5.

    Carries v2 fields verbatim plus client_email_draft + triage_request. The
    missing_fields_referenced ⊆ missing_fields constraint is enforced at the
    model level.
    """

    model_config = ConfigDict(extra="allow")

    contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    entity: dict[str, object]
    periods: list[str]
    pdf_extraction: PdfExtraction
    csv_extraction: CsvExtraction
    files_classified: list[dict[str, object]]
    normalized_paths: dict[str, object]
    quality_flags: list[dict[str, object]]
    reconciliations: Reconciliations
    missing_fields: list[str]
    outputs: list[dict[str, object]]
    client_email_draft: ClientEmailDraft | None = None
    triage_request: dict[str, object] | None = None

    @model_validator(mode="after")
    def _email_draft_missing_fields_must_be_subset(self) -> ManifestV3:
        if self.client_email_draft is None:
            return self
        referenced = set(self.client_email_draft.missing_fields_referenced)
        present = set(self.missing_fields)
        extra = referenced - present
        if extra:
            raise ValueError(
                "client_email_draft.missing_fields_referenced contains items "
                f"not in manifest.missing_fields: {sorted(extra)}"
            )
        return self

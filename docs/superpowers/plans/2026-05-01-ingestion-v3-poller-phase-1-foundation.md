# Insignia Ingestion v3 Poller — Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the v3 poller Python project, lock in the Pydantic schemas that contract the poller against the two managed agents, and build the `GraphAdapter` that wraps Microsoft Graph SDK calls. End state: schemas validate the kickoff/envelope/manifest shapes from the spec, and `GraphAdapter` can list new mail via delta query against a fake Graph backend in tests.

**Architecture:** Single-process Python service. Adapter pattern isolates Microsoft Graph SDK + Anthropic SDK from business logic so each component is testable with mocks. Strict TDD: every component fails first, then minimal implementation passes. State (mail_cursor, seen_attachments, registry) flows through a thin `MemoryStoreClient` whose real-Anthropic backend ships in Phase 2.

**Tech stack:** Python 3.12, `msgraph-sdk-python` (Microsoft Graph), `pydantic` v2 (schemas), `pytest` + `pytest-asyncio` (tests), `ruff` (lint), `mypy` (types), `azure-identity` (Graph auth).

**Spec reference:** `docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md`. Cite as `spec § N.N`.

---

## Prerequisites NOT in this plan

These are NOT required to complete Phase 1 (mocks are fine), but are listed so the engineer knows what blocks Phase 2:
- Microsoft Graph app registration in Azure AD with the four permissions in spec § 2.4 (separate runbook).
- The `insignia_graph_credentials` vault with `client_id` + `client_secret` (lead-0 provisions in its track).
- Lead-0 orchestrator run producing deployed agent IDs (Phase 2 imports them; Phase 1 stubs them).

## File structure (Phase 1)

```
poller/
├── pyproject.toml            # project metadata + deps
├── README.md                 # one-page how-to-run
├── poller/
│   ├── __init__.py
│   ├── config.py             # Settings dataclass, env var loading
│   ├── schemas.py            # ResolverKickoff, ResolverEnvelope, IngestionKickoff, IngestionEnvelope, ManifestV3
│   ├── exceptions.py         # PollerError hierarchy
│   └── adapters/
│       ├── __init__.py
│       └── graph.py          # GraphAdapter — list_new_messages_via_delta() + protocol shape for later methods
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # shared fixtures
│   ├── test_schemas.py       # validates the four kickoff/envelope shapes + manifest v3 additions
│   ├── test_config.py        # env var loading, defaults, validation errors
│   └── adapters/
│       ├── __init__.py
│       └── test_graph.py     # mocks GraphServiceClient, asserts delta-query call shape
├── .python-version           # 3.12
└── ruff.toml                 # ruff config (line length 100, isort)
```

---

## Phase A — Project scaffolding (5 tasks)

### Task A.1: Create the project directory and pyproject.toml

**Files:**
- Create: `poller/pyproject.toml`
- Create: `poller/.python-version`
- Create: `poller/README.md`

- [ ] **Step 1: Create the `poller/` directory and `.python-version`**

```bash
mkdir -p /Users/diego/Dev/managed_agents/poller
echo "3.12" > /Users/diego/Dev/managed_agents/poller/.python-version
```

- [ ] **Step 2: Write `poller/pyproject.toml`**

```toml
[project]
name = "insignia-poller"
version = "0.1.0"
description = "Insignia ingestion v3 email-driven poller. See docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md."
requires-python = ">=3.12,<3.13"
dependencies = [
    "pydantic>=2.7,<3",
    "msgraph-sdk>=1.6,<2",
    "azure-identity>=1.17,<2",
    "anthropic>=0.30,<1",
    "structlog>=24.1,<25",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2,<9",
    "pytest-asyncio>=0.23,<1",
    "pytest-mock>=3.12,<4",
    "ruff>=0.5,<1",
    "mypy>=1.10,<2",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_ignores = true

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["poller*"]
```

- [ ] **Step 3: Write `poller/README.md`**

```markdown
# Insignia Poller

Implements the email-driven control plane for the Insignia ingestion v3 managed-agent pipeline.

## Run locally (development)

```bash
cd poller
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```

## Spec

See `../docs/superpowers/specs/2026-05-01-ingestion-v3-email-poller-design.md`.
```

- [ ] **Step 4: Commit**

```bash
cd /Users/diego/Dev/managed_agents
git add poller/pyproject.toml poller/.python-version poller/README.md
git commit -m "chore(poller): scaffold pyproject + readme for ingestion v3 poller"
```

### Task A.2: Add ruff configuration

**Files:**
- Create: `poller/ruff.toml`

- [ ] **Step 1: Write `poller/ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "UP",  # pyupgrade
    "SIM", # flake8-simplify
    "C4",  # flake8-comprehensions
]
ignore = ["E501"]  # line too long — handled by formatter

[lint.per-file-ignores]
"tests/**/*.py" = ["B011"]  # allow assert in tests
```

- [ ] **Step 2: Commit**

```bash
git add poller/ruff.toml
git commit -m "chore(poller): add ruff config"
```

### Task A.3: Create empty package modules

**Files:**
- Create: `poller/poller/__init__.py`
- Create: `poller/poller/adapters/__init__.py`
- Create: `poller/tests/__init__.py`
- Create: `poller/tests/adapters/__init__.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
cd /Users/diego/Dev/managed_agents/poller
mkdir -p poller/adapters tests/adapters
touch poller/__init__.py poller/adapters/__init__.py tests/__init__.py tests/adapters/__init__.py
```

- [ ] **Step 2: Add a one-line module docstring to `poller/__init__.py`**

```python
"""Insignia ingestion v3 poller — control plane for the email-driven managed-agent pipeline."""
```

- [ ] **Step 3: Commit**

```bash
git add poller/poller/ poller/tests/
git commit -m "chore(poller): scaffold package layout"
```

### Task A.4: Verify ruff and mypy run clean on the empty project

- [ ] **Step 1: Install dev dependencies into a venv**

```bash
cd /Users/diego/Dev/managed_agents/poller
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 2: Run ruff and mypy**

```bash
ruff check .
mypy poller
```

Expected: both commands exit 0 (no errors). If `mypy` complains about missing stubs for `msgraph` or `azure.identity`, add to `pyproject.toml`'s `[tool.mypy]`:

```toml
[[tool.mypy.overrides]]
module = ["msgraph.*", "azure.identity.*"]
ignore_missing_imports = true
```

- [ ] **Step 3: Commit any tweaks**

```bash
git add poller/pyproject.toml
git commit -m "chore(poller): silence mypy missing-stubs for msgraph/azure-identity"
```

(Skip this commit if step 2 was clean.)

### Task A.5: Add `poller/` to `.gitignore` for local artifacts

**Files:**
- Modify: `/Users/diego/Dev/managed_agents/.gitignore`

- [ ] **Step 1: Read current `.gitignore`**

```bash
cat /Users/diego/Dev/managed_agents/.gitignore
```

- [ ] **Step 2: Append poller-specific ignores**

```
# Poller (Python venv + caches)
poller/.venv/
poller/.pytest_cache/
poller/.mypy_cache/
poller/.ruff_cache/
poller/**/__pycache__/
poller/*.egg-info/
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore poller venv and python caches"
```

---

## Phase B — Schemas (10 tasks)

The schemas are the contract between the poller and the two managed agents. Per spec §§ 3.4, 3.5, 4.4, 4.5, 4.6. Define them as Pydantic v2 models so kickoff construction and envelope parsing both validate at runtime.

### Task B.1: Test ResolverKickoff schema accepts a valid payload

**Files:**
- Create: `poller/poller/schemas.py` (initial)
- Create: `poller/tests/test_schemas.py`

- [ ] **Step 1: Write `tests/test_schemas.py` with the first failing test**

```python
"""Schema tests — validates the contract surfaces between poller and managed agents."""

from datetime import datetime, UTC

import pytest

from poller.schemas import ResolverKickoff


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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/diego/Dev/managed_agents/poller
pytest tests/test_schemas.py::test_resolver_kickoff_accepts_valid_payload -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'poller.schemas'` or `ImportError: cannot import name 'ResolverKickoff'`.

- [ ] **Step 3: Implement `ResolverKickoff` in `poller/schemas.py`**

```python
"""Pydantic schemas for the v3 poller. Contract per spec §§ 3.4, 3.5, 4.4, 4.5, 4.6."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


Sha256 = Annotated[str, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]


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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_schemas.py::test_resolver_kickoff_accepts_valid_payload -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/diego/Dev/managed_agents
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): add ResolverKickoff schema with inline pydantic models"
```

### Task B.2: Test ResolverKickoff rejects invalid contract_id format

- [ ] **Step 1: Add a failing test to `tests/test_schemas.py`**

```python
def test_resolver_kickoff_rejects_invalid_contract_id() -> None:
    from pydantic import ValidationError

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
```

- [ ] **Step 2: Run the test (should already pass — Pydantic enforces the pattern from B.1)**

```bash
pytest tests/test_schemas.py::test_resolver_kickoff_rejects_invalid_contract_id -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add poller/tests/test_schemas.py
git commit -m "test(poller): assert ResolverKickoff rejects malformed contract_id"
```

### Task B.3: Test + implement ResolverEnvelope schema

- [ ] **Step 1: Add a failing test to `tests/test_schemas.py`**

```python
from poller.schemas import ResolverEnvelope


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
            "candidates": [{"contract_id": "INS-2026-007", "score": 0.4, "reason": "domain hint"}],
            "inferred_new_contract": {"client_name_guess": "XYZ", "sender_domain": "advisor.com"},
        },
        "new_contract_proposal": None,
    }

    result = ResolverEnvelope.model_validate(payload)

    assert result.decision == "triage"
    assert result.triage_payload is not None
    assert result.triage_payload.candidates[0].contract_id == "INS-2026-007"
```

- [ ] **Step 2: Run tests, verify they fail with `ImportError: cannot import name 'ResolverEnvelope'`**

```bash
pytest tests/test_schemas.py::test_resolver_envelope_accepts_continuation -v
```

- [ ] **Step 3: Implement `ResolverEnvelope` in `poller/schemas.py`**

Append to the existing schemas.py:

```python
from typing import Literal


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
```

- [ ] **Step 4: Run tests, verify both pass**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): add ResolverEnvelope schema with triage + new_contract payloads"
```

### Task B.4: Test + implement IngestionKickoff schema

- [ ] **Step 1: Add a failing test**

```python
from poller.schemas import IngestionKickoff


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
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_schemas.py::test_ingestion_kickoff_accepts_valid_payload -v
```

- [ ] **Step 3: Implement in `schemas.py`**

```python
class EmailContextExcerpt(BaseModel):
    """Email metadata passed into ingestion (excerpt only — body trimmed to ~500 chars)."""

    model_config = ConfigDict(populate_by_name=True)

    from_: EmailStr = Field(alias="from")
    to: list[EmailStr]
    cc: list[EmailStr] = Field(default_factory=list)
    subject: str
    conversationId: str
    messageId: str
    body_text_excerpt: str = Field(max_length=600)  # spec says ~500, allow margin
    received_at: datetime
    language: Literal["es", "en", "pt"]


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
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_schemas.py::test_ingestion_kickoff_accepts_valid_payload -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): add IngestionKickoff schema"
```

### Task B.5: Test + implement IngestionEnvelope schema

- [ ] **Step 1: Failing test**

```python
from poller.schemas import IngestionEnvelope


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
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_schemas.py::test_ingestion_envelope_ok tests/test_schemas.py::test_ingestion_envelope_blocked -v
```

- [ ] **Step 3: Implement in `schemas.py`**

```python
class IngestionEnvelope(BaseModel):
    """Ingestion agent's terse output envelope. Unchanged from v2 per spec § 4.6."""

    status: Literal["ok", "blocked", "failed"]
    normalized_dir: str
    manifest_path: str
    missing_fields: list[str]
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): add IngestionEnvelope schema (unchanged from v2)"
```

### Task B.6: Test + implement ManifestV3 schema (the v3 additions)

- [ ] **Step 1: Failing test**

```python
from poller.schemas import ManifestV3, ClientEmailDraft


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
            "body": "Hola Ana, gracias por enviar la información…",
            "missing_fields_referenced": ["cashflow_2024"],
            "tone_examples_consulted": ["tone_examples/2026-q1-followup.md"],
        },
        "triage_request": None,
    }

    result = ManifestV3.model_validate(payload)

    assert result.client_email_draft is not None
    assert result.client_email_draft.language == "es"
    assert "cashflow_2024" in result.client_email_draft.missing_fields_referenced
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_schemas.py::test_manifest_v3_with_client_email_draft -v
```

- [ ] **Step 3: Implement in `schemas.py`**

```python
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
    """The v3 manifest per spec § 4.5. Carries v2 fields verbatim plus client_email_draft + triage_request."""

    model_config = ConfigDict(extra="allow")  # tolerate forward-compat fields

    contract_id: str = Field(pattern=r"^INS-\d{4}-\d{3}$")
    entity: dict
    periods: list[str]
    pdf_extraction: PdfExtraction
    csv_extraction: CsvExtraction
    files_classified: list[dict]
    normalized_paths: dict
    quality_flags: list[dict]
    reconciliations: Reconciliations
    missing_fields: list[str]
    outputs: list[dict]
    client_email_draft: ClientEmailDraft | None = None
    triage_request: dict | None = None  # ingestion never populates; resolver may
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): add ManifestV3 schema with client_email_draft addition"
```

### Task B.7: Test + assert subset rule for client_email_draft.missing_fields_referenced

Per spec § 7.3, the scorer's `is_subset_of` rule. The schema doesn't enforce this (cross-field), but the poller's manifest validator must.

- [ ] **Step 1: Add a model-level validator**

In `schemas.py`, modify `ManifestV3` to add a `model_validator`:

```python
from pydantic import model_validator


class ManifestV3(BaseModel):
    # ... existing fields ...

    @model_validator(mode="after")
    def _email_draft_missing_fields_must_be_subset(self) -> "ManifestV3":
        if self.client_email_draft is None:
            return self
        referenced = set(self.client_email_draft.missing_fields_referenced)
        present = set(self.missing_fields)
        extra = referenced - present
        if extra:
            raise ValueError(
                f"client_email_draft.missing_fields_referenced contains items "
                f"not in manifest.missing_fields: {sorted(extra)}"
            )
        return self
```

- [ ] **Step 2: Add a failing test**

```python
def test_manifest_v3_rejects_inconsistent_email_draft() -> None:
    from pydantic import ValidationError

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
```

- [ ] **Step 3: Run, verify pass (validator was added in step 1)**

```bash
pytest tests/test_schemas.py::test_manifest_v3_rejects_inconsistent_email_draft -v
```

- [ ] **Step 4: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): enforce missing_fields_referenced ⊆ missing_fields"
```

### Task B.8: Test + add `from_kickoff_email` helper for IngestionKickoff construction

The poller's IngestionStep must build an IngestionKickoff from an EmailMeta + a resolved contract_id. Centralize the trim-to-500-char rule.

- [ ] **Step 1: Failing test**

```python
def test_email_context_excerpt_trims_long_body() -> None:
    from poller.schemas import EmailContextExcerpt, EmailMeta

    long_body = "a" * 1500
    email = EmailMeta.model_validate({
        "from": "ana@tafi.com.ar",
        "to": ["contracts@insignia.com"],
        "cc": [],
        "subject": "S",
        "conversationId": "c",
        "messageId": "m",
        "body_text": long_body,
        "received_at": "2026-05-01T14:22:11Z",
    })

    excerpt = EmailContextExcerpt.from_email_meta(email, language="es")

    assert len(excerpt.body_text_excerpt) <= 500
    assert excerpt.body_text_excerpt == long_body[:500]
    assert excerpt.from_ == email.from_
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_schemas.py::test_email_context_excerpt_trims_long_body -v
```

- [ ] **Step 3: Add the helper**

```python
class EmailContextExcerpt(BaseModel):
    # ... existing definition ...

    @classmethod
    def from_email_meta(cls, meta: "EmailMeta", language: Literal["es", "en", "pt"]) -> "EmailContextExcerpt":
        return cls.model_validate({
            "from": meta.from_,
            "to": meta.to,
            "cc": meta.cc,
            "subject": meta.subject,
            "conversationId": meta.conversationId,
            "messageId": meta.messageId,
            "body_text_excerpt": meta.body_text[:500],
            "received_at": meta.received_at,
            "language": language,
        })
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/schemas.py poller/tests/test_schemas.py
git commit -m "feat(poller): EmailContextExcerpt.from_email_meta helper trims body to 500"
```

### Task B.9: Lint + type-check everything in schemas

- [ ] **Step 1: Run ruff and mypy**

```bash
cd /Users/diego/Dev/managed_agents/poller
ruff check poller/schemas.py tests/test_schemas.py
mypy poller/schemas.py
```

Expected: no errors.

- [ ] **Step 2: Fix any issues, commit**

```bash
git add poller/poller/schemas.py
git commit -m "chore(poller): clean up schemas.py per ruff + mypy"
```

(Skip if step 1 was clean.)

### Task B.10: Add exceptions module

**Files:**
- Create: `poller/poller/exceptions.py`
- Create: `poller/tests/test_exceptions.py`

- [ ] **Step 1: Failing test**

```python
"""exceptions hierarchy tests."""

from poller.exceptions import (
    PollerError,
    GraphError,
    AnthropicError,
    MemoryStoreError,
    SchemaValidationError,
)


def test_exception_hierarchy() -> None:
    assert issubclass(GraphError, PollerError)
    assert issubclass(AnthropicError, PollerError)
    assert issubclass(MemoryStoreError, PollerError)
    assert issubclass(SchemaValidationError, PollerError)


def test_graph_error_carries_status_code() -> None:
    err = GraphError(message="rate limited", status_code=429, retry_after_seconds=30)

    assert err.status_code == 429
    assert err.retry_after_seconds == 30
    assert "rate limited" in str(err)
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_exceptions.py -v
```

- [ ] **Step 3: Implement `poller/exceptions.py`**

```python
"""Exception hierarchy for the poller. PollerError is the base; everything wraps it."""

from __future__ import annotations


class PollerError(Exception):
    """Base for all poller-side errors."""


class GraphError(PollerError):
    """Microsoft Graph SDK or API failure."""

    def __init__(self, message: str, *, status_code: int | None = None, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class AnthropicError(PollerError):
    """Anthropic SDK or session API failure."""


class MemoryStoreError(PollerError):
    """Memory store read/write failure."""


class SchemaValidationError(PollerError):
    """Manifest or envelope failed schema validation."""
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_exceptions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/exceptions.py poller/tests/test_exceptions.py
git commit -m "feat(poller): add exception hierarchy"
```

---

## Phase C — GraphAdapter (10 tasks)

The GraphAdapter wraps Microsoft Graph SDK calls. Phase 1 implements ONLY `list_new_messages_via_delta()` — the other methods (download_attachment, upload_to_onedrive, post_channel_message, send_mail) ship in Phase 2 because they require live tenant config to integration-test. But we define the protocol shape now so the rest of the poller can depend on the interface.

### Task C.1: Test for the GraphAdapter protocol shape

**Files:**
- Create: `poller/tests/adapters/test_graph.py`

- [ ] **Step 1: Failing test**

```python
"""GraphAdapter protocol tests."""

from typing import Protocol

import pytest

from poller.adapters.graph import GraphAdapterProtocol


def test_graph_adapter_protocol_is_a_protocol() -> None:
    assert issubclass(GraphAdapterProtocol, Protocol)


def test_graph_adapter_protocol_declares_list_new_messages_via_delta() -> None:
    assert hasattr(GraphAdapterProtocol, "list_new_messages_via_delta")
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/adapters/test_graph.py -v
```

- [ ] **Step 3: Create `poller/poller/adapters/graph.py` with the protocol**

```python
"""GraphAdapter — wraps Microsoft Graph SDK calls for the poller.

Phase 1 implements list_new_messages_via_delta only. Other methods (download_attachment,
upload_to_onedrive, post_channel_message, send_mail) are declared in the protocol but
implemented in Phase 2 alongside live tenant integration tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from poller.schemas import EmailMeta


@runtime_checkable
class GraphAdapterProtocol(Protocol):
    """Microsoft Graph adapter contract. Phase 1 implements list_new_messages_via_delta only."""

    async def list_new_messages_via_delta(self, *, delta_link: str | None) -> tuple[list[EmailMeta], str]:
        """Fetch new mail since the last delta_link. Returns (messages, next_delta_link).

        On first run (delta_link is None), starts a fresh delta sequence and consumes
        the entire current state, returning [] and the new delta_link to persist.
        """
        ...
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/adapters/test_graph.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/adapters/graph.py poller/tests/adapters/test_graph.py
git commit -m "feat(poller): declare GraphAdapterProtocol with list_new_messages_via_delta"
```

### Task C.2: Test for GraphAdapter implementation against a fake SDK

- [ ] **Step 1: Add a failing test**

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from poller.adapters.graph import GraphAdapter


def _make_fake_graph_message(message_id: str, subject: str = "Test", from_addr: str = "x@y.com") -> MagicMock:
    msg = MagicMock()
    msg.id = message_id
    msg.subject = subject
    msg.from_ = MagicMock()
    msg.from_.email_address.address = from_addr
    msg.to_recipients = [MagicMock(email_address=MagicMock(address="contracts@insignia.com"))]
    msg.cc_recipients = []
    msg.conversation_id = "conv-1"
    msg.body = MagicMock(content="Test body")
    msg.received_date_time = datetime(2026, 5, 1, 14, 22, 11, tzinfo=UTC)
    return msg


async def test_list_new_messages_via_delta_fresh_start() -> None:
    """First call (delta_link is None) starts a fresh delta sequence."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.value = [_make_fake_graph_message("msg-1")]
    fake_response.odata_delta_link = "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages/delta?$deltaToken=abc"
    fake_response.odata_next_link = None

    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.get = AsyncMock(
        return_value=fake_response
    )

    adapter = GraphAdapter(client=fake_client)

    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=None)

    assert len(messages) == 1
    assert messages[0].messageId == "msg-1"
    assert next_delta == fake_response.odata_delta_link


async def test_list_new_messages_via_delta_resume() -> None:
    """Subsequent call uses the prior delta_link."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.value = []
    fake_response.odata_delta_link = "https://graph.microsoft.com/v1.0/...?$deltaToken=def"
    fake_response.odata_next_link = None

    # Resume path uses the with_url builder when delta_link is provided.
    fake_request_builder = MagicMock()
    fake_request_builder.get = AsyncMock(return_value=fake_response)
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.return_value = (
        fake_request_builder
    )

    adapter = GraphAdapter(client=fake_client)

    prior_delta = "https://graph.microsoft.com/v1.0/...?$deltaToken=abc"
    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=prior_delta)

    assert messages == []
    assert next_delta == fake_response.odata_delta_link
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.assert_called_once_with(
        prior_delta
    )
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/adapters/test_graph.py -v
```

- [ ] **Step 3: Implement `GraphAdapter` in `graph.py`**

```python
from msgraph.graph_service_client import GraphServiceClient

from poller.exceptions import GraphError
from poller.schemas import EmailMeta


class GraphAdapter:
    """Concrete GraphAdapterProtocol implementation backed by msgraph-sdk-python.

    Phase 1: list_new_messages_via_delta only. Phase 2 adds download_attachment,
    upload_to_onedrive (via createUploadSession per spec § 2.5), post_channel_message,
    send_mail.
    """

    def __init__(self, client: GraphServiceClient) -> None:
        self._client = client

    async def list_new_messages_via_delta(
        self, *, delta_link: str | None
    ) -> tuple[list[EmailMeta], str]:
        try:
            delta_endpoint = (
                self._client.me.mail_folders.by_mail_folder_id("Inbox").messages.delta
            )

            if delta_link is None:
                response = await delta_endpoint.get()
            else:
                response = await delta_endpoint.with_url(delta_link).get()

            messages = [self._convert(m) for m in (response.value or [])]
            next_link = response.odata_delta_link

            if next_link is None:
                raise GraphError("Graph delta response missing odata_delta_link")

            return messages, next_link

        except GraphError:
            raise
        except Exception as exc:  # pragma: no cover — wrap for the caller
            raise GraphError(f"Graph delta query failed: {exc}") from exc

    @staticmethod
    def _convert(graph_message: object) -> EmailMeta:
        """Convert an msgraph Message object to EmailMeta."""
        return EmailMeta.model_validate({
            "from": graph_message.from_.email_address.address,
            "to": [r.email_address.address for r in (graph_message.to_recipients or [])],
            "cc": [r.email_address.address for r in (graph_message.cc_recipients or [])],
            "subject": graph_message.subject or "",
            "conversationId": graph_message.conversation_id,
            "messageId": graph_message.id,
            "body_text": (graph_message.body.content if graph_message.body else "") or "",
            "received_at": graph_message.received_date_time,
        })
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/adapters/test_graph.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/adapters/graph.py poller/tests/adapters/test_graph.py
git commit -m "feat(poller): GraphAdapter.list_new_messages_via_delta (delta query, fresh + resume paths)"
```

### Task C.3: Test GraphAdapter raises on missing delta_link in response

- [ ] **Step 1: Failing test**

```python
async def test_list_new_messages_via_delta_raises_on_missing_delta_link() -> None:
    from poller.exceptions import GraphError

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.value = []
    fake_response.odata_delta_link = None  # malformed
    fake_response.odata_next_link = None

    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.get = AsyncMock(
        return_value=fake_response
    )

    adapter = GraphAdapter(client=fake_client)

    with pytest.raises(GraphError, match="missing odata_delta_link"):
        await adapter.list_new_messages_via_delta(delta_link=None)
```

- [ ] **Step 2: Run, verify pass (the implementation already raises this)**

```bash
pytest tests/adapters/test_graph.py::test_list_new_messages_via_delta_raises_on_missing_delta_link -v
```

- [ ] **Step 3: Commit**

```bash
git add poller/tests/adapters/test_graph.py
git commit -m "test(poller): assert GraphAdapter raises on malformed delta response"
```

### Task C.4: Test GraphAdapter handles paginated delta (odata_next_link)

In delta queries, when there are more results than fit in one response, Graph returns `odata_next_link` instead of `odata_delta_link`. The adapter must follow these links until a `delta_link` arrives.

- [ ] **Step 1: Failing test**

```python
async def test_list_new_messages_via_delta_paginates() -> None:
    """Adapter follows odata_next_link until odata_delta_link is returned."""
    fake_client = MagicMock()

    # First page: 1 message, next_link present, delta_link absent.
    page1 = MagicMock()
    page1.value = [_make_fake_graph_message("msg-1")]
    page1.odata_next_link = "https://graph.microsoft.com/v1.0/...?$skiptoken=p2"
    page1.odata_delta_link = None

    # Second page: 1 message, next_link absent, delta_link present.
    page2 = MagicMock()
    page2.value = [_make_fake_graph_message("msg-2")]
    page2.odata_next_link = None
    page2.odata_delta_link = "https://graph.microsoft.com/v1.0/...?$deltaToken=final"

    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.get = AsyncMock(
        return_value=page1
    )
    fake_next_builder = MagicMock()
    fake_next_builder.get = AsyncMock(return_value=page2)
    fake_client.me.mail_folders.by_mail_folder_id.return_value.messages.delta.with_url.return_value = (
        fake_next_builder
    )

    adapter = GraphAdapter(client=fake_client)
    messages, next_delta = await adapter.list_new_messages_via_delta(delta_link=None)

    assert [m.messageId for m in messages] == ["msg-1", "msg-2"]
    assert next_delta == "https://graph.microsoft.com/v1.0/...?$deltaToken=final"
```

- [ ] **Step 2: Run, verify failure** (current implementation doesn't paginate)

```bash
pytest tests/adapters/test_graph.py::test_list_new_messages_via_delta_paginates -v
```

- [ ] **Step 3: Update `GraphAdapter.list_new_messages_via_delta` to follow `odata_next_link`**

Replace the body of `list_new_messages_via_delta` with:

```python
async def list_new_messages_via_delta(
    self, *, delta_link: str | None
) -> tuple[list[EmailMeta], str]:
    try:
        delta_endpoint = (
            self._client.me.mail_folders.by_mail_folder_id("Inbox").messages.delta
        )

        if delta_link is None:
            response = await delta_endpoint.get()
        else:
            response = await delta_endpoint.with_url(delta_link).get()

        messages: list[EmailMeta] = [self._convert(m) for m in (response.value or [])]

        # Follow odata_next_link until a delta_link arrives.
        while response.odata_delta_link is None:
            if response.odata_next_link is None:
                raise GraphError(
                    "Graph delta response missing both odata_delta_link and odata_next_link"
                )
            response = await delta_endpoint.with_url(response.odata_next_link).get()
            messages.extend(self._convert(m) for m in (response.value or []))

        return messages, response.odata_delta_link

    except GraphError:
        raise
    except Exception as exc:  # pragma: no cover
        raise GraphError(f"Graph delta query failed: {exc}") from exc
```

- [ ] **Step 4: Run all GraphAdapter tests**

```bash
pytest tests/adapters/test_graph.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add poller/poller/adapters/graph.py poller/tests/adapters/test_graph.py
git commit -m "feat(poller): GraphAdapter follows odata_next_link pagination in delta queries"
```

### Task C.5: Test for GraphAdapter authentication construction

- [ ] **Step 1: Add a builder method test**

```python
def test_graph_adapter_from_client_credentials() -> None:
    """The adapter exposes a builder that takes (tenant_id, client_id, client_secret)."""
    from poller.adapters.graph import GraphAdapter

    adapter = GraphAdapter.from_client_credentials(
        tenant_id="tenant-uuid",
        client_id="client-uuid",
        client_secret="secret",
    )

    assert isinstance(adapter, GraphAdapter)
    assert adapter._client is not None
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/adapters/test_graph.py::test_graph_adapter_from_client_credentials -v
```

- [ ] **Step 3: Implement the builder**

Add to `GraphAdapter`:

```python
@classmethod
def from_client_credentials(
    cls,
    *,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> "GraphAdapter":
    from azure.identity.aio import ClientSecretCredential
    from msgraph.graph_service_client import GraphServiceClient

    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    client = GraphServiceClient(credentials=credential, scopes=["https://graph.microsoft.com/.default"])
    return cls(client=client)
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/adapters/test_graph.py::test_graph_adapter_from_client_credentials -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/adapters/graph.py poller/tests/adapters/test_graph.py
git commit -m "feat(poller): GraphAdapter.from_client_credentials builder"
```

### Task C.6: Add `Settings` config dataclass

**Files:**
- Create: `poller/poller/config.py`
- Create: `poller/tests/test_config.py`

- [ ] **Step 1: Failing test**

```python
"""Settings tests — env var loading + validation."""

import os
from unittest.mock import patch

import pytest

from poller.config import Settings


def test_settings_loads_from_env() -> None:
    env = {
        "GRAPH_TENANT_ID": "tenant-uuid",
        "GRAPH_CLIENT_ID": "client-uuid",
        "GRAPH_CLIENT_SECRET": "secret",
        "WATCHED_INBOX": "contracts@insignia.com",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "INSIGNIA_RESOLVER_AGENT_ID": "agent_resolver_id",
        "INSIGNIA_INGESTION_V3_AGENT_ID": "agent_ingestion_id",
        "INSIGNIA_MEMORY_STORE_ID": "mem_id",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings.from_env()

    assert s.graph_tenant_id == "tenant-uuid"
    assert s.watched_inbox == "contracts@insignia.com"
    assert s.poll_interval_seconds == 300  # 5-min default per spec § 2.1


def test_settings_raises_on_missing_required() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="GRAPH_TENANT_ID"):
            Settings.from_env()
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 3: Implement `poller/config.py`**

```python
"""Poller configuration. Env-var-driven; no config files in v1."""

from __future__ import annotations

import os
from dataclasses import dataclass


_REQUIRED_KEYS = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_CLIENT_SECRET",
    "WATCHED_INBOX",
    "ANTHROPIC_API_KEY",
    "INSIGNIA_RESOLVER_AGENT_ID",
    "INSIGNIA_INGESTION_V3_AGENT_ID",
    "INSIGNIA_MEMORY_STORE_ID",
)


@dataclass(frozen=True)
class Settings:
    graph_tenant_id: str
    graph_client_id: str
    graph_client_secret: str
    watched_inbox: str
    anthropic_api_key: str
    insignia_resolver_agent_id: str
    insignia_ingestion_v3_agent_id: str
    insignia_memory_store_id: str
    poll_interval_seconds: int = 300  # spec § 2.1 default
    # Phase 1 only reads these; Phase 2 will use them in adapter calls.

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [k for k in _REQUIRED_KEYS if not os.environ.get(k)]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        return cls(
            graph_tenant_id=os.environ["GRAPH_TENANT_ID"],
            graph_client_id=os.environ["GRAPH_CLIENT_ID"],
            graph_client_secret=os.environ["GRAPH_CLIENT_SECRET"],
            watched_inbox=os.environ["WATCHED_INBOX"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            insignia_resolver_agent_id=os.environ["INSIGNIA_RESOLVER_AGENT_ID"],
            insignia_ingestion_v3_agent_id=os.environ["INSIGNIA_INGESTION_V3_AGENT_ID"],
            insignia_memory_store_id=os.environ["INSIGNIA_MEMORY_STORE_ID"],
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
        )
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/config.py poller/tests/test_config.py
git commit -m "feat(poller): Settings.from_env loads + validates required env vars"
```

### Task C.7: Add `extended-cache-ttl-2025-04-11` beta header constant

Per spec § 5.5, v1 commits to the 1h TTL opt-in. This constant lives next to the Anthropic SDK call site (which ships in Phase 2), but lives in `config.py` for Phase 1 so Phase 2 doesn't have to re-find the spec reference.

- [ ] **Step 1: Add a test**

```python
def test_settings_exposes_extended_cache_beta_header() -> None:
    from poller.config import Settings, EXTENDED_CACHE_TTL_BETA_HEADER

    assert EXTENDED_CACHE_TTL_BETA_HEADER == "extended-cache-ttl-2025-04-11"
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/test_config.py::test_settings_exposes_extended_cache_beta_header -v
```

- [ ] **Step 3: Add the constant to `config.py`**

```python
# Per spec § 5.5: v1 opts into the 1-hour cache_control TTL beta on all session API calls.
EXTENDED_CACHE_TTL_BETA_HEADER = "extended-cache-ttl-2025-04-11"
```

- [ ] **Step 4: Run, verify pass**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add poller/poller/config.py poller/tests/test_config.py
git commit -m "feat(poller): pin extended-cache-ttl-2025-04-11 beta header constant"
```

### Task C.8: Lint and type-check the entire poller package

- [ ] **Step 1: Run ruff and mypy on everything**

```bash
cd /Users/diego/Dev/managed_agents/poller
ruff check .
mypy poller
```

- [ ] **Step 2: Fix any issues. Common fixes:**

If mypy complains about `model_validate` returning Any, add explicit type annotations. If it complains about `MagicMock` in tests, those are in test files which mypy can ignore via `[[tool.mypy.overrides]]` for the `tests.*` module.

Append to `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

- [ ] **Step 3: Re-run, verify clean**

```bash
ruff check .
mypy poller
```

- [ ] **Step 4: Commit**

```bash
git add poller/pyproject.toml
git commit -m "chore(poller): relax mypy strict mode for tests/"
```

(Skip if step 1 was clean.)

### Task C.9: Add a `conftest.py` with shared fixtures

**Files:**
- Create: `poller/tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures for the poller test suite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_env() -> Iterator[dict[str, str]]:
    """Provides a complete required-env-vars dict and patches os.environ."""
    env = {
        "GRAPH_TENANT_ID": "test-tenant",
        "GRAPH_CLIENT_ID": "test-client",
        "GRAPH_CLIENT_SECRET": "test-secret",
        "WATCHED_INBOX": "contracts@insignia-test.com",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "INSIGNIA_RESOLVER_AGENT_ID": "agent_resolver_test",
        "INSIGNIA_INGESTION_V3_AGENT_ID": "agent_ingestion_test",
        "INSIGNIA_MEMORY_STORE_ID": "mem_test",
    }
    with patch.dict(os.environ, env, clear=True):
        yield env
```

- [ ] **Step 2: Refactor existing tests to use `fake_env` where they patch env**

Update `test_config.py::test_settings_loads_from_env` to use the fixture instead of inlining env. Diff:

```python
def test_settings_loads_from_env(fake_env: dict[str, str]) -> None:
    s = Settings.from_env()

    assert s.graph_tenant_id == "test-tenant"
    assert s.watched_inbox == "contracts@insignia-test.com"
    assert s.poll_interval_seconds == 300
```

- [ ] **Step 3: Run all tests, verify they pass**

```bash
pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add poller/tests/conftest.py poller/tests/test_config.py
git commit -m "test(poller): add fake_env fixture and refactor config tests"
```

### Task C.10: Run the full test suite + lint as the closing check

- [ ] **Step 1: Full suite**

```bash
cd /Users/diego/Dev/managed_agents/poller
pytest tests/ -v
ruff check .
mypy poller
```

Expected: all green.

- [ ] **Step 2: If green, commit any remaining workspace state**

```bash
cd /Users/diego/Dev/managed_agents
git status --short
```

If `git status --short` shows nothing, Phase 1 is shipped. If anything's outstanding, commit with a descriptive message.

- [ ] **Step 3: Tag the milestone**

```bash
git tag -a poller-phase-1 -m "Insignia v3 poller — Phase 1 foundation complete (schemas + GraphAdapter + config)"
```

(Push the tag separately if you want; this plan does not push to remote.)

---

## Self-review (was run on this plan during writing)

Cross-checked against `2026-05-01-ingestion-v3-email-poller-design.md`:

- **§ 2.1 MailFeed delta query** — covered by Task C.2 + C.4 (delta + pagination).
- **§ 2.5 createUploadSession constraint** — NOT covered; deferred to Phase 2 alongside `download_attachment` and `upload_to_onedrive`. Phase 1 declares the protocol shape but doesn't implement those methods.
- **§ 3.4 ResolverKickoff schema** — Task B.1.
- **§ 3.5 ResolverEnvelope schema** — Task B.3.
- **§ 4.4 IngestionKickoff schema** — Task B.4.
- **§ 4.5 ManifestV3 with `client_email_draft` and the subset rule** — Tasks B.6, B.7.
- **§ 4.6 IngestionEnvelope (unchanged from v2)** — Task B.5.
- **§ 5.5 extended-cache-ttl-2025-04-11 opt-in** — Task C.7 (header constant in config).
- **§ 8.2 Gate 0a (extended-cache TTL entitlement check)** — out of scope for Phase 1; the constant exists, but the live probe + fallback ships in Phase 2 alongside the Anthropic adapter.
- **§ 8.2 Gate 0b (`/mnt/memory/` mount-path verification)** — out of scope for Phase 1; the schemas hardcode the path, which is verified in Phase 2 via memory-expert grounding.

No placeholders, no "implement later" steps. Every code step has complete code. File paths are absolute or relative to the repo root.

---

## Follow-up plans (separate sessions)

In rough dependency order:

1. **`2026-05-?-ingestion-v3-poller-phase-2-intake.md`** — MailFeed component (uses GraphAdapter), EmailGate 5-stage filter, MemoryStoreClient (Anthropic backend), tests against fixtures. End state: poller binary fetches mail and emits spawn/reject decisions to a log. Ships the live extended-cache TTL probe (spec § 8.2 Gate 0a). ~25 tasks.

2. **`2026-05-?-ingestion-v3-poller-phase-3-dispatch.md`** — AnthropicSessionsAdapter, ResolverStep, IngestionStep, AttachmentStager (with createUploadSession per spec § 2.5), ManifestStep. End state: full happy path through both agents. ~30 tasks.

3. **`2026-05-?-ingestion-v3-poller-phase-4-teams-hitl.md`** — TeamsCardPoster (plain-text channel messages per § 2.3), HITL reply polling, scheduler, error/retry budgets. End state: deployable. ~20 tasks.

4. **`2026-05-?-m365-tenant-runbook.md`** — runbook (not a code plan). Azure AD app registration, inbox provisioning, Teams team + channel setup, secret upload to vault, smoke test of Graph SDK auth. ~15 manual steps.

5. **`2026-05-?-eval-slices-v3.md`** — `evals/ingestion/tafi_2025_v3/` and `evals/resolver/<4 cases>/` content authoring + runner/scorer changes (`is_subset_of`, `must_not_contain`, language detection). ~20 tasks.

6. **`2026-05-?-synthetic-contracts-b-c.md`** — Spanish financial PDFs and CSVs for the demo (spec § 10.2). Content authoring, not code. ~10 substantive tasks (~2 days each per the spec).

Lead-0 handles agent + memory-store + vault + environment provisioning autonomously via its own pipeline; no plan needed for that track.

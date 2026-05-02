"""IngestionStep — runs the ingestion v3 agent against an IngestionKickoff.

Captures the manifest.json from session output, parses it as ManifestV3 (which
enforces the missing_fields_referenced ⊆ missing_fields rule), and returns the
parsed envelope + manifest pair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from poller.adapters.anthropic_sessions import AnthropicSessionsAdapter, SessionResult
from poller.exceptions import AnthropicError, SchemaValidationError
from poller.schemas import IngestionEnvelope, IngestionKickoff, ManifestV3


@dataclass
class IngestionOutcome:
    """Ingestion invocation result."""

    envelope: IngestionEnvelope
    manifest: ManifestV3
    session_id: str
    stop_reason: str
    is_error: bool


class IngestionStep:
    """Runs one ingestion session per resolved contract."""

    def __init__(
        self,
        *,
        sessions: AnthropicSessionsAdapter,
        agent_id: str,
        environment_id: str | None = None,
    ) -> None:
        self._sessions = sessions
        self._agent_id = agent_id
        self._environment_id = environment_id

    async def run(self, kickoff: IngestionKickoff) -> IngestionOutcome:
        kickoff_text = kickoff.model_dump_json(by_alias=True)

        # Capture the manifest at its known path per spec § 4.5.
        manifest_path = (
            f"/mnt/session/out/{kickoff.contract_id}/manifest.json"
        )

        result = await self._sessions.run(
            agent_id=self._agent_id,
            environment_id=self._environment_id,
            kickoff_text=kickoff_text,
            cache_control_blocks=None,  # ingestion kickoffs are per-contract; cache rarely hits
            capture_files=[manifest_path],
        )

        if result.is_error:
            raise AnthropicError(
                f"ingestion session {result.session_id} reported errors mid-stream "
                f"(stop_reason={result.stop_reason!r})"
            )

        envelope = self._parse_envelope(result)
        manifest = self._parse_manifest(result, manifest_path)

        return IngestionOutcome(
            envelope=envelope,
            manifest=manifest,
            session_id=result.session_id,
            stop_reason=result.stop_reason,
            is_error=result.is_error,
        )

    @staticmethod
    def _parse_envelope(result: SessionResult) -> IngestionEnvelope:
        text = result.final_message_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError(
                f"ingestion session {result.session_id} returned non-JSON: {exc}"
            ) from exc

        try:
            return IngestionEnvelope.model_validate(payload)
        except Exception as exc:
            raise AnthropicError(
                f"ingestion session {result.session_id} envelope failed validation: {exc}"
            ) from exc

    @staticmethod
    def _parse_manifest(result: SessionResult, manifest_path: str) -> ManifestV3:
        if manifest_path not in result.captured_files:
            raise SchemaValidationError(
                f"ingestion session {result.session_id} did not produce {manifest_path}"
            )
        raw = result.captured_files[manifest_path]
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SchemaValidationError(
                f"manifest at {manifest_path} is not valid JSON: {exc}"
            ) from exc

        try:
            return ManifestV3.model_validate(payload)
        except Exception as exc:
            raise SchemaValidationError(
                f"manifest at {manifest_path} failed schema validation: {exc}"
            ) from exc

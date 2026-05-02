"""ResolverStep — runs the resolver agent against a ResolverKickoff.

Serializes the kickoff to JSON, marks the registry payload with cache_control,
runs the session via AnthropicSessionsAdapter, parses the envelope into a
ResolverEnvelope. On parse failure, returns a triage-flavored envelope so the
poller can still post a card and ask a human.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from poller.adapters.anthropic_sessions import AnthropicSessionsAdapter, SessionResult
from poller.exceptions import AnthropicError
from poller.schemas import ResolverEnvelope, ResolverKickoff


@dataclass
class ResolverOutcome:
    """Resolver invocation result, including the raw session metadata."""

    envelope: ResolverEnvelope
    session_id: str
    stop_reason: str
    is_error: bool


class ResolverStep:
    """Runs one resolver session per inbound email."""

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

    async def run(self, kickoff: ResolverKickoff) -> ResolverOutcome:
        """Send the kickoff, parse the envelope, return the outcome."""
        kickoff_text = self._build_kickoff_text(kickoff)
        cache_blocks = self._build_cache_control(kickoff)

        result = await self._sessions.run(
            agent_id=self._agent_id,
            environment_id=self._environment_id,
            kickoff_text=kickoff_text,
            cache_control_blocks=cache_blocks,
            capture_files=None,
        )

        envelope = self._parse_envelope(result)
        return ResolverOutcome(
            envelope=envelope,
            session_id=result.session_id,
            stop_reason=result.stop_reason,
            is_error=result.is_error,
        )

    @staticmethod
    def _build_kickoff_text(kickoff: ResolverKickoff) -> str:
        """Serialize the kickoff to a JSON string the agent reads in its first turn."""
        return kickoff.model_dump_json(by_alias=True)

    @staticmethod
    def _build_cache_control(kickoff: ResolverKickoff) -> list[dict[str, object]]:
        """Per spec § 5.5: mark the registry block as ephemeral / 1h TTL.

        Adapter normalizes the TTL to 1h if absent, so we ship a minimal block.
        """
        # Minimum cacheable prefix is ~1024 tokens; the registry is well above that
        # at any nontrivial contract count, but the adapter won't reject small ones.
        return [{"type": "ephemeral"}]

    @staticmethod
    def _parse_envelope(result: SessionResult) -> ResolverEnvelope:
        """Parse the agent's final message text as a ResolverEnvelope.

        On parse failure, raises AnthropicError. The poller catches this and
        synthesizes a triage decision per spec § 6.2.
        """
        text = result.final_message_text.strip()

        # Strip a single ```json ... ``` fence if present (defensive — the agent
        # is told not to emit fences, but we tolerate one round of wrapping).
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError(
                f"resolver session {result.session_id} returned non-JSON: {exc}"
            ) from exc

        try:
            return ResolverEnvelope.model_validate(payload)
        except Exception as exc:
            raise AnthropicError(
                f"resolver session {result.session_id} envelope failed validation: {exc}"
            ) from exc

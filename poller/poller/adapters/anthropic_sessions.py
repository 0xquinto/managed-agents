"""AnthropicSessionsAdapter — wraps the Managed Agents sessions API.

The poller creates one session per email per agent (resolver, then ingestion). Each
session runs to completion (stop_reason: end_turn), the final envelope is captured,
and any session-output files (e.g. manifest.json) are pulled before the session
terminates.

Implementation note: the Managed Agents API + SDK shape is partly gated by the
extended-cache-TTL beta entitlement (spec § 8.2 Gate 0a). This module ships a
typed protocol the rest of the poller depends on, plus a stub
`AnthropicSessionsBackend` whose methods raise NotImplementedError until the
backend wiring is filled in. Tests use FakeSessionsBackend (in tests/).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from poller.config import EXTENDED_CACHE_TTL_BETA_HEADER


@dataclass(frozen=True)
class SessionResult:
    """Outcome of running a single session to completion."""

    session_id: str
    stop_reason: str  # "end_turn" | other
    final_message_text: str  # the agent's last assistant message content
    captured_files: dict[str, bytes]  # {session-output path -> bytes}
    is_error: bool


@runtime_checkable
class AnthropicSessionsBackend(Protocol):
    """Backend protocol for running a single agent session end-to-end."""

    async def run_session(
        self,
        *,
        agent_id: str,
        environment_id: str | None,
        kickoff_text: str,
        cache_control_blocks: list[dict[str, Any]] | None = None,
        capture_files: list[str] | None = None,
        beta_headers: list[str] | None = None,
    ) -> SessionResult:
        """Create a session bound to agent_id, send kickoff, wait for end_turn,
        capture session-output files, return SessionResult.
        """
        ...


class AnthropicSessionsAdapter:
    """High-level wrapper that pins the spec § 5.5 cache-control opt-in."""

    def __init__(self, backend: AnthropicSessionsBackend) -> None:
        self._backend = backend

    async def run(
        self,
        *,
        agent_id: str,
        environment_id: str | None,
        kickoff_text: str,
        cache_control_blocks: list[dict[str, Any]] | None = None,
        capture_files: list[str] | None = None,
        extra_beta_headers: list[str] | None = None,
    ) -> SessionResult:
        """Run a session with the spec-mandated extended-cache-ttl beta opt-in.

        Per spec § 5.5 + § 8.2 Gate 0a, every session API call carries the
        `extended-cache-ttl-2025-04-11` beta header and emits cache_control
        blocks that include `"ttl": "1h"` for any cached prefix.
        """
        beta_headers = [EXTENDED_CACHE_TTL_BETA_HEADER]
        if extra_beta_headers:
            beta_headers.extend(extra_beta_headers)

        normalized_cache_control = (
            self._ensure_one_hour_ttl(cache_control_blocks) if cache_control_blocks else None
        )

        return await self._backend.run_session(
            agent_id=agent_id,
            environment_id=environment_id,
            kickoff_text=kickoff_text,
            cache_control_blocks=normalized_cache_control,
            capture_files=capture_files,
            beta_headers=beta_headers,
        )

    @staticmethod
    def _ensure_one_hour_ttl(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Pin every cache_control block to 1h TTL.

        Caller may pass minimal blocks like {"type": "ephemeral"}; we add
        "ttl": "1h" if missing. Existing TTL values are preserved (caller
        intent wins).
        """
        result: list[dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, Mapping):
                raise TypeError(f"cache_control block must be a dict, got {type(b).__name__}")
            new = dict(b)
            new.setdefault("ttl", "1h")
            result.append(new)
        return result


class StubAnthropicSessionsBackend:
    """Production backend stub — raises until the real SDK call is filled in.

    Gate 0a (spec § 8.2) blocks live wiring: confirm extended-cache-ttl beta
    entitlement on the API key, then wire `client.beta.agents.sessions.*` calls
    here. Until then, the poller can only run with a test/fake backend.
    """

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    async def run_session(
        self,
        *,
        agent_id: str,
        environment_id: str | None,
        kickoff_text: str,
        cache_control_blocks: list[dict[str, Any]] | None = None,
        capture_files: list[str] | None = None,
        beta_headers: list[str] | None = None,
    ) -> SessionResult:  # pragma: no cover — gated on Gate 0a
        raise NotImplementedError(
            "StubAnthropicSessionsBackend.run_session is gated on spec § 8.2 Gate 0a"
        )

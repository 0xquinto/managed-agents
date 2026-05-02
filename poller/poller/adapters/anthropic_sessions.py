"""AnthropicSessionsAdapter — wraps the Managed Agents sessions API.

The poller creates one session per email per agent (resolver, then ingestion). Each
session runs to completion (stop_reason: end_turn), the final envelope is captured,
and any session-output files (e.g. manifest.json) are pulled before the session
terminates.

Two backends ship in this module:

- `AnthropicSDKSessionsBackend` — production wiring against the live
  `anthropic` SDK's beta sessions API. Closes spec § 8.2 Gate 0a: pins the
  `extended-cache-ttl-2025-04-11` beta header by default and falls back to
  the GA 5-min TTL on a 400 unrecognized-beta error (warning once, sticky).
- `StubAnthropicSessionsBackend` — kept for explicit "no real calls" tests
  and as a sentinel that fails loudly if the live backend isn't wired in.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import anthropic

from poller.config import EXTENDED_CACHE_TTL_BETA_HEADER

if TYPE_CHECKING:
    from anthropic import Anthropic

logger = logging.getLogger(__name__)


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


_WRITE_TOOL_NAMES = frozenset({"write", "Write", "edit", "Edit"})
"""Built-in tool names whose `input.file_path` writes we want to capture."""


class AnthropicSDKSessionsBackend:
    """Live backend wiring the `anthropic` SDK's beta sessions API.

    One backend instance per process — it owns the SDK client. Each
    `run_session` call:

    1. Creates a session bound to `agent_id` / `environment_id`.
    2. Sends the kickoff as a `user.message` event.
    3. Streams session events; concatenates `agent.message` text blocks into
       `final_message_text`; captures `agent.tool_use` `write`/`edit` tool
       inputs whose `file_path` ∈ `capture_files` into `captured_files`.
    4. Stops on `session.status_idle` (carrying `stop_reason`) or
       `session.status_terminated`.

    **Entitlement fallback (spec § 8.2 Gate 0a).** If session creation fails
    with a 400 about an unrecognized beta header AND
    `extended-cache-ttl-2025-04-11` is in `beta_headers`, we drop that header,
    log a warning once, and retry. The fallback is sticky for the lifetime of
    the backend instance — no point re-paying the failed-call cost on every
    cycle. The 5-min GA cache TTL still applies; per § 8.7 the per-email cost
    roughly doubles vs. the 1h tier.

    The SDK client is synchronous; we wrap calls in `asyncio.to_thread` to
    match the async protocol the poller's components expect. This is fine for
    the v1 cron cadence — one session at a time, no concurrent sessions per
    process.
    """

    def __init__(
        self,
        *,
        client: Anthropic | None = None,
        api_key: str | None = None,
        default_environment_id: str | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        elif api_key is not None:
            self._client = anthropic.Anthropic(api_key=api_key)
        else:
            raise ValueError(
                "AnthropicSDKSessionsBackend requires either `client=` or `api_key=`"
            )
        self._default_environment_id = default_environment_id
        # Sticky: once we've seen a 400 about extended-cache-ttl, assume the
        # entitlement is not enabled and stop sending the header.
        self._extended_cache_ttl_disabled = False

    @property
    def extended_cache_ttl_disabled(self) -> bool:
        """True iff a prior call fell back due to missing entitlement."""
        return self._extended_cache_ttl_disabled

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
        return await asyncio.to_thread(
            self._run_sync,
            agent_id=agent_id,
            environment_id=environment_id,
            kickoff_text=kickoff_text,
            cache_control_blocks=cache_control_blocks,
            capture_files=capture_files,
            beta_headers=beta_headers,
        )

    def _run_sync(
        self,
        *,
        agent_id: str,
        environment_id: str | None,
        kickoff_text: str,
        cache_control_blocks: list[dict[str, Any]] | None,
        capture_files: list[str] | None,
        beta_headers: list[str] | None,
    ) -> SessionResult:
        # `cache_control_blocks` is accepted for protocol parity. The SDK's
        # text-block param doesn't expose `cache_control` on the kickoff event
        # itself; caching is keyed off the agent's stable system prompt prefix.
        # When the SDK adds typed support, plumb the blocks into the user.message
        # content here.
        del cache_control_blocks
        env_id = environment_id or self._default_environment_id
        if env_id is None:
            raise ValueError(
                "AnthropicSDKSessionsBackend.run_session requires an environment_id; "
                "pass one explicitly or set `default_environment_id` at construction."
            )

        betas = list(beta_headers or [])
        if self._extended_cache_ttl_disabled:
            betas = [b for b in betas if b != EXTENDED_CACHE_TTL_BETA_HEADER]

        capture_paths = set(capture_files or [])

        session = self._create_session_with_fallback(
            agent_id=agent_id, environment_id=env_id, betas=betas
        )
        # `betas` may have been mutated by the fallback path; refresh from state.
        if self._extended_cache_ttl_disabled:
            betas = [b for b in betas if b != EXTENDED_CACHE_TTL_BETA_HEADER]

        self._client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": kickoff_text}],
                }
            ],
            betas=betas,
        )

        return self._collect_outcome(
            session_id=session.id, betas=betas, capture_paths=capture_paths
        )

    def _create_session_with_fallback(
        self,
        *,
        agent_id: str,
        environment_id: str,
        betas: list[str],
    ) -> Any:
        try:
            return self._client.beta.sessions.create(
                agent=agent_id,
                environment_id=environment_id,
                betas=betas,
            )
        except anthropic.BadRequestError as exc:
            should_fallback = (
                EXTENDED_CACHE_TTL_BETA_HEADER in betas
                and "extended-cache-ttl" in str(exc).lower()
                and not self._extended_cache_ttl_disabled
            )
            if not should_fallback:
                raise
            logger.warning(
                "Anthropic API rejected `%s` beta — Gate 0a entitlement not "
                "enabled. Falling back to default 5-min cache TTL for this "
                "process. See spec § 8.2 + § 8.7 (per-email cost roughly "
                "doubles vs. 1h tier).",
                EXTENDED_CACHE_TTL_BETA_HEADER,
            )
            self._extended_cache_ttl_disabled = True
            betas[:] = [b for b in betas if b != EXTENDED_CACHE_TTL_BETA_HEADER]
            return self._client.beta.sessions.create(
                agent=agent_id,
                environment_id=environment_id,
                betas=betas,
            )

    def _collect_outcome(
        self,
        *,
        session_id: str,
        betas: list[str],
        capture_paths: set[str],
    ) -> SessionResult:
        message_parts: list[str] = []
        captured_files: dict[str, bytes] = {}
        stop_reason = "unknown"
        is_error = False

        with self._client.beta.sessions.events.stream(
            session_id, betas=betas
        ) as stream:
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "agent.message":
                    for block in getattr(event, "content", []) or []:
                        if getattr(block, "type", "") == "text":
                            message_parts.append(getattr(block, "text", ""))
                elif event_type == "agent.tool_use":
                    self._maybe_capture_file_write(
                        event=event,
                        capture_paths=capture_paths,
                        captured_files=captured_files,
                    )
                elif event_type == "session.status_idle":
                    stop_reason = self._extract_stop_reason(event)
                    break
                elif event_type == "session.status_terminated":
                    if stop_reason == "unknown":
                        stop_reason = "terminated"
                        is_error = True
                    break
                elif event_type == "session.error":
                    is_error = True

        return SessionResult(
            session_id=session_id,
            stop_reason=stop_reason,
            final_message_text="".join(message_parts),
            captured_files=captured_files,
            is_error=is_error,
        )

    @staticmethod
    def _maybe_capture_file_write(
        *,
        event: Any,
        capture_paths: set[str],
        captured_files: dict[str, bytes],
    ) -> None:
        if getattr(event, "name", "") not in _WRITE_TOOL_NAMES:
            return
        tool_input = getattr(event, "input", {}) or {}
        path = tool_input.get("file_path") or tool_input.get("path")
        if not path or path not in capture_paths:
            return
        content = tool_input.get("content", "")
        if isinstance(content, bytes):
            captured_files[path] = content
        else:
            captured_files[path] = str(content).encode("utf-8")

    @staticmethod
    def _extract_stop_reason(event: Any) -> str:
        sr = getattr(event, "stop_reason", None)
        if sr is None:
            return "unknown"
        return getattr(sr, "type", None) or "unknown"


class StubAnthropicSessionsBackend:
    """Sentinel backend — raises on every call.

    Used by tests that want to assert "no real session call was made" and as a
    fail-loud default if the production wiring forgets to swap in the live
    backend. Prefer `AnthropicSDKSessionsBackend` for any code path that
    should reach the platform.
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
    ) -> SessionResult:
        del agent_id, environment_id, kickoff_text
        del cache_control_blocks, capture_files, beta_headers
        raise NotImplementedError(
            "StubAnthropicSessionsBackend.run_session is a sentinel — wire in "
            "AnthropicSDKSessionsBackend for production calls."
        )

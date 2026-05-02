"""RetryBudget — exponential backoff for transient Graph failures (spec § 6.1).

Retries on:
  - GraphError with status_code in {500..599} (server-side transient)
  - GraphError with status_code == 429 (throttling — honor retry_after_seconds)
  - GraphError with no status_code  (treated as transient on first failure;
    upstream caller should mark non-transient errors clearly)

Hard-fails on:
  - GraphError 4xx (other than 429) — auth/permission/bad-request
  - Any non-GraphError exception
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from poller.exceptions import GraphError

T = TypeVar("T")


class RetryBudget:
    """Exponential backoff (1, 2, 4, 8, ..., max_delay), bounded by max_attempts.

    Spec § 6.1 calls for 1s, 2s, 4s, 8s, max 60s, with 5 retries.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 60.0,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be ≥ 1")
        self._max_attempts = max_attempts
        self._base = base_delay_seconds
        self._max = max_delay_seconds
        self._sleep = sleep or asyncio.sleep

    async def run(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Invoke factory(); retry on transient GraphError; raise after budget."""
        attempt = 0
        last_exc: GraphError | None = None
        while attempt < self._max_attempts:
            try:
                return await factory()
            except GraphError as exc:
                if not self._is_transient(exc):
                    raise
                last_exc = exc
                attempt += 1
                if attempt >= self._max_attempts:
                    break
                delay = self._delay(attempt, exc)
                await self._sleep(delay)
        assert last_exc is not None  # narrowing for mypy
        raise last_exc

    def _delay(self, attempt: int, exc: GraphError) -> float:
        # Honor 429 Retry-After when present.
        if exc.status_code == 429 and exc.retry_after_seconds is not None:
            return float(min(float(exc.retry_after_seconds), self._max))
        # 1, 2, 4, 8, ...
        backoff = self._base * (2 ** (attempt - 1))
        return float(min(backoff, self._max))

    @staticmethod
    def _is_transient(exc: GraphError) -> bool:
        code = exc.status_code
        if code is None:
            return True
        if code == 429:
            return True
        return 500 <= code < 600

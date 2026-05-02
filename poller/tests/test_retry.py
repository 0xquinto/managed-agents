"""RetryBudget tests — backoff schedule, transient-vs-fatal classification."""

from __future__ import annotations

import pytest

from poller.exceptions import GraphError, PollerError
from poller.retry import RetryBudget


class _FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.calls.append(delay)


async def test_succeeds_on_first_call() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep)

    async def factory() -> str:
        return "ok"

    assert await budget.run(factory) == "ok"
    assert sleep.calls == []


async def test_retries_on_transient_5xx() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep, max_attempts=4, base_delay_seconds=1.0)
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise GraphError("server error", status_code=503)
        return "ok-after-retries"

    result = await budget.run(factory)
    assert result == "ok-after-retries"
    # Two retries → two sleeps, exponential 1s, 2s.
    assert sleep.calls == [1.0, 2.0]


async def test_honors_retry_after_on_429() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep, max_attempts=3)
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise GraphError("throttled", status_code=429, retry_after_seconds=15)
        return "ok"

    assert await budget.run(factory) == "ok"
    assert sleep.calls == [15.0]


async def test_raises_after_max_attempts() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep, max_attempts=3, base_delay_seconds=1.0)

    async def factory() -> str:
        raise GraphError("server down", status_code=502)

    with pytest.raises(GraphError, match="server down"):
        await budget.run(factory)

    # 3 attempts → 2 backoff sleeps (after attempt 1 and after attempt 2).
    assert sleep.calls == [1.0, 2.0]


async def test_does_not_retry_4xx_other_than_429() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep)

    async def factory() -> str:
        raise GraphError("bad request", status_code=400)

    with pytest.raises(GraphError, match="bad request"):
        await budget.run(factory)
    assert sleep.calls == []


async def test_does_not_retry_non_graph_errors() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(sleep=sleep)

    async def factory() -> str:
        raise PollerError("memory store down")

    with pytest.raises(PollerError, match="memory store down"):
        await budget.run(factory)
    assert sleep.calls == []


async def test_backoff_capped_at_max_delay() -> None:
    sleep = _FakeSleep()
    budget = RetryBudget(
        sleep=sleep, max_attempts=6, base_delay_seconds=1.0, max_delay_seconds=8.0
    )

    async def factory() -> str:
        raise GraphError("flaky", status_code=503)

    with pytest.raises(GraphError):
        await budget.run(factory)

    # 6 attempts → 5 backoffs: 1, 2, 4, 8 (cap), 8 (cap)
    assert sleep.calls == [1.0, 2.0, 4.0, 8.0, 8.0]

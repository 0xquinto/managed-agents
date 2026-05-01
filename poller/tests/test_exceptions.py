"""Exception hierarchy tests."""

from poller.exceptions import (
    AnthropicError,
    GraphError,
    MemoryStoreError,
    PollerError,
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


def test_graph_error_optional_kwargs_default_none() -> None:
    err = GraphError(message="bare error")

    assert err.status_code is None
    assert err.retry_after_seconds is None

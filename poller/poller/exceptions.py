"""Exception hierarchy for the poller. PollerError is the base; everything wraps it."""

from __future__ import annotations


class PollerError(Exception):
    """Base for all poller-side errors."""


class GraphError(PollerError):
    """Microsoft Graph SDK or API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class AnthropicError(PollerError):
    """Anthropic SDK or session API failure."""


class MemoryStoreError(PollerError):
    """Memory store read/write failure."""


class SchemaValidationError(PollerError):
    """Manifest or envelope failed schema validation."""

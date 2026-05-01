"""Settings tests — env var loading + validation."""

import os
from unittest.mock import patch

import pytest

from poller.config import EXTENDED_CACHE_TTL_BETA_HEADER, Settings


def test_settings_loads_from_env(fake_env: dict[str, str]) -> None:
    s = Settings.from_env()

    assert s.graph_tenant_id == "test-tenant"
    assert s.watched_inbox == "contracts@insignia-test.com"
    assert s.poll_interval_seconds == 300  # 5-min default per spec § 2.1


def test_settings_raises_on_missing_required() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="GRAPH_TENANT_ID"):
        Settings.from_env()


def test_settings_exposes_extended_cache_beta_header() -> None:
    assert EXTENDED_CACHE_TTL_BETA_HEADER == "extended-cache-ttl-2025-04-11"


def test_settings_overrides_poll_interval(fake_env: dict[str, str]) -> None:
    fake_env["POLL_INTERVAL_SECONDS"] = "60"
    with patch.dict(os.environ, fake_env, clear=True):
        s = Settings.from_env()

    assert s.poll_interval_seconds == 60

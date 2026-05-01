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

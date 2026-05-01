"""Poller configuration. Env-var-driven; no config files in v1."""

from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED_KEYS = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_CLIENT_SECRET",
    "WATCHED_INBOX",
    "ANTHROPIC_API_KEY",
    "INSIGNIA_RESOLVER_AGENT_ID",
    "INSIGNIA_INGESTION_V3_AGENT_ID",
    "INSIGNIA_MEMORY_STORE_ID",
)


# Per spec § 5.5: v1 opts into the 1-hour cache_control TTL beta on all session API calls.
EXTENDED_CACHE_TTL_BETA_HEADER = "extended-cache-ttl-2025-04-11"


@dataclass(frozen=True)
class Settings:
    """Poller runtime configuration loaded from env vars.

    All required keys must be present; defaults are applied for poll_interval_seconds.
    """

    graph_tenant_id: str
    graph_client_id: str
    graph_client_secret: str
    watched_inbox: str
    anthropic_api_key: str
    insignia_resolver_agent_id: str
    insignia_ingestion_v3_agent_id: str
    insignia_memory_store_id: str
    poll_interval_seconds: int = 300  # spec § 2.1 default

    @classmethod
    def from_env(cls) -> Settings:
        missing = [k for k in _REQUIRED_KEYS if not os.environ.get(k)]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        return cls(
            graph_tenant_id=os.environ["GRAPH_TENANT_ID"],
            graph_client_id=os.environ["GRAPH_CLIENT_ID"],
            graph_client_secret=os.environ["GRAPH_CLIENT_SECRET"],
            watched_inbox=os.environ["WATCHED_INBOX"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            insignia_resolver_agent_id=os.environ["INSIGNIA_RESOLVER_AGENT_ID"],
            insignia_ingestion_v3_agent_id=os.environ["INSIGNIA_INGESTION_V3_AGENT_ID"],
            insignia_memory_store_id=os.environ["INSIGNIA_MEMORY_STORE_ID"],
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
        )

"""Scheduler entrypoint — `python -m poller.scheduler` runs one poll cycle.

Designed for cron / Azure Function timer trigger / GitHub Actions schedule.
Spec § 2.1: default N = 5 min cadence, set by the surrounding scheduler — the
process itself is idempotent and one-shot.

Wiring: builds adapters from environment via Settings.from_env (Phase 1), wires
together every component, runs Orchestrator.run_cycle, prints a one-line
CycleSummary to stdout, exits with code 0 on no errors / 1 if any.

This module is intentionally thin so tests can import-and-call run_one_cycle
without subprocess plumbing. The CLI entrypoint is the bottom of this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from poller.adapters.anthropic_sessions import (
    AnthropicSessionsAdapter,
    AnthropicSessionsBackend,
    StubAnthropicSessionsBackend,
)
from poller.adapters.graph import GraphAdapter, GraphAdapterProtocol
from poller.adapters.memory import (
    AnthropicMemoryBackend,
    LocalFilesystemBackend,
    MemoryBackendProtocol,
    MemoryStoreClient,
)
from poller.components.attachment_stager import AttachmentStager
from poller.components.email_gate import EmailGate
from poller.components.ingestion_step import IngestionStep
from poller.components.mail_feed import MailFeed
from poller.components.manifest_step import ManifestStep
from poller.components.reply_parser import ChannelReplyPoll
from poller.components.resolver_step import ResolverStep
from poller.components.teams_poster import ChannelRef, TeamsCardPoster
from poller.config import Settings
from poller.orchestrator import (
    ContractChannelResolver,
    CycleSummary,
    Orchestrator,
)

logger = logging.getLogger(__name__)


def _build_orchestrator(
    *,
    settings: Settings,
    graph: GraphAdapterProtocol | None = None,
    memory_backend: MemoryBackendProtocol | None = None,
    sessions_backend: AnthropicSessionsBackend | None = None,
    clock: Callable[[], float] | None = None,
    triage_channel: ChannelRef | None = None,
    default_team_id: str = "team-default",
) -> Orchestrator:
    """Assemble an Orchestrator from settings + (optionally) injected adapters.

    The default adapters are production-shaped (GraphAdapter via client-creds,
    AnthropicMemoryBackend, StubAnthropicSessionsBackend). Tests pass fakes via
    keyword args.
    """
    graph_adapter: GraphAdapterProtocol = graph or GraphAdapter.from_client_credentials(
        tenant_id=settings.graph_tenant_id,
        client_id=settings.graph_client_id,
        client_secret=settings.graph_client_secret,
    )

    memory_be: MemoryBackendProtocol
    if memory_backend is not None:
        memory_be = memory_backend
    else:
        memory_be = AnthropicMemoryBackend(
            store_id=settings.insignia_memory_store_id,
            api_key=settings.anthropic_api_key,
        )
    memory = MemoryStoreClient(backend=memory_be)

    sessions_be: AnthropicSessionsBackend = (
        sessions_backend or StubAnthropicSessionsBackend(api_key=settings.anthropic_api_key)
    )
    sessions = AnthropicSessionsAdapter(backend=sessions_be)

    triage = triage_channel or ChannelRef(
        team_id=default_team_id, channel_id="chan-triage"
    )

    return Orchestrator(
        graph=graph_adapter,
        mail_feed=MailFeed(graph=graph_adapter, memory=memory),
        email_gate=EmailGate(
            memory=memory,
            clock=clock or (lambda: datetime.now(tz=UTC).timestamp()),
        ),
        resolver_step=ResolverStep(
            sessions=sessions, agent_id=settings.insignia_resolver_agent_id
        ),
        attachment_stager=AttachmentStager(graph=graph_adapter, memory=memory),
        ingestion_step=IngestionStep(
            sessions=sessions, agent_id=settings.insignia_ingestion_v3_agent_id
        ),
        manifest_step=ManifestStep(),
        teams_poster=TeamsCardPoster(
            graph=graph_adapter, triage_channel=triage
        ),
        reply_poll=ChannelReplyPoll(graph=graph_adapter, memory=memory),
        memory=memory,
        contract_channel_resolver=ContractChannelResolver(
            memory=memory, default_team_id=default_team_id
        ),
    )


async def run_one_cycle(
    *,
    settings: Settings | None = None,
) -> CycleSummary:
    """Build an Orchestrator and run exactly one cycle. Returns the summary."""
    s = settings or Settings.from_env()
    orchestrator = _build_orchestrator(settings=s)
    return await orchestrator.run_cycle()


def _cli_main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    summary = asyncio.run(run_one_cycle())
    print(json.dumps(summary.__dict__, indent=2))
    return 0 if not summary.errors else 1


def _local_dev_orchestrator(
    *,
    memory_root: str,
    settings: Settings | None = None,
) -> Orchestrator:
    """Convenience for local dev: filesystem memory backend instead of API."""
    from pathlib import Path
    s = settings or Settings.from_env()
    return _build_orchestrator(
        settings=s,
        memory_backend=LocalFilesystemBackend(root=Path(memory_root)),
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_cli_main())

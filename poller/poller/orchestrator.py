"""Orchestrator — runs one poll cycle end-to-end.

Sequence per spec § 2.1:

  1. ChannelReplyPoll.collect()                  — close out prior cycles' HITL
  2. Apply each resolved decision               — APPROVE → sendMail; etc.
  3. MailFeed.fetch_new()                        — new inbound messages
  4. For each new email:
       a. EmailGate.evaluate()                   — 5-stage filter
       b. ResolverStep.run(kickoff)              — classify (new/cont/triage)
       c. (continuation/new) AttachmentStager.stage()
       d. (continuation/new) IngestionStep.run(kickoff)
       e. ManifestStep.classify(env, manifest)
       f. TeamsCardPoster.post_<kind>()          — post + add to pending_cards
       g. (triage)            TeamsCardPoster.post_triage()

Failures are logged into a CycleSummary; the orchestrator never raises out of a
single email — it logs and moves on. Hard halts are reserved for memory store
and Graph-token failures (spec § 6.5).

This is a v1 single-cycle orchestrator. Multi-cycle scheduling is in
`scheduler.py`. Per-email parallelism is deferred — a single-threaded sweep
keeps the audit trail trivially serializable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from poller.adapters.graph import GraphAdapterProtocol
from poller.adapters.memory import MemoryStoreClient
from poller.components.attachment_stager import AttachmentStager
from poller.components.email_gate import EmailGate, GateDecision
from poller.components.ingestion_step import IngestionStep
from poller.components.mail_feed import MailFeed
from poller.components.manifest_step import ManifestStep
from poller.components.reply_parser import ChannelReplyPoll
from poller.components.resolver_step import ResolverStep
from poller.components.teams_poster import (
    CardPostResult,
    ChannelRef,
    TeamsCardPoster,
)
from poller.exceptions import PollerError
from poller.schemas import (
    EmailContextExcerpt,
    EmailMeta,
    IngestionKickoff,
    MemoryPaths,
    ResolverEnvelope,
)

logger = logging.getLogger(__name__)


@dataclass
class CycleSummary:
    """Aggregated outcome of one poll cycle."""

    decisions_applied: int = 0
    emails_seen: int = 0
    emails_rejected_by_gate: int = 0
    emails_deferred_by_gate: int = 0
    triage_cards_posted: int = 0
    status_ok_cards_posted: int = 0
    draft_cards_posted: int = 0
    degraded_cards_posted: int = 0
    errors: list[str] = field(default_factory=list)


class Orchestrator:
    """Wires every Phase 1–4 component into a single poll-cycle invocation."""

    def __init__(
        self,
        *,
        graph: GraphAdapterProtocol,
        mail_feed: MailFeed,
        email_gate: EmailGate,
        resolver_step: ResolverStep,
        attachment_stager: AttachmentStager,
        ingestion_step: IngestionStep,
        manifest_step: ManifestStep,
        teams_poster: TeamsCardPoster,
        reply_poll: ChannelReplyPoll,
        memory: MemoryStoreClient,
        contract_channel_resolver: ContractChannelResolver,
    ) -> None:
        self._graph = graph
        self._mail = mail_feed
        self._gate = email_gate
        self._resolver = resolver_step
        self._stager = attachment_stager
        self._ingest = ingestion_step
        self._manifest = manifest_step
        self._poster = teams_poster
        self._reply_poll = reply_poll
        self._memory = memory
        self._channel_resolver = contract_channel_resolver

    async def run_cycle(self) -> CycleSummary:
        summary = CycleSummary()

        # 1. Resolve any pending HITL responses from prior cycles.
        try:
            replies = await self._reply_poll.collect()
            summary.decisions_applied = (
                len(replies.draft_decisions) + len(replies.triage_decisions)
            )
            # NB: actually applying each decision (sendMail on approve, registry
            # write on triage assign) is part of v1 follow-on work — this v1
            # cycle hands the resolved decisions to the caller. The stub below
            # logs them so they're visible in CycleSummary.
            for cb_id, draft_dec in replies.draft_decisions.items():
                logger.info(
                    "HITL draft decision callback=%s decision=%s",
                    cb_id, draft_dec.decision,
                )
            for cb_id, triage_dec in replies.triage_decisions.items():
                logger.info(
                    "HITL triage decision callback=%s decision=%s",
                    cb_id, triage_dec.decision,
                )
        except PollerError as exc:
            summary.errors.append(f"reply_poll: {exc}")

        # 2. Fetch new mail.
        try:
            new_emails = await self._mail.fetch_new()
        except PollerError as exc:
            summary.errors.append(f"mail_feed: {exc}")
            return summary

        summary.emails_seen = len(new_emails)

        # 3. Per-email pipeline.
        for email in new_emails:
            try:
                await self._process_email(email, summary)
            except Exception as exc:
                # Defensive — the per-email pipeline should never raise; if it
                # does, log and keep moving.
                logger.exception("unhandled error processing email %s", email.messageId)
                summary.errors.append(
                    f"email {email.messageId}: {type(exc).__name__}: {exc}"
                )

        return summary

    async def _process_email(self, email: EmailMeta, summary: CycleSummary) -> None:
        # Fetch attachment metadata + bytes for this message before EmailGate.
        # Per spec § 6.1: the poller is the attachment-fetch boundary. EmailGate
        # needs metadata for stages 1-2 (count, isInline, size, content_type)
        # and bytes for stage 3 (sha256 dedup). Item-attachment / reference
        # kinds come back with content_type="x-graph-itemattachment/..." and
        # are stripped by stage 2 alongside cosmetic images.
        try:
            raw_attachments = await self._graph.list_message_attachments(
                message_id=email.messageId
            )
        except PollerError as exc:
            summary.errors.append(
                f"email {email.messageId}: list_message_attachments failed: {exc}"
            )
            return
        decision: GateDecision = self._gate.evaluate(
            email=email, raw_attachments=raw_attachments
        )
        if decision.outcome == "reject":
            summary.emails_rejected_by_gate += 1
            return
        if decision.outcome == "defer":
            summary.emails_deferred_by_gate += 1
            return

        kickoff = decision.kickoff
        if kickoff is None:
            summary.errors.append(
                f"email {email.messageId}: gate spawn produced no kickoff"
            )
            return

        # 3a. Resolver
        resolver = await self._resolver.run(kickoff)
        envelope = resolver.envelope

        if envelope.decision == "triage":
            await self._post_triage(envelope, email, summary)
            return

        contract_id = envelope.contract_id
        if contract_id is None:
            summary.errors.append(
                f"email {email.messageId}: resolver decided "
                f"{envelope.decision} but returned no contract_id"
            )
            return

        # 3b. Stage attachments to OneDrive (and prep session resources).
        client_name = self._lookup_client_name(contract_id)
        onedrive_root = self._lookup_onedrive_root(contract_id, client_name)
        staged = await self._stager.stage(
            contract_id=contract_id,
            client_name=client_name,
            onedrive_root=onedrive_root,
            message_id=email.messageId,
            attachments=kickoff.attachments,
            received_at=email.received_at,
        )

        # 3c. Ingest
        ingest_kickoff = IngestionKickoff(
            contract_id=contract_id,
            client_name=client_name,
            input_files=staged.session_resource_paths,
            email_context=EmailContextExcerpt.from_email_meta(email, language="es"),
            memory_paths=MemoryPaths(
                priors=f"/mnt/memory/priors/{contract_id}.json",
                tone_examples_dir="/mnt/memory/tone_examples/",
            ),
        )
        ingestion = await self._ingest.run(ingest_kickoff)

        # 3d. Classify the manifest into a card kind.
        post = self._manifest.classify(
            envelope=ingestion.envelope, manifest=ingestion.manifest
        )

        # 3e. Post the appropriate card.
        channel = self._channel_resolver.resolve(contract_id)
        callback_id = f"{contract_id}:{email.messageId}"
        result: CardPostResult
        if post.kind == "status_ok":
            result = await self._poster.post_status_ok(
                post=post, channel=channel, callback_id=callback_id
            )
            summary.status_ok_cards_posted += 1
        elif post.kind == "client_email_draft":
            result = await self._poster.post_email_draft(
                post=post, channel=channel, callback_id=callback_id
            )
            summary.draft_cards_posted += 1
        elif post.kind == "degraded":
            result = await self._poster.post_degraded(
                post=post, channel=channel, callback_id=callback_id
            )
            summary.degraded_cards_posted += 1
        else:  # pragma: no cover — kind enum exhausted above
            summary.errors.append(f"unknown post kind: {post.kind}")
            return

        # 3f. Record the new card in pending_cards (only kinds with callbacks).
        if post.kind == "client_email_draft":
            self._append_pending_card(result)

    async def _post_triage(
        self, envelope: ResolverEnvelope, email: EmailMeta, summary: CycleSummary
    ) -> None:
        callback_id = f"triage:{email.messageId}"
        result = await self._poster.post_triage(
            envelope=envelope, email=email, callback_id=callback_id
        )
        summary.triage_cards_posted += 1
        self._append_pending_card(result)

    # -------------------------------------------------------- registry helpers

    def _lookup_client_name(self, contract_id: str) -> str:
        for row in self._memory.read_registry():
            if row.get("contract_id") == contract_id:
                return str(row.get("client_name", contract_id))
        return contract_id

    def _lookup_onedrive_root(self, contract_id: str, client_name: str) -> str:
        for row in self._memory.read_registry():
            if row.get("contract_id") == contract_id:
                path = row.get("onedrive_path")
                if isinstance(path, str) and path:
                    if not path.endswith("/"):
                        path = path + "/"
                    if not path.startswith("/"):
                        path = "/" + path
                    return path
        # Fallback derived from client_name
        safe = client_name.replace(" ", "_")
        return f"/Contracts/{safe}/"

    # --------------------------------------------------------- pending cards

    def _append_pending_card(self, card: CardPostResult) -> None:
        existing = []
        if self._memory.exists(ChannelReplyPoll.PENDING_KEY):
            raw = self._memory.read_json(ChannelReplyPoll.PENDING_KEY)
            if isinstance(raw, list):
                existing = list(raw)
        existing.append(card.to_dict())
        self._memory.write_json(ChannelReplyPoll.PENDING_KEY, existing)


class ContractChannelResolver:
    """Looks up the per-contract Teams channel from the registry.

    Intentionally a separate class so the orchestrator can be unit-tested with
    a stub resolver that doesn't need a populated memory store.
    """

    def __init__(self, *, memory: MemoryStoreClient, default_team_id: str) -> None:
        self._memory = memory
        self._default_team_id = default_team_id

    def resolve(self, contract_id: str) -> ChannelRef:
        for row in self._memory.read_registry():
            if row.get("contract_id") == contract_id:
                channel_id = row.get("teams_channel_id")
                if isinstance(channel_id, str) and channel_id:
                    return ChannelRef(
                        team_id=self._default_team_id,
                        channel_id=channel_id,
                    )
        # Fallback: send to a placeholder; orchestrator will surface an error
        # via the post call if Graph rejects it.
        return ChannelRef(
            team_id=self._default_team_id, channel_id=f"missing:{contract_id}"
        )

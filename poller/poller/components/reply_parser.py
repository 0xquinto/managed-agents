"""ReplyParser + ChannelReplyPoll — collects HITL decisions from Teams reply threads.

Two card kinds carry callback contracts (per spec § 2.3 + § 6.4):

  • client_email_draft → APPROVE | EDIT <body> | REJECT <reason>
  • triage             → <contract_id> | new <client_name> | drop <reason>

The poller persists a `pending_cards.json` array under the memory store. Each
poll cycle:

  1. Read pending_cards.
  2. For each, list_channel_replies on the parent message.
  3. Parse the *first* recognized command (case-insensitive, leading whitespace
     and Markdown noise stripped). Subsequent replies are ignored — humans get
     one shot, additional replies should land as new cards.
  4. Hand the resolved decisions back to the orchestrator. Resolved entries are
     removed from pending_cards.

Bot replies are ignored to avoid loops. Author display name + id pass through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from poller.adapters.graph import ChannelReply, GraphAdapterProtocol
from poller.adapters.memory import MemoryStoreClient
from poller.components.teams_poster import CardPostResult

DraftDecision = Literal["approve", "edit", "reject"]
TriageDecision = Literal["assign", "new_contract", "drop"]


@dataclass(frozen=True)
class DraftReply:
    """Parsed reply to a client_email_draft card."""

    decision: DraftDecision
    edit_body: str | None
    reject_reason: str | None
    author_id: str
    author_name: str
    received_at: datetime


@dataclass(frozen=True)
class TriageReply:
    """Parsed reply to a triage card."""

    decision: TriageDecision
    contract_id: str | None
    new_client_name: str | None
    drop_reason: str | None
    author_id: str
    author_name: str
    received_at: datetime


# A relaxed leading-token regex: optional bullets, leading whitespace.
_PREFIX = r"^\s*[-*•]?\s*"


def parse_draft_reply(reply: ChannelReply) -> DraftReply | None:
    """Extract a DraftReply from the reply body text, or None if no command."""
    text = _strip_html(reply.body_text).strip()
    if not text:
        return None

    # APPROVE — anything trailing is informational and ignored.
    m = re.match(_PREFIX + r"approve\b", text, flags=re.IGNORECASE)
    if m:
        return DraftReply(
            decision="approve",
            edit_body=None,
            reject_reason=None,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    m = re.match(_PREFIX + r"edit\b\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        new_body = m.group(1).strip()
        if not new_body:
            return None  # bare EDIT without body — ignore, wait for clarification
        return DraftReply(
            decision="edit",
            edit_body=new_body,
            reject_reason=None,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    m = re.match(_PREFIX + r"reject\b\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        reason = m.group(1).strip() or "no reason provided"
        return DraftReply(
            decision="reject",
            edit_body=None,
            reject_reason=reason,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    return None


_CONTRACT_RE = re.compile(r"^INS-\d{4}-\d{3}$")


def parse_triage_reply(reply: ChannelReply) -> TriageReply | None:
    """Extract a TriageReply from the reply body text, or None if no command."""
    text = _strip_html(reply.body_text).strip()
    if not text:
        return None

    # `new <client_name>`
    m = re.match(_PREFIX + r"new\b\s+(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return TriageReply(
            decision="new_contract",
            contract_id=None,
            new_client_name=m.group(1).strip(),
            drop_reason=None,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    # `drop <reason>`
    m = re.match(_PREFIX + r"drop\b\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        reason = m.group(1).strip() or "no reason provided"
        return TriageReply(
            decision="drop",
            contract_id=None,
            new_client_name=None,
            drop_reason=reason,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    # Bare INS-YYYY-NNN
    first_token = text.split()[0]
    if _CONTRACT_RE.match(first_token):
        return TriageReply(
            decision="assign",
            contract_id=first_token,
            new_client_name=None,
            drop_reason=None,
            author_id=reply.author_id,
            author_name=reply.author_name,
            received_at=reply.created_at,
        )

    return None


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    """Crude tag-strip — Teams channel messages render as HTML even for plaintext.

    We don't try to be exhaustive; the parser only needs the first leading token
    to be readable. <p>APPROVE</p> / <div>REJECT bad tone</div> both work.
    """
    return _HTML_TAG_RE.sub(" ", s)


@dataclass
class CollectedReplies:
    """Result of one poll cycle's reply collection."""

    draft_decisions: dict[str, DraftReply]
    triage_decisions: dict[str, TriageReply]
    still_pending: list[CardPostResult]


class ChannelReplyPoll:
    """Reads pending cards from memory, polls each thread, returns resolved decisions."""

    PENDING_KEY = "pending_cards.json"
    BOT_AUTHOR_IDS_KEY = "bot_author_ids.json"  # bot replies to ignore

    def __init__(
        self,
        *,
        graph: GraphAdapterProtocol,
        memory: MemoryStoreClient,
    ) -> None:
        self._graph = graph
        self._memory = memory

    async def collect(self) -> CollectedReplies:
        pending = self._read_pending()
        bot_ids = set(self._read_bot_ids())

        draft_decisions: dict[str, DraftReply] = {}
        triage_decisions: dict[str, TriageReply] = {}
        still: list[CardPostResult] = []

        for card in pending:
            replies = await self._graph.list_channel_replies(
                team_id=card.team_id,
                channel_id=card.channel_id,
                message_id=card.message_id,
            )
            decision = self._first_decision(card, replies, bot_ids=bot_ids)

            if decision is None:
                still.append(card)
                continue

            if isinstance(decision, DraftReply):
                draft_decisions[card.callback_id] = decision
            else:
                triage_decisions[card.callback_id] = decision

        self._write_pending(still)

        return CollectedReplies(
            draft_decisions=draft_decisions,
            triage_decisions=triage_decisions,
            still_pending=still,
        )

    @staticmethod
    def _first_decision(
        card: CardPostResult,
        replies: list[ChannelReply],
        *,
        bot_ids: set[str],
    ) -> DraftReply | TriageReply | None:
        sorted_replies = sorted(replies, key=lambda r: r.created_at)
        for r in sorted_replies:
            if r.author_id and r.author_id in bot_ids:
                continue
            if card.kind == "client_email_draft":
                draft = parse_draft_reply(r)
                if draft is not None:
                    return draft
            elif card.kind == "triage":
                triage = parse_triage_reply(r)
                if triage is not None:
                    return triage
            # status_ok / degraded carry no callback contract; the poll never
            # produces decisions for them — they're informational only.
        return None

    def _read_pending(self) -> list[CardPostResult]:
        if not self._memory.exists(self.PENDING_KEY):
            return []
        raw = self._memory.read_json(self.PENDING_KEY)
        if not isinstance(raw, list):
            return []
        return [CardPostResult.from_dict(entry) for entry in raw]

    def _write_pending(self, cards: list[CardPostResult]) -> None:
        self._memory.write_json(
            self.PENDING_KEY,
            [card.to_dict() for card in cards],
        )

    def _read_bot_ids(self) -> list[str]:
        if not self._memory.exists(self.BOT_AUTHOR_IDS_KEY):
            return []
        raw = self._memory.read_json(self.BOT_AUTHOR_IDS_KEY)
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw]

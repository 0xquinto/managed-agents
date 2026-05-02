"""TeamsCardPoster — posts plain-text status / triage / draft / degraded "cards"
to Teams channels.

Per spec § 2.3 Option B: v1 ships plain-text channel messages with explicit
APPROVE / EDIT <body> / REJECT <reason> instructions. The poller polls the reply
thread; Adaptive Cards with action buttons are deferred to v2 (requires bot
registration + public HTTPS callback, neither of which v1 has).

Each post returns a CardPostResult with the team_id + channel_id + posted
message_id. The caller stores these in a `pending_cards.json` memory key so the
next poll cycle can collect replies.

The "draft" card is the only one that gates a follow-up action (sendMail upon
APPROVE). Status-OK / triage / degraded cards are informational — no callback
contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from poller.adapters.graph import GraphAdapterProtocol
from poller.components.manifest_step import ManifestPost
from poller.exceptions import GraphError, SchemaValidationError
from poller.schemas import EmailMeta, ResolverEnvelope


@dataclass(frozen=True)
class ChannelRef:
    """Pointer to a Teams channel."""

    team_id: str
    channel_id: str


CARD_POST_RESULT_SCHEMA_VERSION = 1


def _coerce_schema_version(v: object) -> int:
    """Best-effort coerce a persisted schema_version to int; default to 1."""
    if v is None:
        return 1
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 1
    return 1


@dataclass(frozen=True)
class CardPostResult:
    """Result of posting a card. The message_id is the parent of the reply thread.

    Persisted to memory under `pending_cards.json` between cycles. The
    `schema_version` field exists so future field additions / removals can be
    handled tolerantly by `from_dict()` instead of crashing on every persisted
    card from before the deploy.
    """

    kind: str  # "status_ok" | "client_email_draft" | "triage" | "degraded"
    team_id: str
    channel_id: str
    message_id: str
    contract_id: str | None
    callback_id: str  # opaque correlation id for HITL resume tracking
    schema_version: int = CARD_POST_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize for memory persistence — always includes schema_version."""
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "team_id": self.team_id,
            "channel_id": self.channel_id,
            "message_id": self.message_id,
            "contract_id": self.contract_id,
            "callback_id": self.callback_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> CardPostResult:
        """Tolerant loader. Drops unknown keys, defaults missing schema_version
        to 1, raises clearly when a *required* field (kind / team_id /
        channel_id / message_id / callback_id) is absent.

        Forward-compat: future versions can add fields with defaults; older
        cards round-trip cleanly because the loader fills in the default and
        ignores any keys this codebase doesn't recognize.
        """
        required = ("kind", "team_id", "channel_id", "message_id", "callback_id")
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValueError(
                f"CardPostResult.from_dict missing required keys: {missing}"
            )
        return cls(
            kind=str(raw["kind"]),
            team_id=str(raw["team_id"]),
            channel_id=str(raw["channel_id"]),
            message_id=str(raw["message_id"]),
            contract_id=(
                str(raw["contract_id"]) if raw.get("contract_id") is not None else None
            ),
            callback_id=str(raw["callback_id"]),
            schema_version=_coerce_schema_version(raw.get("schema_version")),
        )


class TeamsCardPoster:
    """Renders + posts the four card kinds described in spec § 6 + § 2.3.

    Channel routing:
      - triage cards          → triage_channel (e.g., #contracts-triage)
      - status_ok / draft /
        degraded              → caller-provided per-contract channel
    """

    APPROVAL_INSTRUCTIONS = (
        "Reply with one of:\n"
        "  • APPROVE — send the draft as written\n"
        "  • EDIT <new body> — send your edited body instead\n"
        "  • REJECT <reason> — drop the draft, log the reason"
    )

    def __init__(
        self,
        *,
        graph: GraphAdapterProtocol,
        triage_channel: ChannelRef,
    ) -> None:
        self._graph = graph
        self._triage = triage_channel

    async def post_status_ok(
        self,
        *,
        post: ManifestPost,
        channel: ChannelRef,
        callback_id: str,
    ) -> CardPostResult:
        if post.kind != "status_ok":
            raise SchemaValidationError(
                f"post_status_ok called with kind={post.kind!r}"
            )
        body = (
            f"✅ Ingestion complete — `{post.contract_id}`\n\n"
            f"{post.summary}\n\n"
            f"Manifest: `{post.manifest.contract_id}` "
            f"({len(post.manifest.outputs)} outputs, "
            f"{len(post.manifest.quality_flags)} quality flags)\n"
            f"Callback: `{callback_id}`"
        )
        return await self._post(
            kind="status_ok",
            channel=channel,
            body=body,
            contract_id=post.contract_id,
            callback_id=callback_id,
        )

    async def post_email_draft(
        self,
        *,
        post: ManifestPost,
        channel: ChannelRef,
        callback_id: str,
    ) -> CardPostResult:
        if post.kind != "client_email_draft":
            raise SchemaValidationError(
                f"post_email_draft called with kind={post.kind!r}"
            )
        draft = post.manifest.client_email_draft
        if draft is None:
            raise SchemaValidationError(
                "post_email_draft requires manifest.client_email_draft"
            )
        body = (
            f"📧 Draft client follow-up — `{post.contract_id}`\n\n"
            f"**To:** {', '.join(draft.to)}\n"
            f"**Subject:** {draft.subject}\n"
            f"**Language:** {draft.language}\n"
            f"**Missing fields referenced:** "
            f"{', '.join(draft.missing_fields_referenced) or '(none)'}\n\n"
            f"---\n{draft.body}\n---\n\n"
            f"{self.APPROVAL_INSTRUCTIONS}\n\n"
            f"Callback: `{callback_id}`"
        )
        return await self._post(
            kind="client_email_draft",
            channel=channel,
            body=body,
            contract_id=post.contract_id,
            callback_id=callback_id,
        )

    async def post_triage(
        self,
        *,
        envelope: ResolverEnvelope,
        email: EmailMeta,
        callback_id: str,
    ) -> CardPostResult:
        body_lines = [
            f"❓ Triage required — resolver could not classify email `{email.messageId}`",
            "",
            f"**From:** {email.from_}",
            f"**Subject:** {email.subject}",
            f"**Confidence:** {envelope.confidence:.2f}",
            f"**Rationale:** {envelope.rationale_short}",
        ]
        if envelope.triage_payload is not None:
            body_lines.append("")
            body_lines.append(f"**Question:** {envelope.triage_payload.question}")
            for cand in envelope.triage_payload.candidates:
                body_lines.append(
                    f"  • `{cand.contract_id}` (score {cand.score:.2f}) — {cand.reason}"
                )
            inferred = envelope.triage_payload.inferred_new_contract
            if inferred is not None:
                body_lines.append(
                    f"  • or new contract: {inferred.client_name_guess} "
                    f"(@ {inferred.sender_domain})"
                )
        body_lines.extend([
            "",
            "Reply with the chosen `contract_id`, `new <client_name>`, or `drop <reason>`.",
            "",
            f"Callback: `{callback_id}`",
        ])
        return await self._post(
            kind="triage",
            channel=self._triage,
            body="\n".join(body_lines),
            contract_id=envelope.contract_id,
            callback_id=callback_id,
        )

    async def post_degraded(
        self,
        *,
        post: ManifestPost,
        channel: ChannelRef,
        callback_id: str,
    ) -> CardPostResult:
        if post.kind != "degraded":
            raise SchemaValidationError(
                f"post_degraded called with kind={post.kind!r}"
            )
        body = (
            f"⚠️ Degraded ingestion — `{post.contract_id}`\n\n"
            f"{post.summary}\n\n"
            f"Reason: `{post.rejection_reason or 'unspecified'}`\n\n"
            f"Callback: `{callback_id}`"
        )
        return await self._post(
            kind="degraded",
            channel=channel,
            body=body,
            contract_id=post.contract_id,
            callback_id=callback_id,
        )

    # -------------------------------------------------------------- internals

    async def _post(
        self,
        *,
        kind: str,
        channel: ChannelRef,
        body: str,
        contract_id: str | None,
        callback_id: str,
    ) -> CardPostResult:
        try:
            message_id = await self._graph.post_channel_message(
                team_id=channel.team_id,
                channel_id=channel.channel_id,
                body_text=body,
            )
        except GraphError:
            raise
        except Exception as exc:
            raise GraphError(f"_post failed for kind={kind}: {exc}") from exc
        return CardPostResult(
            kind=kind,
            team_id=channel.team_id,
            channel_id=channel.channel_id,
            message_id=message_id,
            contract_id=contract_id,
            callback_id=callback_id,
        )

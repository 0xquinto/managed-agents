"""MailFeed component — fetches new mail from the watched inbox via Graph delta query.

Persists the deltaLink cursor in the memory store so each scheduler tick resumes from
exactly where the last one left off. Per spec § 2.1 + § 5.1.
"""

from __future__ import annotations

from poller.adapters.graph import GraphAdapterProtocol
from poller.adapters.memory import MemoryStoreClient
from poller.schemas import EmailMeta


class MailFeed:
    """Fetches new mail since the last delta cursor; updates the cursor on success."""

    CURSOR_PATH = "mail_cursor.json"
    CURSOR_KEY = "deltaLink"

    def __init__(
        self,
        *,
        graph: GraphAdapterProtocol,
        memory: MemoryStoreClient,
    ) -> None:
        self._graph = graph
        self._memory = memory

    async def fetch_new(self) -> list[EmailMeta]:
        """Fetch all messages new since the persisted deltaLink.

        On the very first call ever (no cursor in memory yet), this consumes the
        current state of the inbox and returns whatever it sees. Subsequent calls
        return only what arrived since the last call.
        """
        delta_link = self._read_cursor()
        messages, next_link = await self._graph.list_new_messages_via_delta(
            delta_link=delta_link
        )
        self._write_cursor(next_link)
        return messages

    def _read_cursor(self) -> str | None:
        cursor = self._memory.read_mail_cursor()
        if cursor is None:
            return None
        link = cursor.get(self.CURSOR_KEY)
        if link is not None and not isinstance(link, str):
            raise TypeError(
                f"mail_cursor.json {self.CURSOR_KEY} must be a string, got {type(link).__name__}"
            )
        return link

    def _write_cursor(self, delta_link: str) -> None:
        self._memory.write_mail_cursor({self.CURSOR_KEY: delta_link})

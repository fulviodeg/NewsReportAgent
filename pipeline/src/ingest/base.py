"""IngestSource interface — the single swap point for news sources.

v1 implements IMAP (imap_source.py). A webhook or RSS source can be added later by
implementing this interface, with no change to any downstream stage.
See docs/v1-architecture.md (Sections 4 and 11).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, Optional


@dataclass
class RawMessage:
    """A raw newsletter message, normalized to a small header set + the parsed email."""

    from_address: str
    from_name: str
    subject: str
    date: str  # ISO-8601 (best effort)
    message_id: str
    message: EmailMessage


class IngestSource(ABC):
    """A source of raw messages to be parsed into news items."""

    @abstractmethod
    def fetch_new(self, since: Optional[str] = None) -> Iterable[RawMessage]:
        """Yield messages newer than `since` (ISO-8601), or all if `since` is None."""
        raise NotImplementedError

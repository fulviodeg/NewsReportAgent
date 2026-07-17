"""IngestSource interface — the single swap point for news sources.

v1 implements IMAP (imap_source.py). A webhook or RSS source can be added later by
implementing this interface, with no change to any downstream stage.
See docs/v1-architecture.md (Sections 4 and 11).
"""

from abc import ABC, abstractmethod


class IngestSource(ABC):
    """A source of raw messages to be parsed into news items."""

    @abstractmethod
    def fetch_new(self):
        """Yield raw messages newer than the last successful poll.

        Each message carries sender, subject, received date, and a stable message id.
        """
        raise NotImplementedError

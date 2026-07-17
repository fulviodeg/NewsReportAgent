"""IMAP implementation of IngestSource. Uses stdlib imaplib/email. No LLM.

Connects to the dedicated mailbox and fetches only messages newer than the last
successful poll (tracked by UID or date in the store).
"""

from .base import IngestSource


class ImapSource(IngestSource):
    def fetch_new(self):
        raise NotImplementedError

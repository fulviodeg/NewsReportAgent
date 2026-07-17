"""IMAP implementation of IngestSource. Uses stdlib imaplib/email. No LLM.

Connects to the dedicated mailbox and fetches only messages newer than the last successful
poll (via IMAP SEARCH SINCE). Idempotency downstream is guaranteed by the item content
hash, so exact UID tracking is not required.
"""

from __future__ import annotations

import email
import imaplib
from datetime import datetime
from email.policy import default as default_policy
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterable, Optional

from .base import IngestSource, RawMessage


def _imap_since(since_iso: str) -> str:
    """Convert an ISO-8601 timestamp to IMAP SEARCH date format (DD-Mon-YYYY)."""
    dt = datetime.strptime(since_iso[:10], "%Y-%m-%d")
    return dt.strftime("%d-%b-%Y")


def _to_record(msg) -> RawMessage:
    name, addr = parseaddr(msg["From"] or "")
    try:
        date_iso = parsedate_to_datetime(msg["Date"]).isoformat()
    except (TypeError, ValueError):
        date_iso = ""
    return RawMessage(
        from_address=addr,
        from_name=name,
        subject=str(msg["Subject"] or ""),
        date=date_iso,
        message_id=str(msg["Message-ID"] or ""),
        message=msg,
    )


class ImapSource(IngestSource):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        mailbox: str = "INBOX",
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mailbox = mailbox

    def fetch_new(self, since: Optional[str] = None) -> Iterable[RawMessage]:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.username, self.password)
            conn.select(self.mailbox)
            if since:
                typ, data = conn.search(None, "SINCE", _imap_since(since))
            else:
                typ, data = conn.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return
            for num in data[0].split():
                typ, msgdata = conn.fetch(num, "(RFC822)")
                if typ != "OK" or not msgdata or not msgdata[0]:
                    continue
                raw_bytes = msgdata[0][1]
                msg = email.message_from_bytes(raw_bytes, policy=default_policy)
                yield _to_record(msg)
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

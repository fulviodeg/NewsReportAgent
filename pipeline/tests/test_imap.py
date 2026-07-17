from email.message import EmailMessage

import src.ingest.imap_source as imap_mod
from src.ingest.imap_source import ImapSource


def _raw_email_bytes(from_addr: str) -> bytes:
    m = EmailMessage()
    m["From"] = from_addr
    m["Subject"] = "Hello"
    m["Date"] = "Mon, 14 Jul 2026 10:00:00 +0000"
    m["Message-ID"] = "<abc@x>"
    m.set_content("body")
    return m.as_bytes()


class FakeIMAP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.searched = None

    def login(self, u, p):
        return ("OK", [b""])

    def select(self, mailbox):
        return ("OK", [b"1"])

    def search(self, charset, *criteria):
        self.searched = criteria
        return ("OK", [b"1 2"])

    def fetch(self, num, spec):
        return ("OK", [(b"%s (RFC822 {N})" % num, _raw_email_bytes("news@example.com"))])

    def close(self):
        return ("OK", [b""])

    def logout(self):
        return ("BYE", [b""])


def test_imap_source_parses_fetched_messages(monkeypatch):
    monkeypatch.setattr(imap_mod.imaplib, "IMAP4_SSL", FakeIMAP)
    src = ImapSource("imap.example.com", 993, "u", "p")
    records = list(src.fetch_new())
    assert len(records) == 2
    assert records[0].from_address == "news@example.com"
    assert records[0].subject == "Hello"
    assert records[0].message_id == "<abc@x>"


def test_imap_source_uses_since_criteria(monkeypatch):
    captured = {}

    class Cap(FakeIMAP):
        def search(self, charset, *criteria):
            captured["criteria"] = criteria
            return ("OK", [b""])

    monkeypatch.setattr(imap_mod.imaplib, "IMAP4_SSL", Cap)
    src = ImapSource("h", 993, "u", "p")
    list(src.fetch_new(since="2026-07-10T00:00:00Z"))
    assert captured["criteria"] == ("SINCE", "10-Jul-2026")

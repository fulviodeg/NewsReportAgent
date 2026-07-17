from email.message import EmailMessage

from src.config import Source
from src.ingest.base import IngestSource, RawMessage
from src.main import run_collection
from src.store import db

HTML = """
<html><body>
  <div class="item"><a href="https://news.example.com/a">Story A about AI systems</a>
    <p>Details about story A and its impact.</p></div>
  <div class="item"><a href="https://news.example.com/b">Story B about fintech growth</a>
    <p>Details about story B.</p></div>
</body></html>
"""


def _msg(from_addr: str) -> RawMessage:
    m = EmailMessage()
    m["From"] = from_addr
    m["Subject"] = "Digest"
    m.set_content("fallback")
    m.add_alternative(HTML, subtype="html")
    return RawMessage(from_addr, "", "Digest", "", "<id>", m)


class FakeSource(IngestSource):
    def __init__(self, messages):
        self._messages = messages

    def fetch_new(self, since=None):
        return list(self._messages)


def _fresh():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


CFG = [Source(name="Example", from_address="news@example.com")]


def test_collection_inserts_items_and_writes_run():
    conn = _fresh()
    counts = run_collection(conn, FakeSource([_msg("news@example.com")]), CFG)
    assert counts["messages"] == 1
    assert counts["items_inserted"] == 2
    assert len(db.get_recent_items(conn, 72)) == 2
    assert db.last_run_started_at(conn, "collection") is not None


def test_collection_is_idempotent_on_rerun():
    conn = _fresh()
    src = FakeSource([_msg("news@example.com")])
    run_collection(conn, src, CFG)
    second = run_collection(conn, src, CFG)
    assert second["items_inserted"] == 0  # same content hashes -> nothing new
    assert len(db.get_recent_items(conn, 72)) == 2


def test_collection_skips_unknown_senders():
    conn = _fresh()
    counts = run_collection(conn, FakeSource([_msg("stranger@spam.com")]), CFG)
    assert counts["unknown_senders"] == 1
    assert counts["items_inserted"] == 0
    assert db.get_recent_items(conn, 72) == []

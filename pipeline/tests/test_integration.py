"""Full-chain integration test with all external services faked (runs offline).

collection (FakeSource) -> processing (FakeEmbeddings + ScriptedLLM) -> export.json
"""

import json
from email.message import EmailMessage
from pathlib import Path

from src.config import Source, load_config
from src.embeddings import EmbeddingsProvider
from src.ingest.base import IngestSource, RawMessage
from src.llm import LLMResult
from src.main import run_collection, run_processing
from src.store import db

CONFIG_PATH = str(Path(__file__).parents[1] / "config.toml")

HTML = """
<html><body>
  <div class="item"><a href="https://a.example/apple">grp1 Apple unveils new chip</a>
    <p>grp1 Apple announced a new processor today.</p></div>
</body></html>
"""

HTML2 = """
<html><body>
  <div class="item"><a href="https://b.example/apple">grp1 Apple new processor</a>
    <p>grp1 Apple's chip reported by another outlet.</p></div>
</body></html>
"""


def _raw(from_addr, html):
    m = EmailMessage()
    m["From"] = from_addr
    m["Subject"] = "Digest"
    m.set_content("fallback")
    m.add_alternative(html, subtype="html")
    return RawMessage(from_addr, "", "Digest", "", "<id>", m)


class FakeSource(IngestSource):
    def __init__(self, messages):
        self._messages = messages

    def fetch_new(self, since=None):
        return list(self._messages)


class FakeEmbeddingsProvider(EmbeddingsProvider):
    def embed(self, texts):
        return [[1.0, 0.0] if "grp1" in t else [0.0, 1.0] for t in texts]


class ScriptedLLM:
    def complete(self, model, messages, response_json=True):
        if "classifier" in messages[0]["content"]:
            return LLMResult('{"theme":"AI","companies":["Apple"],"relevance":0.9}', 0.001)
        return LLMResult(
            '{"title":"Apple presenta il chip M5","subtitle":"Nuovo processore on-device",'
            '"summary_it":"Apple ha presentato un nuovo chip.",'
            '"summary_long":"Apple ha presentato il chip M5 con miglioramenti AI on-device.",'
            '"source_links":["https://a.example/apple"]}',
            0.001,
        )


def test_full_chain(tmp_path):
    conn = db.connect(":memory:")
    db.init_schema(conn)
    cfg = load_config(CONFIG_PATH)
    cfg.sources = [
        Source(name="A", from_address="a@x.com"),
        Source(name="B", from_address="b@x.com"),
    ]

    source = FakeSource([_raw("a@x.com", HTML), _raw("b@x.com", HTML2)])
    collected = run_collection(conn, source, cfg.sources)
    assert collected["items_inserted"] == 2

    out = str(tmp_path / "export.json")
    processed = run_processing(conn, cfg, FakeEmbeddingsProvider(), ScriptedLLM(), out)

    # both outlets report the same story -> one cluster with two sources
    assert processed["new_clusters"] == 1
    assert processed["synthesized"] == 1
    data = json.loads(Path(out).read_text())
    assert len(data["stories"]) == 1
    assert len(data["stories"][0]["sources"]) == 2
    assert data["stories"][0]["theme"] == "AI"

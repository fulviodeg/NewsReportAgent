import json
from pathlib import Path

from src.config import load_config
from src.embeddings import EmbeddingsProvider
from src.llm import LLMResult
from src.main import run_processing
from src.store import db

CONFIG_PATH = str(Path(__file__).parents[1] / "config.toml")


class FakeEmbeddingsProvider(EmbeddingsProvider):
    def embed(self, texts):
        out = []
        for t in texts:
            if "grp1" in t:
                out.append([1.0, 0.0, 0.0])
            elif "grp2" in t:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out


class ScriptedLLM:
    """Valid classify for all; valid synth except for the grp2 story (tests isolation)."""

    def __init__(self):
        self.calls = 0

    def complete(self, model, messages, response_json=True):
        self.calls += 1
        is_classify = "classifier" in messages[0]["content"]
        user = messages[1]["content"]
        if is_classify:
            return LLMResult('{"theme":"AI","companies":["Acme"],"relevance":0.7}', 0.001)
        if "grp2" in user:
            return LLMResult('{"title":"x","subtitle":"y","summary_it":"z","summary_long":"w","source_links":[]}', 0.001)  # invalid
        return LLMResult(
            '{"title":"Nuovo chip","subtitle":"Contesto","summary_it":"Sintesi breve",'
            '"summary_long":"Approfondimento esteso con English terms","entities":["Acme"],'
            '"source_links":["https://a/1"]}',
            0.001,
        )


def _seed(conn):
    a = db.upsert_source(conn, "Testata A", "a@x.com")
    b = db.upsert_source(conn, "Testata B", "b@x.com")
    db.insert_item(conn, a, "grp1 Apple chip", "grp1 story", "https://a/1", "h1")
    db.insert_item(conn, b, "grp1 Apple processor", "grp1 story", "https://b/1", "h2")
    db.insert_item(conn, a, "grp2 BCE rates", "grp2 story", "https://a/2", "h3")


def _fresh():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_processing_end_to_end_with_per_item_isolation(tmp_path):
    conn = _fresh()
    _seed(conn)
    cfg = load_config(CONFIG_PATH)
    out = str(tmp_path / "export.json")

    counts = run_processing(conn, cfg, FakeEmbeddingsProvider(), ScriptedLLM(), out)

    assert counts["new_clusters"] == 2
    assert counts["classified"] == 2
    assert counts["synthesized"] == 1
    assert counts["synthesize_skipped"] == 1  # grp2 invalid, isolated
    assert counts["exported"] == 1

    data = json.loads(Path(out).read_text())
    assert len(data["stories"]) == 1
    story = data["stories"][0]
    assert story["theme"] == "AI"
    assert story["title"] == "Nuovo chip"
    assert story["subtitle"]
    assert story["summary_long"]
    assert story["entities"] == ["Acme"]
    assert {s["testata"] for s in story["sources"]} == {"Testata A", "Testata B"}
    assert data["themes"] == ["AI"]

    run = conn.execute("SELECT outcome FROM runs WHERE kind='processing'").fetchone()
    assert run["outcome"] == "ok"


def test_processing_is_idempotent(tmp_path):
    conn = _fresh()
    _seed(conn)
    cfg = load_config(CONFIG_PATH)
    out = str(tmp_path / "export.json")
    run_processing(conn, cfg, FakeEmbeddingsProvider(), ScriptedLLM(), out)

    second = run_processing(conn, cfg, FakeEmbeddingsProvider(), ScriptedLLM(), out)
    assert second["new_clusters"] == 0
    assert second["classified"] == 0  # already classified
    assert second["synthesized"] == 0  # grp1 already synthesized


def test_cost_cap_stops_run(tmp_path):
    conn = _fresh()
    _seed(conn)
    cfg = load_config(CONFIG_PATH)
    cfg.cost.daily_usd_cap = 0.0  # cap already reached -> block first call
    out = str(tmp_path / "export.json")

    counts = run_processing(conn, cfg, FakeEmbeddingsProvider(), ScriptedLLM(), out)
    assert counts["classified"] == 0
    run = conn.execute("SELECT outcome FROM runs WHERE kind='processing'").fetchone()
    assert run["outcome"] == "cost_cap_hit"

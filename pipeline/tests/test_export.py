import json
from pathlib import Path

from src.export import build_payload, export_json
from src.store import db


def _fresh():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def _story(conn, sources, theme, companies, relevance, summary):
    ids = []
    for name, addr, title, link in sources:
        sid = db.upsert_source(conn, name, addr)
        h = f"{title}{link}"
        db.insert_item(conn, sid, title, "text", link, h)
        row = conn.execute(
            "SELECT id FROM items WHERE content_hash = ?", (h,)
        ).fetchone()
        ids.append(row["id"])
    cid = db.insert_cluster(conn, ids)
    db.set_classification(conn, cid, theme, companies, relevance)
    db.set_synthesis(conn, cid, summary)
    return cid


def test_build_payload_shape_and_facets():
    conn = _fresh()
    _story(
        conn,
        [("Testata A", "a@x", "Apple M5", "https://a/1"),
         ("Testata B", "b@x", "Apple chip", "https://b/1")],
        "AI",
        ["Apple"],
        0.7,
        "Sintesi",
    )
    payload = build_payload(conn, min_relevance=0.3)
    assert payload["themes"] == ["AI"]
    assert payload["companies"] == ["Apple"]
    assert sorted(payload["testate"]) == ["Testata A", "Testata B"]
    story = payload["stories"][0]
    assert len(story["sources"]) == 2
    assert story["summary_it"] == "Sintesi"
    assert "generated_at" in payload


def test_min_relevance_filter():
    conn = _fresh()
    _story(conn, [("A", "a@x", "t1", "https://a/1")], "AI", [], 0.9, "keep")
    _story(conn, [("A", "a@x", "t2", "https://a/2")], "AI", [], 0.1, "drop")
    payload = build_payload(conn, min_relevance=0.3)
    assert len(payload["stories"]) == 1
    assert payload["stories"][0]["summary_it"] == "keep"


def test_export_json_atomic_and_no_temp_left(tmp_path):
    conn = _fresh()
    _story(conn, [("A", "a@x", "t1", "https://a/1")], "AI", [], 0.9, "s")
    out = tmp_path / "export.json"
    n = export_json(conn, 0.3, str(out))
    assert n == 1
    assert json.loads(out.read_text())["stories"][0]["summary_it"] == "s"
    # atomic write leaves no stray temp files behind
    assert list(tmp_path.glob("*.tmp")) == []


def test_export_overwrites_previous(tmp_path):
    conn = _fresh()
    out = tmp_path / "export.json"
    export_json(conn, 0.3, str(out))
    assert json.loads(out.read_text())["stories"] == []
    _story(conn, [("A", "a@x", "t1", "https://a/1")], "AI", [], 0.9, "s")
    export_json(conn, 0.3, str(out))
    assert len(json.loads(out.read_text())["stories"]) == 1

import json
from pathlib import Path

from src.export import build_payload, export_dashboard, export_json
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
    db.set_synthesis(
        conn, cid, f"Titolo {summary}", "Sottotitolo", summary, f"Lungo {summary}", companies
    )
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


def test_recent_window_and_archive(tmp_path):
    conn = _fresh()
    old = _story(conn, [("A", "a@x", "old", "https://a/old")], "AI", [], 0.9, "vecchia")
    _story(conn, [("A", "a@x", "new", "https://a/new")], "AI", [], 0.9, "recente")
    conn.execute("UPDATE clusters SET processed_at = ? WHERE id = ?", ("2000-01-01T00:00:00Z", old))
    conn.commit()

    recent = build_payload(conn, 0.3, since_days=7)
    assert len(recent["stories"]) == 1
    assert build_payload(conn, 0.3)["stories"].__len__() == 2

    out = tmp_path / "export.json"
    res = export_dashboard(conn, 0.3, 7, str(out))
    assert res == {"recent": 1, "archive": 2}
    assert (tmp_path / "archive.json").exists()
    assert len(json.loads((tmp_path / "archive.json").read_text())["stories"]) == 2


def test_entities_in_payload():
    conn = _fresh()
    cid = _story(conn, [("A", "a@x", "t", "https://a/1")], "AI", ["Nvidia"], 0.9, "s")
    assert cid
    payload = build_payload(conn, 0.3)
    assert payload["stories"][0]["entities"] == ["Nvidia"]

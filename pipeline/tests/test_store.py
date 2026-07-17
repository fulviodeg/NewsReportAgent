from src.store import db


def _fresh():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def test_init_schema_idempotent_and_tables_exist():
    conn = _fresh()
    db.init_schema(conn)  # second call must be a no-op
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"sources", "items", "embeddings", "clusters", "runs"} <= names


def test_item_insert_is_idempotent_on_content_hash():
    conn = _fresh()
    sid = db.upsert_source(conn, "Testata", "news@example.com")
    assert db.insert_item(conn, sid, "T", "body", "https://x/1", "hash1") is True
    # same content_hash again -> ignored
    assert db.insert_item(conn, sid, "T", "body", "https://x/1", "hash1") is False
    rows = db.get_recent_items(conn, window_hours=72)
    assert len(rows) == 1


def test_upsert_source_returns_stable_id():
    conn = _fresh()
    a = db.upsert_source(conn, "Testata", "news@example.com")
    b = db.upsert_source(conn, "Testata", "news@example.com")
    assert a == b


def test_embeddings_roundtrip():
    conn = _fresh()
    sid = db.upsert_source(conn, "T", "a@b.com")
    db.insert_item(conn, sid, "t", "x", "l", "h")
    item_id = db.get_recent_items(conn, 72)[0]["id"]
    db.put_embedding(conn, item_id, "model-x", [0.1, 0.2, 0.3])
    got = db.get_embeddings(conn, [item_id])
    assert got[item_id] == [0.1, 0.2, 0.3]


def test_cluster_lifecycle():
    conn = _fresh()
    cid = db.insert_cluster(conn, [1, 2])
    assert db.clusters_needing_classification(conn)[0]["id"] == cid
    db.set_classification(conn, cid, "AI", ["Acme"], 0.8)
    assert not db.clusters_needing_classification(conn)
    assert db.clusters_needing_synthesis(conn)[0]["id"] == cid
    db.set_synthesis(conn, cid, "Titolo", "Sottotitolo", "Sintesi in italiano", "Approfondimento", ["Acme"])
    assert not db.clusters_needing_synthesis(conn)
    exp = db.exportable_clusters(conn, min_relevance=0.3)
    assert len(exp) == 1 and exp[0]["summary_it"] == "Sintesi in italiano"


def test_exportable_respects_min_relevance():
    conn = _fresh()
    cid = db.insert_cluster(conn, [1])
    db.set_classification(conn, cid, "AI", [], 0.1)
    db.set_synthesis(conn, cid, "t", "s", "summary", "long", [])
    assert db.exportable_clusters(conn, min_relevance=0.3) == []


def test_runs_and_todays_cost():
    conn = _fresh()
    rid = db.start_run(conn, "processing")
    db.finish_run(conn, rid, {"clusters": 3}, cost_usd=1.25, outcome="ok")
    assert db.todays_cost(conn) == 1.25
    assert db.last_run_started_at(conn, "processing") is not None
    assert db.last_run_started_at(conn, "collection") is None

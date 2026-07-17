from src.cluster import cluster_items
from src.embeddings import EmbeddingsProvider
from src.store import db
import json


class FakeEmbeddingsProvider(EmbeddingsProvider):
    """Deterministic vectors keyed by a tag present in the text."""

    def __init__(self):
        self.calls = 0
        self.texts_seen = 0

    def embed(self, texts):
        self.calls += 1
        self.texts_seen += len(texts)
        out = []
        for t in texts:
            if "grp1" in t:
                out.append([1.0, 0.0, 0.0])
            elif "grp2" in t:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out


def _fresh():
    conn = db.connect(":memory:")
    db.init_schema(conn)
    return conn


def _seed_two_sources_same_story(conn):
    a = db.upsert_source(conn, "Testata A", "a@x.com")
    b = db.upsert_source(conn, "Testata B", "b@x.com")
    db.insert_item(conn, a, "grp1 Apple chip", "grp1 story", "https://a/1", "h1")
    db.insert_item(conn, b, "grp1 Apple processor", "grp1 story", "https://b/1", "h2")
    db.insert_item(conn, a, "grp2 BCE rates", "grp2 story", "https://a/2", "h3")


def test_similar_items_cluster_together_distant_separate():
    conn = _fresh()
    _seed_two_sources_same_story(conn)
    stats = cluster_items(conn, FakeEmbeddingsProvider(), 0.82, 72, "fake-model")
    assert stats["new_clusters"] == 2
    assert stats["joined"] == 1
    assert stats["embedded"] == 3

    clusters = db.get_clusters(conn)
    sizes = sorted(len(json.loads(c["member_ids"])) for c in clusters)
    assert sizes == [1, 2]  # the grp1 story has both sources


def test_cluster_exposes_multiple_sources():
    conn = _fresh()
    _seed_two_sources_same_story(conn)
    cluster_items(conn, FakeEmbeddingsProvider(), 0.82, 72, "fake-model")

    big = next(c for c in db.get_clusters(conn) if len(json.loads(c["member_ids"])) == 2)
    members = db.get_items_by_ids(conn, json.loads(big["member_ids"]))
    assert {m["source_name"] for m in members} == {"Testata A", "Testata B"}


def test_clustering_is_idempotent_and_caches_embeddings():
    conn = _fresh()
    _seed_two_sources_same_story(conn)
    provider = FakeEmbeddingsProvider()
    cluster_items(conn, provider, 0.82, 72, "fake-model")
    before = len(db.get_clusters(conn))

    second = cluster_items(conn, provider, 0.82, 72, "fake-model")
    assert second["new_clusters"] == 0
    assert second["joined"] == 0
    assert second["embedded"] == 0  # vectors were cached, not recomputed
    assert len(db.get_clusters(conn)) == before

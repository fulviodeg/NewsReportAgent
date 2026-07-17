"""Dedup and cluster items into stories. Deterministic + embeddings.

A cluster is one story; its members are the items (from possibly different sources) that
report it. Algorithm: embed each recent item (once, then cached in the store), then greedy
single-linkage by cosine similarity within a time window. An item joins an existing cluster
if its similarity to any member is >= threshold, otherwise it starts a new cluster.

Idempotency: only items not already in a cluster are placed, and embeddings are computed
once and persisted, so re-running adds no new clusters and no duplicate membership. The
"other sources reporting the same story" data falls out of cluster membership (see export).
See docs/v1-architecture.md (Sections 4.3 and 8).
"""

from __future__ import annotations

import json
import sqlite3

from .embeddings import EmbeddingsProvider, unit_normalize
from .store import db


def _embed_text(row: sqlite3.Row) -> str:
    return f"{row['title']} {row['text']}".strip()


def _cosine(a: list[float], b: list[float]) -> float:
    # vectors are unit-normalized on store, so cosine == dot product
    return sum(x * y for x, y in zip(a, b))


def cluster_items(
    conn: sqlite3.Connection,
    provider: EmbeddingsProvider,
    similarity_threshold: float,
    window_hours: int,
    model: str,
) -> dict:
    recent = db.get_recent_items(conn, window_hours)
    if not recent:
        return {"new_clusters": 0, "joined": 0, "embedded": 0}

    recent_ids = [r["id"] for r in recent]
    text_by_id = {r["id"]: _embed_text(r) for r in recent}

    # Embed only items that lack a stored vector (cost + idempotency).
    embeds = db.get_embeddings(conn, recent_ids)
    missing = [i for i in recent_ids if i not in embeds]
    embedded = 0
    if missing:
        vectors = provider.embed([text_by_id[i] for i in missing])
        for item_id, vec in zip(missing, vectors):
            nv = unit_normalize(vec)
            db.put_embedding(conn, item_id, model, nv)
            embeds[item_id] = nv
            embedded += 1

    # Active clusters = existing clusters containing any recent item; seed the in-memory set.
    recent_set = set(recent_ids)
    clusters: list[dict] = []
    clustered_ids: set[int] = set()
    for row in db.get_clusters(conn):
        members = json.loads(row["member_ids"])
        clustered_ids.update(members)
        if recent_set.intersection(members):
            member_vecs = db.get_embeddings(conn, members)
            clusters.append(
                {
                    "id": row["id"],
                    "members": list(members),
                    "vecs": [member_vecs[m] for m in members if m in member_vecs],
                }
            )

    new_clusters = joined = 0
    for item_id in recent_ids:
        if item_id in clustered_ids:
            continue
        vec = embeds.get(item_id)
        if vec is None:
            continue

        best_sim, best = 0.0, None
        for cluster in clusters:
            for mv in cluster["vecs"]:
                sim = _cosine(vec, mv)
                if sim > best_sim:
                    best_sim, best = sim, cluster

        if best is not None and best_sim >= similarity_threshold:
            best["members"].append(item_id)
            best["vecs"].append(vec)
            db.update_cluster_members(conn, best["id"], best["members"])
            joined += 1
        else:
            cid = db.insert_cluster(conn, [item_id])
            clusters.append({"id": cid, "members": [item_id], "vecs": [vec]})
            new_clusters += 1
        clustered_ids.add(item_id)

    return {"new_clusters": new_clusters, "joined": joined, "embedded": embedded}

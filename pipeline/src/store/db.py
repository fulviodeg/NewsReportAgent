"""SQLite access. The store is the single source of truth across all runs.

Applies schema.sql on first use and exposes read/write helpers for the tables
(sources, items, embeddings, clusters, runs). WAL + busy_timeout let the scheduler and
an on-demand process share the file safely. Reruns are safe: content-hash uniqueness and
"process only unprocessed rows" make collection and processing idempotent.
See docs/v1-architecture.md (Sections 2 and 4.7).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow_iso() -> str:
    """Current UTC time as a sortable ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _window_cutoff(window_hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql (idempotent: CREATE TABLE IF NOT EXISTS)."""
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


# --- sources ---------------------------------------------------------------

def upsert_source(conn: sqlite3.Connection, name: str, from_address: str) -> int:
    """Return the id of the source with this from_address, inserting if new."""
    conn.execute(
        "INSERT OR IGNORE INTO sources (name, from_address) VALUES (?, ?)",
        (name, from_address),
    )
    row = conn.execute(
        "SELECT id FROM sources WHERE from_address = ?", (from_address,)
    ).fetchone()
    conn.commit()
    return int(row["id"])


# --- items -----------------------------------------------------------------

def insert_item(
    conn: sqlite3.Connection,
    source_id: int,
    title: str,
    text: str,
    link: str,
    content_hash: str,
    collected_at: Optional[str] = None,
) -> bool:
    """Insert a news item; INSERT OR IGNORE on content_hash makes it idempotent.

    Returns True if a new row was inserted, False if it was a duplicate.
    """
    cur = conn.execute(
        """INSERT OR IGNORE INTO items
           (source_id, title, text, link, content_hash, collected_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (source_id, title, text, link, content_hash, collected_at or utcnow_iso()),
    )
    conn.commit()
    return cur.rowcount > 0


def get_recent_items(conn: sqlite3.Connection, window_hours: int) -> list[sqlite3.Row]:
    cutoff = _window_cutoff(window_hours)
    return conn.execute(
        "SELECT * FROM items WHERE collected_at >= ? ORDER BY id", (cutoff,)
    ).fetchall()


def get_items_by_ids(conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    return conn.execute(
        f"SELECT i.*, s.name AS source_name FROM items i "
        f"JOIN sources s ON s.id = i.source_id WHERE i.id IN ({placeholders})",
        ids,
    ).fetchall()


# --- embeddings ------------------------------------------------------------

def put_embedding(
    conn: sqlite3.Connection, item_id: int, model: str, vector: list[float]
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO embeddings (item_id, model, vector) VALUES (?, ?, ?)",
        (item_id, model, json.dumps(vector)),
    )
    conn.execute("UPDATE items SET embedding_ref = ? WHERE id = ?", (model, item_id))
    conn.commit()


def get_embeddings(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, list[float]]:
    if not item_ids:
        return {}
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT item_id, vector FROM embeddings WHERE item_id IN ({placeholders})",
        item_ids,
    ).fetchall()
    return {int(r["item_id"]): json.loads(r["vector"]) for r in rows}


# --- clusters --------------------------------------------------------------

def get_clusters(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM clusters ORDER BY id").fetchall()


def insert_cluster(conn: sqlite3.Connection, member_ids: list[int]) -> int:
    cur = conn.execute(
        "INSERT INTO clusters (member_ids) VALUES (?)", (json.dumps(member_ids),)
    )
    conn.commit()
    return int(cur.lastrowid)


def update_cluster_members(
    conn: sqlite3.Connection, cluster_id: int, member_ids: list[int]
) -> None:
    conn.execute(
        "UPDATE clusters SET member_ids = ? WHERE id = ?",
        (json.dumps(member_ids), cluster_id),
    )
    conn.commit()


def set_classification(
    conn: sqlite3.Connection,
    cluster_id: int,
    theme: str,
    companies: list[str],
    relevance: float,
) -> None:
    conn.execute(
        "UPDATE clusters SET theme = ?, companies = ?, relevance = ? WHERE id = ?",
        (theme, json.dumps(companies), relevance, cluster_id),
    )
    conn.commit()


def set_synthesis(
    conn: sqlite3.Connection,
    cluster_id: int,
    title: str,
    subtitle: str,
    summary_it: str,
    summary_long: str,
) -> None:
    conn.execute(
        "UPDATE clusters SET title = ?, subtitle = ?, summary_it = ?, summary_long = ?, "
        "processed_at = ? WHERE id = ?",
        (title, subtitle, summary_it, summary_long, utcnow_iso(), cluster_id),
    )
    conn.commit()


def clusters_needing_classification(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM clusters WHERE theme IS NULL").fetchall()


def clusters_needing_synthesis(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM clusters WHERE theme IS NOT NULL AND summary_it IS NULL"
    ).fetchall()


def exportable_clusters(
    conn: sqlite3.Connection, min_relevance: float
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM clusters WHERE summary_it IS NOT NULL AND relevance >= ? "
        "ORDER BY processed_at DESC",
        (min_relevance,),
    ).fetchall()


# --- runs ------------------------------------------------------------------

def start_run(conn: sqlite3.Connection, kind: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs (kind, started_at, outcome) VALUES (?, ?, 'running')",
        (kind, utcnow_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    counts: dict,
    cost_usd: float,
    outcome: str,
) -> None:
    conn.execute(
        "UPDATE runs SET ended_at = ?, counts = ?, cost_usd = ?, outcome = ? WHERE id = ?",
        (utcnow_iso(), json.dumps(counts), cost_usd, outcome, run_id),
    )
    conn.commit()


def last_run_started_at(conn: sqlite3.Connection, kind: str) -> Optional[str]:
    row = conn.execute(
        "SELECT started_at FROM runs WHERE kind = ? AND outcome != 'running' "
        "ORDER BY id DESC LIMIT 1",
        (kind,),
    ).fetchone()
    return row["started_at"] if row else None


def todays_cost(conn: sqlite3.Connection) -> float:
    start_of_day = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM runs WHERE started_at >= ?",
        (start_of_day,),
    ).fetchone()
    return float(row["total"])

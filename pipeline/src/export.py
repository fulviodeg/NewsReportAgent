"""Export the ready-to-show stories as a single JSON file. Deterministic.

For each story: Italian summary, theme, companies, sources with links, timestamps. The
"sources" list is built live from cluster membership, so it always reflects every source
reporting the story. Written atomically (temp file + os.replace) so the dashboard never
reads a half-written file. This file is the only thing the dashboard reads.
See docs/v1-architecture.md (Section 4.6).
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from .store import db


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)  # readable by nginx container
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def build_payload(conn: sqlite3.Connection, min_relevance: float, since_days=None) -> dict:
    themes: set[str] = set()
    companies: set[str] = set()
    testate: set[str] = set()
    stories = []

    cutoff = None
    if since_days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    for c in db.exportable_clusters(conn, min_relevance):
        if cutoff and (c["processed_at"] or "") < cutoff:
            continue
        members = db.get_items_by_ids(conn, json.loads(c["member_ids"]))
        story_companies = json.loads(c["companies"]) if c["companies"] else []
        entities = json.loads(c["entities"]) if c["entities"] else []
        sources = [
            {"testata": m["source_name"], "title": m["title"], "link": m["link"]}
            for m in members
        ]
        themes.add(c["theme"])
        companies.update(story_companies)
        testate.update(s["testata"] for s in sources)
        stories.append(
            {
                "id": c["id"],
                "theme": c["theme"],
                "companies": story_companies,
                "entities": entities,
                "relevance": c["relevance"],
                "title": c["title"],
                "subtitle": c["subtitle"],
                "summary_it": c["summary_it"],
                "summary_long": c["summary_long"],
                "processed_at": c["processed_at"],
                "sources": sources,
            }
        )

    return {
        "generated_at": db.utcnow_iso(),
        "themes": sorted(themes),
        "companies": sorted(companies),
        "testate": sorted(testate),
        "stories": stories,
    }


def export_json(
    conn: sqlite3.Connection, min_relevance: float, out_path: str, since_days=None
) -> int:
    """Write exportable stories to out_path atomically. Returns the story count."""
    payload = build_payload(conn, min_relevance, since_days=since_days)
    _atomic_write(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return len(payload["stories"])


def export_dashboard(
    conn: sqlite3.Connection, min_relevance: float, recent_days: int, out_path: str
) -> dict:
    """Write both the recent feed (out_path) and the full archive (archive.json sibling)."""
    recent = export_json(conn, min_relevance, out_path, since_days=recent_days)
    archive_path = os.path.join(os.path.dirname(out_path) or ".", "archive.json")
    archive = export_json(conn, min_relevance, archive_path, since_days=None)
    return {"recent": recent, "archive": archive}

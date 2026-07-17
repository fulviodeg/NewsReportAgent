"""Scheduler entrypoint: two clocks (collection, processing) plus on-demand trigger.

The runtime is a fixed workflow, not an agent: at runtime no LLM decides which step
runs next. This module reads both cadences from config and drives the fixed sequence
collect -> parse -> dedup/cluster -> classify -> synthesize -> export -> persist.
See docs/v1-architecture.md (Sections 3-5).
"""

from __future__ import annotations

import logging
import sqlite3

from .config import AppConfig, Source
from .ingest.base import IngestSource
from .parse import parse_email
from .store import db

log = logging.getLogger("news_report_agent")


def run_collection(
    conn: sqlite3.Connection, source: IngestSource, sources_cfg: list[Source]
) -> dict:
    """Collection clock: poll the source, parse messages, store items. No LLM.

    Idempotent: content-hash uniqueness means re-running over the same messages adds
    nothing. Only messages from configured senders are accepted.
    """
    run_id = db.start_run(conn, "collection")
    addr_map = {s.from_address.lower(): s for s in sources_cfg}
    since = db.last_run_started_at(conn, "collection")

    messages = items_inserted = unknown = 0
    try:
        for raw in source.fetch_new(since):
            cfg = addr_map.get((raw.from_address or "").lower())
            if not cfg:
                unknown += 1
                continue
            messages += 1
            source_id = db.upsert_source(conn, cfg.name, cfg.from_address)
            for item in parse_email(raw, cfg.parse_hint):
                if db.insert_item(
                    conn,
                    source_id,
                    item.title,
                    item.text,
                    item.link,
                    item.content_hash,
                ):
                    items_inserted += 1
    except Exception:
        counts = {"messages": messages, "items_inserted": items_inserted, "unknown_senders": unknown}
        db.finish_run(conn, run_id, counts, 0.0, "error")
        raise

    counts = {"messages": messages, "items_inserted": items_inserted, "unknown_senders": unknown}
    db.finish_run(conn, run_id, counts, 0.0, "ok")
    log.info("collection: %s", counts)
    return counts


def run_processing(conn: sqlite3.Connection, config: AppConfig) -> dict:
    """Processing clock (also the on-demand trigger): dedup/cluster, classify, synthesize, export."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()

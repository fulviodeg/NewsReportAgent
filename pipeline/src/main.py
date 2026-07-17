"""Scheduler entrypoint: two clocks (collection, processing) plus on-demand trigger.

The runtime is a fixed workflow, not an agent: at runtime no LLM decides which step
runs next. This module reads both cadences from config and drives the fixed sequence
collect -> parse -> dedup/cluster -> classify -> synthesize -> export -> persist.
See docs/v1-architecture.md (Sections 3-5).
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from typing import Callable, Optional

from .classify import classify_cluster
from .cluster import cluster_items
from .config import AppConfig, Source, load_config, load_secrets
from .embeddings import EmbeddingsProvider, OpenAICompatibleEmbeddings
from .export import export_json
from .ingest.base import IngestSource
from .ingest.imap_source import ImapSource
from .llm import (
    CostCapExceeded,
    CostTracker,
    ItemProcessingError,
    LLMClient,
    LLMError,
)
from .parse import parse_email
from .store import db
from .synthesize import synthesize_cluster

log = logging.getLogger("news_report_agent")


class _RunAborted(Exception):
    """Circuit breaker tripped: too many consecutive failures."""


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


def run_processing(
    conn: sqlite3.Connection,
    config: AppConfig,
    provider: EmbeddingsProvider,
    llm: LLMClient,
    out_path: str,
) -> dict:
    """Processing clock (also the on-demand trigger): cluster, classify, synthesize, export.

    Per-item isolation: one cluster's failure is logged and skipped; the run continues.
    A run-level circuit breaker aborts after too many consecutive failures. The cost cap
    stops the run and records an alert. Export always runs so the dashboard reflects
    whatever was completed. Idempotent: only unclassified/unsynthesized clusters are touched.
    """
    run_id = db.start_run(conn, "processing")
    tracker = CostTracker(db.todays_cost(conn), config.cost.daily_usd_cap)
    counts = {
        "new_clusters": 0,
        "joined": 0,
        "embedded": 0,
        "classified": 0,
        "classify_skipped": 0,
        "synthesized": 0,
        "synthesize_skipped": 0,
        "exported": 0,
    }
    outcome = "ok"
    consecutive = 0
    max_consecutive = config.llm.max_consecutive_failures

    try:
        stats = cluster_items(
            conn,
            provider,
            config.clustering.similarity_threshold,
            config.clustering.window_hours,
            config.embeddings.model,
        )
        for key in ("new_clusters", "joined", "embedded"):
            counts[key] = stats[key]

        for cluster in db.clusters_needing_classification(conn):
            members = db.get_items_by_ids(conn, json.loads(cluster["member_ids"]))
            try:
                result = classify_cluster(
                    llm, tracker, config.llm.model_classify, members, config.classify.themes
                )
            except (ItemProcessingError, LLMError) as exc:
                log.warning("classify skipped cluster %s: %s", cluster["id"], exc)
                counts["classify_skipped"] += 1
                consecutive += 1
                if consecutive >= max_consecutive:
                    raise _RunAborted("too many consecutive classify failures")
                continue
            db.set_classification(
                conn, cluster["id"], result.theme, result.companies, result.relevance
            )
            counts["classified"] += 1
            consecutive = 0

        for cluster in db.clusters_needing_synthesis(conn):
            members = db.get_items_by_ids(conn, json.loads(cluster["member_ids"]))
            try:
                result = synthesize_cluster(
                    llm, tracker, config.llm.model_synthesize, members
                )
            except (ItemProcessingError, LLMError) as exc:
                log.warning("synthesize skipped cluster %s: %s", cluster["id"], exc)
                counts["synthesize_skipped"] += 1
                consecutive += 1
                if consecutive >= max_consecutive:
                    raise _RunAborted("too many consecutive synthesize failures")
                continue
            db.set_synthesis(conn, cluster["id"], result.summary_it)
            counts["synthesized"] += 1
            consecutive = 0

    except CostCapExceeded as exc:
        outcome = "cost_cap_hit"
        log.error("COST CAP ALERT: %s", exc)
    except _RunAborted as exc:
        outcome = "error"
        log.error("run aborted: %s", exc)

    try:
        counts["exported"] = export_json(conn, config.filters.min_relevance, out_path)
    except Exception as exc:  # export must never crash the run record
        log.error("export failed: %s", exc)

    db.finish_run(conn, run_id, counts, tracker.run_cost, outcome)
    log.info("processing: %s", counts)
    return counts


def run_scheduler(
    collection_task: Callable[[], None],
    processing_task: Callable[[], None],
    coll_interval_s: float,
    proc_interval_s: float,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Optional[Callable[[float], object]] = None,
    should_continue: Optional[Callable[[], bool]] = None,
    tick: float = 5.0,
) -> None:
    """Two-clock scheduler: a single-thread tick loop, no external dependency.

    Both clocks run in one thread so SQLite writes stay serialized. Injectable
    monotonic/wait/should_continue make it testable without real sleeping.
    """
    if wait is None:
        wait = time.sleep
    if should_continue is None:
        should_continue = lambda: True  # noqa: E731

    next_coll = monotonic()
    next_proc = monotonic()
    while should_continue():
        now = monotonic()
        if now >= next_coll:
            collection_task()
            next_coll = now + coll_interval_s
        if now >= next_proc:
            processing_task()
            next_proc = now + proc_interval_s
        wait(tick)


def _build_context(config: AppConfig, secrets, data_dir: str):
    conn = db.connect(os.path.join(data_dir, "news.db"))
    db.init_schema(conn)
    provider = OpenAICompatibleEmbeddings(
        config.embeddings.endpoint,
        config.embeddings.model,
        secrets.embeddings_api_key or "",
        batch_size=config.embeddings.batch_size,
    )
    llm = LLMClient(
        config.llm.endpoint,
        secrets.openrouter_api_key,
        max_retries=config.llm.max_retries,
        backoff_base=config.llm.backoff_base_seconds,
    )
    source = ImapSource(
        secrets.imap_host, secrets.imap_port, secrets.imap_username, secrets.imap_password
    )
    out_path = os.path.join(data_dir, "export.json")
    return conn, source, provider, llm, out_path


def main(argv: Optional[list] = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "schedule"

    config = load_config(os.environ.get("CONFIG_PATH", "config.toml"))
    secrets = load_secrets()
    data_dir = os.environ.get("DATA_DIR", "/data")
    conn, source, provider, llm, out_path = _build_context(config, secrets, data_dir)

    if command == "run-collection":
        run_collection(conn, source, config.sources)
    elif command == "run-processing":
        run_processing(conn, config, provider, llm, out_path)
    elif command == "schedule":
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_a: stop.set())

        def collection_task() -> None:
            try:
                run_collection(conn, source, config.sources)
            except Exception:
                log.exception("collection run failed")

        def processing_task() -> None:
            try:
                run_processing(conn, config, provider, llm, out_path)
            except Exception:
                log.exception("processing run failed")

        log.info("scheduler starting (collection %sm, processing %sm)",
                 config.cadence.collection_interval_minutes,
                 config.cadence.processing_interval_minutes)
        run_scheduler(
            collection_task,
            processing_task,
            config.cadence.collection_interval_minutes * 60,
            config.cadence.processing_interval_minutes * 60,
            wait=stop.wait,
            should_continue=lambda: not stop.is_set(),
        )
        log.info("scheduler stopped")
    else:
        print("usage: python -m src.main [schedule|run-collection|run-processing]")
        sys.exit(2)


if __name__ == "__main__":
    main()

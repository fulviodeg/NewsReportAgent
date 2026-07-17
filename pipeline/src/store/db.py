"""SQLite access. The store is the single source of truth across all runs.

Applies schema.sql on first use and exposes read/write helpers for the four tables.
Reruns are safe (idempotency via content hash + embedding similarity).
See docs/v1-architecture.md (Sections 2 and 4.7).
"""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str) -> sqlite3.Connection:
    raise NotImplementedError


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql (idempotent: CREATE TABLE IF NOT EXISTS)."""
    raise NotImplementedError

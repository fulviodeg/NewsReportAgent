-- News Report Agent — SQLite schema (single source of truth).
-- See docs/v1-architecture.md (Section 4.7). Columns are a starting point for v1.

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,          -- display name (testata)
    from_address TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    title         TEXT,
    text          TEXT,
    link          TEXT,
    content_hash  TEXT UNIQUE,           -- cross-run dedup
    embedding_ref TEXT,                  -- reference to the stored embedding
    collected_at  TEXT NOT NULL          -- ISO-8601 timestamp
);

CREATE TABLE IF NOT EXISTS clusters (
    id            INTEGER PRIMARY KEY,
    member_ids    TEXT,                  -- JSON array of item ids
    theme         TEXT,
    companies     TEXT,                  -- JSON array
    relevance     REAL,
    summary_it    TEXT,                  -- Italian synthesis
    processed_at  TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,            -- 'collection' | 'processing'
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    counts     TEXT,                     -- JSON summary of what was processed
    cost_usd   REAL,
    outcome    TEXT                      -- 'ok' | 'error' | 'cost_cap_hit' | ...
);

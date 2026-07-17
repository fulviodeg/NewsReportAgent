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

-- Persisted embedding vectors so re-runs never re-embed (cost + idempotency).
CREATE TABLE IF NOT EXISTS embeddings (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    model   TEXT NOT NULL,
    vector  TEXT NOT NULL          -- JSON array of floats (unit-normalized)
);

CREATE TABLE IF NOT EXISTS clusters (
    id            INTEGER PRIMARY KEY,
    member_ids    TEXT,                  -- JSON array of item ids
    theme         TEXT,
    companies     TEXT,                  -- JSON array
    relevance     REAL,
    title         TEXT,                  -- Italian headline (synthesis)
    subtitle      TEXT,                  -- Italian standfirst (synthesis)
    summary_it    TEXT,                  -- Italian short description
    summary_long  TEXT,                  -- Italian deeper description ("View more")
    entities      TEXT,                  -- JSON array of proper nouns to highlight
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

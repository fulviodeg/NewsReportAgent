# News Report Agent

Ingests news from newsletters (IMAP), classifies and synthesizes each story with an LLM,
and publishes a filterable, password-protected static dashboard.

**Status:** light scaffold. Directory structure, config, and the two swap interfaces
(`IngestSource`, embeddings) are in place; the pipeline logic is stubbed (`NotImplementedError`).

## Documentation

- **Architecture & Definition of Done:** [docs/v1-architecture.md](docs/v1-architecture.md)
- **Build task & locked/open decisions:** [docs/build-prompt.md](docs/build-prompt.md)
- **Coding-agent rules:** [CLAUDE.md](CLAUDE.md)

## Layout

```
pipeline/            Python service (collect → parse → cluster → classify → synthesize → export)
  config.toml        cadences, sources, model-per-task, thresholds (no secrets)
  src/               pipeline modules (see docs/v1-architecture.md §10)
web/                 static dashboard served by nginx + HTTP basic auth
data/                shared runtime volume (SQLite + export.json) — gitignored
docker-compose.yml   two services: pipeline + web
```

## Setup

1. `cp .env.example .env` and fill in the values (never commit `.env`).
2. Pick the open decisions in [docs/build-prompt.md](docs/build-prompt.md): OpenRouter model,
   embeddings approach, config format.
3. Implement the stubs, then `docker compose up`.

## Note on restricted networks

OpenRouter (the LLM provider) may be unreachable from corporate/restricted networks.
The LLM lives behind `pipeline/src/llm.py`; for offline development a fake client can be
swapped in behind the same code path so the deterministic stages can be tested without
network access.

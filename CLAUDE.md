# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Orientation

v1 is implemented (51 tests pass offline). Read [docs/v1-architecture.md](docs/v1-architecture.md) before any significant change — it's the full spec and Definition of Done (§9). Locked build decisions are in [docs/build-prompt.md](docs/build-prompt.md).

## Commands

```bash
# Setup
python -m venv .venv && . .venv/bin/activate
pip install -r pipeline/requirements.txt tomli   # tomli only for Python < 3.11

# Tests (all offline — no network, no keys)
cd pipeline && python -m pytest                  # all 51 tests
cd pipeline && python -m pytest tests/test_classify.py
cd pipeline && python -m pytest tests/test_cluster.py::test_single_item_creates_cluster

# Local demo
cd pipeline && python local_demo.py              # offline (fake LLM/embeddings)
cd pipeline && python local_demo.py --real       # real APIs (needs .env)

# Pipeline (single-shot)
cd pipeline && python -m src.main run-collection
cd pipeline && python -m src.main run-processing

# Docker
docker compose up -d --build
docker compose exec pipeline python -m src.main run-processing

# Architecture docs
npm install && npm run docs:serve                # live preview
npm run docs:mermaid                             # regenerate docs/diagrams.md
```

## Architecture

Three independent parts communicating only through SQLite + exported JSON:

1. **Collection** (frequent, no LLM): IMAP poll → parse → store items
2. **Processing** (configurable, paid): cluster (embeddings) → classify (LLM) → synthesize in Italian (LLM) → export JSON
3. **Dashboard** (static): nginx + HTTP basic auth, client-side filtering in `app.js`

The runtime is a **fixed workflow, not an agent**. No LLM decides which step runs next. The sequence is coded in `main.py`; triggers are two configurable clocks or a manual command. The LLM is used only in `classify.py` and `synthesize.py`.

### Key files

| File | Role |
|------|------|
| `pipeline/src/main.py` | Scheduler: two clocks + on-demand trigger |
| `pipeline/src/config.py` | `config.toml` → Pydantic models + secrets from env |
| `pipeline/src/ingest/base.py` | `IngestSource` interface (swap for RSS/webhook later) |
| `pipeline/src/ingest/imap_source.py` | IMAP implementation |
| `pipeline/src/parse.py` | Email → items (BeautifulSoup HTML + text fallback) |
| `pipeline/src/cluster.py` | Greedy single-linkage by cosine similarity |
| `pipeline/src/embeddings.py` | `EmbeddingsProvider` interface + OpenAI-compatible impl |
| `pipeline/src/llm.py` | OpenRouter client: retry/backoff, cost tracking, JSON extraction |
| `pipeline/src/classify.py` | LLM: theme + companies + relevance (Pydantic-validated) |
| `pipeline/src/synthesize.py` | LLM: Italian summary + source links (Pydantic-validated) |
| `pipeline/src/models.py` | `Classification` and `Synthesis` schemas |
| `pipeline/src/export.py` | Atomic JSON export (recent + archive) |
| `pipeline/src/store/db.py` | SQLite: items, clusters, embeddings, runs |
| `pipeline/src/store/schema.sql` | Five tables: sources, items, embeddings, clusters, runs |
| `pipeline/local_demo.py` | End-to-end demo with fake/real LLM, reads `.eml` files |
| `web/site/app.js` | Client-side dashboard: filter, search, theme tabs, pagination |
| `web/nginx.conf` | Static serving + basic auth + export.json aliases |

### Data flow

```
IMAP → IngestSource.fetch_new() → parse_email() → items
  → cluster_items() (embeddings + cosine) → clusters
  → classify_cluster() (LLM) → theme/companies/relevance
  → synthesize_cluster() (LLM) → Italian title/summary
  → export_dashboard() → export.json + archive.json
  → nginx → app.js in browser
```

## Project rules

- **Plain Python, no agent framework.** Pydantic for structured LLM output. SQLite as single source of truth.
- **Config-driven:** newsletters, cadences, model, thresholds, themes in `pipeline/config.toml`. Secrets in `.env` (gitignored).
- **Model name is a config value** — never hardcode it. `model_classify` and `model_synthesize` are separate keys so they can diverge later.
- **Guardrails:** per-item isolation (one cluster fails → logged + skipped, run continues), retry with exponential backoff, circuit breaker (`max_consecutive_failures`), daily cost cap, idempotent reruns (content-hash uniqueness + embedding persistence), atomic export.
- **Code & comments:** English. **News output:** Italian, technical terms in English, preserve source links.
- **Architecture docs:** source of truth is `docs/architecture/*.c4` (LikeC4). After changing architecture, run `npm run docs:mermaid` and commit the regenerated `docs/diagrams.md`. CI enforces this.
- **Evolution hooks** (do not remove): `IngestSource` interface, `EmbeddingsProvider` interface, separate model keys in config.

## Behavioral rules

1. **Think before coding.** State assumptions. If uncertain, ask. If multiple interpretations exist, present them.
2. **Simplicity first.** Minimum code that solves the problem. No speculative features, no abstractions for single-use code.
3. **Surgical changes.** Touch only what the task requires. Match existing style. Remove only imports/variables your change made unused.
4. **Goal-driven execution.** Turn tasks into verifiable goals. The v1 Definition of Done in `docs/v1-architecture.md` §9 is the top-level success criteria.
5. **Debugging.** Reproduce with a failing test first. Diagnose cause before fixing. Keep the test.
6. **Don't touch what you don't understand.** Ask or leave it alone.
7. **Dependency hygiene.** Prefer stdlib and existing deps. Add a new dependency only when it clearly earns its place.
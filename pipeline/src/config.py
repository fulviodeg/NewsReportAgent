"""Load and validate config.toml. Secrets come from the environment, never from here.

Config (non-secret) is validated into a typed Pydantic AppConfig. Secrets (API keys,
mailbox credentials) are read separately from environment variables into Secrets.
See docs/v1-architecture.md (Section 6).
"""

from __future__ import annotations

import os
from typing import Optional

try:
    import tomllib  # Python 3.11+ (the container uses this)
except ModuleNotFoundError:  # pragma: no cover - dev fallback on Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef]

from pydantic import BaseModel


class Cadence(BaseModel):
    collection_interval_minutes: int
    processing_interval_minutes: int


class Llm(BaseModel):
    provider: str
    endpoint: str
    model_classify: str
    model_synthesize: str
    max_retries: int = 4
    backoff_base_seconds: float = 1.0
    max_consecutive_failures: int = 5


class Embeddings(BaseModel):
    provider: str
    model: str
    endpoint: str
    batch_size: int = 8


class Clustering(BaseModel):
    similarity_threshold: float
    window_hours: int


class Filters(BaseModel):
    min_relevance: float


class Cost(BaseModel):
    daily_usd_cap: float


class Classify(BaseModel):
    themes: list[str]


class Dashboard(BaseModel):
    refresh_seconds: int = 60


class Source(BaseModel):
    name: str
    from_address: str
    parse_hint: Optional[str] = None


class AppConfig(BaseModel):
    cadence: Cadence
    llm: Llm
    embeddings: Embeddings
    clustering: Clustering
    filters: Filters
    cost: Cost
    classify: Classify
    dashboard: Dashboard = Dashboard()
    sources: list[Source] = []


class Secrets(BaseModel):
    """Secrets read from the environment. Never stored in config.toml."""

    openrouter_api_key: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    embeddings_api_key: Optional[str] = None


def load_config(path: str = "config.toml") -> AppConfig:
    """Read and validate the TOML config into a typed AppConfig."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return AppConfig.model_validate(raw)


def load_secrets(env: Optional[dict] = None) -> Secrets:
    """Read secrets from environment variables (see .env.example)."""
    env = os.environ if env is None else env
    return Secrets(
        openrouter_api_key=env.get("OPENROUTER_API_KEY", ""),
        imap_host=env.get("IMAP_HOST", ""),
        imap_port=int(env.get("IMAP_PORT", "993")),
        imap_username=env.get("IMAP_USERNAME", ""),
        imap_password=env.get("IMAP_PASSWORD", ""),
        embeddings_api_key=env.get("EMBEDDINGS_API_KEY") or None,
    )

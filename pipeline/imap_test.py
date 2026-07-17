"""IMAP diagnostic + real-email ingest test. Run from the pipeline/ directory.

Reads IMAP credentials from ../.env, connects to the mailbox, and shows recent messages
and how the parser splits them into items. Read-only by default (safe). With --ingest it
runs the full real pipeline (cluster + classify + synthesize via OpenRouter) over the
fetched messages and writes web/site/export.json for the dashboard.

    python imap_test.py                 # diagnostic only (read-only), last 7 days
    python imap_test.py --days 3 --max 10
    python imap_test.py --ingest        # also run the pipeline over the real emails

Security: put IMAP_HOST/PORT/USERNAME/PASSWORD in ../.env (never in chat). Gmail/Outlook
usually need an app-specific password with IMAP enabled.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import Source, load_config, load_secrets
from src.embeddings import OpenAICompatibleEmbeddings
from src.ingest.imap_source import ImapSource
from src.llm import LLMClient
from src.main import run_collection, run_processing
from src.parse import parse_email
from src.store import db

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "data" / "imap_test.db"
EXPORT_PATH = REPO / "web" / "site" / "export.json"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="look back this many days")
    parser.add_argument("--max", type=int, default=20, help="cap messages processed")
    parser.add_argument("--ingest", action="store_true", help="run the full pipeline")
    parser.add_argument(
        "--senders", default="", help="comma-separated from-addresses to keep (default: all)"
    )
    args = parser.parse_args()
    keep = {s.strip().lower() for s in args.senders.split(",") if s.strip()}

    _load_dotenv(REPO / ".env")
    secrets = load_secrets()
    if not secrets.imap_host or not secrets.imap_username:
        raise SystemExit("IMAP_HOST / IMAP_USERNAME missing in ../.env")

    config = load_config(str(REPO / "pipeline" / "config.toml"))
    cfg_by_addr = {s.from_address.lower(): s for s in config.sources}

    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    source = ImapSource(secrets.imap_host, secrets.imap_port, secrets.imap_username, secrets.imap_password)

    print(f"Connecting to {secrets.imap_host} as {secrets.imap_username} (since {since[:10]})…")
    messages = []
    for raw in source.fetch_new(since):
        if keep and (raw.from_address or "").lower() not in keep:
            continue
        messages.append(raw)
        if len(messages) >= args.max:
            break

    print(f"\nFetched {len(messages)} message(s):\n")
    senders = {}
    for raw in messages:
        cfg = cfg_by_addr.get((raw.from_address or "").lower())
        hint = cfg.parse_hint if cfg else None
        items = parse_email(raw, hint)
        senders.setdefault(raw.from_address, raw.from_name or raw.from_address)
        marker = f" (hint: {hint})" if hint else ""
        print(f"- {raw.from_address}{marker} | {raw.subject[:55]!r} -> {len(items)} item(s)")
        for it in items[:3]:
            print(f"      · {it.title[:70]!r}  {it.link[:60]}")

    if not args.ingest:
        print("\n(diagnostic only — pass --ingest to run the full pipeline)")
        return

    # Ingest: use the configured source (name + parse_hint) when known, else accept as-is.
    sources_cfg = [
        cfg_by_addr.get(addr.lower()) or Source(name=name, from_address=addr)
        for addr, name in senders.items()
    ]

    class _Fixed(ImapSource):
        def fetch_new(self, since=None):
            return list(messages)

    provider = OpenAICompatibleEmbeddings(
        config.embeddings.endpoint,
        config.embeddings.model,
        secrets.embeddings_api_key or "",
        batch_size=config.embeddings.batch_size,
    )
    llm = LLMClient(
        config.llm.endpoint, secrets.openrouter_api_key,
        max_retries=config.llm.max_retries, backoff_base=config.llm.backoff_base_seconds,
    )
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(str(DB_PATH))
    db.init_schema(conn)

    print("\ningest:", run_collection(conn, _Fixed(secrets.imap_host, secrets.imap_port,
          secrets.imap_username, secrets.imap_password), sources_cfg))
    print("processing:", run_processing(conn, config, provider, llm, str(EXPORT_PATH)))
    print(f"\nWrote {EXPORT_PATH.relative_to(REPO)} — serve web/site to view.")


if __name__ == "__main__":
    main()

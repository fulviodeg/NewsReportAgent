"""Local end-to-end demo runner — no VPS, no Docker, no mailbox needed.

Ingests sample newsletter .eml files, runs the real pipeline (collect -> parse -> cluster ->
classify -> synthesize -> export) and writes web/site/export.json so you can open the
dashboard locally.

Default is OFFLINE: deterministic fake embeddings + a templated fake LLM, so you can play
with the flow and the dashboard without any API key or network. Pass --real to use the
actual OpenRouter + embeddings APIs from config.toml / .env.

Run from the pipeline/ directory:
    python local_demo.py            # offline demo (no keys, no network)
    python local_demo.py --real     # real APIs (needs keys in ../.env and network)

Then serve the dashboard:
    cd ../web/site && python -m http.server 8000
    # open http://localhost:8000
"""

from __future__ import annotations

import email
import hashlib
import os
import re
import sys
from email.policy import default as default_policy
from email.utils import parseaddr
from pathlib import Path

from src.config import Source, load_config, load_secrets
from src.embeddings import EmbeddingsProvider, OpenAICompatibleEmbeddings
from src.ingest.base import IngestSource, RawMessage
from src.llm import LLMClient, LLMResult
from src.main import run_collection, run_processing
from src.store import db

REPO = Path(__file__).resolve().parents[1]
NEWSLETTERS = REPO / "demo" / "newsletters"
DB_PATH = REPO / "data" / "demo.db"
EXPORT_PATH = REPO / "web" / "site" / "export.json"

# Senders of the sample emails, used as the accepted source list for the demo.
DEMO_SOURCES = [
    Source(name="Tech Daily", from_address="news@techdaily.com"),
    Source(name="Innovation Weekly", from_address="news@innovation.com"),
    Source(name="Fin News", from_address="news@finnews.com"),
]

_THEME_KEYWORDS = {
    "AI": ["ai", "chip", "processor", "model", "openai", "machine learning", "neural"],
    "Fintech": ["payment", "bank", "ecb", "rate", "inflation", "fintech"],
    "Startup": ["startup", "seed", "funding", "round"],
}


class EmlFolderSource(IngestSource):
    """Reads *.eml files from a folder — a drop-in IngestSource for local testing."""

    def __init__(self, folder: Path):
        self.folder = folder

    def fetch_new(self, since=None):
        for path in sorted(self.folder.glob("*.eml")):
            msg = email.message_from_bytes(path.read_bytes(), policy=default_policy)
            name, addr = parseaddr(msg["From"] or "")
            yield RawMessage(
                from_address=addr,
                from_name=name,
                subject=str(msg["Subject"] or ""),
                date="",
                message_id=str(msg["Message-ID"] or path.name),
                message=msg,
            )


class DemoEmbeddings(EmbeddingsProvider):
    """Deterministic hashing bag-of-words vectors — similar texts get similar vectors."""

    DIM = 64

    def embed(self, texts):
        out = []
        for text in texts:
            vec = [0.0] * self.DIM
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.DIM] += 1.0
            out.append(vec)
        return out


class DemoLLM:
    """Templated offline stand-in for the real OpenRouter client (valid JSON output)."""

    def complete(self, model, messages, response_json=True):
        content = messages[1]["content"]
        if "classifier" in messages[0]["content"]:
            theme = self._guess_theme(content)
            return LLMResult(
                f'{{"theme": "{theme}", "companies": {self._companies(content)}, '
                f'"relevance": 0.7}}',
                0.0,
            )
        links = re.findall(r"https?://[^\s\]\"',)]+", content)
        links_json = "[" + ", ".join(f'"{l}"' for l in dict.fromkeys(links)) + "]"
        headline = self._headline(content)
        return LLMResult(
            f'{{"title": "{headline[:70]}", '
            f'"subtitle": "[demo] sottotitolo di contesto", '
            f'"summary_it": "[demo] Sintesi in italiano: {headline}", '
            f'"summary_long": "[demo] Approfondimento: {headline}. '
            f'Dettagli aggiuntivi e contesto della notizia.", '
            f'"source_links": {links_json}}}',
            0.0,
        )

    @staticmethod
    def _guess_theme(text):
        # scan only the story text (after the prompt's "Story items:" / "notizia:" marker)
        # with word-boundary matching, so the themes list in the prompt can't false-match.
        marker = "Elementi della notizia:" if "Elementi della notizia:" in text else "Story items:"
        part = text.split(marker)[-1].lower()
        for theme, words in _THEME_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(w)}\b", part) for w in words):
                return theme
        return "Other"

    @staticmethod
    def _companies(text):
        found = []
        for name in ["Apple", "OpenAI", "ECB"]:
            if name.lower() in text.lower():
                found.append(name)
        return "[" + ", ".join(f'"{c}"' for c in found) + "]"

    @staticmethod
    def _headline(text):
        first = next((l for l in text.splitlines() if l.strip().startswith("- ")), "")
        first = re.sub(r"\s+", " ", first).strip("- ").strip()
        # drop the trailing "(url)" if present
        first = re.sub(r"\s*\(https?://[^)]+\)\s*$", "", first)
        return first.replace('"', "'")[:180] or "Notizia"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    real = "--real" in sys.argv[1:]
    config = load_config(str(REPO / "pipeline" / "config.toml"))

    if real:
        _load_dotenv(REPO / ".env")
        secrets = load_secrets()
        llm = LLMClient(
            config.llm.endpoint,
            secrets.openrouter_api_key,
            max_retries=config.llm.max_retries,
            backoff_base=config.llm.backoff_base_seconds,
        )
        # OpenRouter serves chat completions only; use a real embeddings API when a key is
        # present, otherwise fall back to the deterministic demo embeddings for clustering.
        if secrets.embeddings_api_key:
            provider = OpenAICompatibleEmbeddings(
                config.embeddings.endpoint,
                config.embeddings.model,
                secrets.embeddings_api_key,
                batch_size=config.embeddings.batch_size,
            )
            print(f"REAL mode: LLM={config.llm.model_synthesize}, embeddings={config.embeddings.model}")
        else:
            provider = DemoEmbeddings()
            config.clustering.similarity_threshold = 0.6
            print(
                f"REAL mode: LLM={config.llm.model_synthesize} (real), "
                "embeddings=demo fallback (no EMBEDDINGS_API_KEY set)"
            )
    else:
        provider = DemoEmbeddings()
        llm = DemoLLM()
        config.clustering.similarity_threshold = 0.6  # tuned for the demo embeddings
        print("Running in OFFLINE demo mode (fake embeddings + fake LLM). Use --real for real APIs.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(str(DB_PATH))
    db.init_schema(conn)

    collected = run_collection(conn, EmlFolderSource(NEWSLETTERS), DEMO_SOURCES)
    print("collection:", collected)
    processed = run_processing(conn, config, provider, llm, str(EXPORT_PATH))
    print("processing:", processed)
    print(f"\nWrote {EXPORT_PATH.relative_to(REPO)}")
    print("Now serve the dashboard:")
    print("    cd ../web/site && python -m http.server 8000")
    print("    open http://localhost:8000")


if __name__ == "__main__":
    main()

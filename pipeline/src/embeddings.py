"""Embeddings provider interface + a generic OpenAI-compatible implementation.

Kept separate from the brain LLM (llm.py). v1 uses a hosted API model (VPS is small);
provider, model and endpoint are config values so the vendor can be swapped without code
changes. See docs/v1-architecture.md (Section 7).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Optional

import httpx


class EmbeddingsProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise NotImplementedError


def unit_normalize(vec: list[float]) -> list[float]:
    """Scale a vector to unit length so cosine similarity is a plain dot product."""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class OpenAICompatibleEmbeddings(EmbeddingsProvider):
    """Calls any OpenAI-compatible /embeddings endpoint (OpenAI, Cohere-compat, etc.)."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str,
        client: Optional[httpx.Client] = None,
        timeout: float = 30.0,
        batch_size: int = 8,
    ):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self._client = client
        self._timeout = timeout
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size]))
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": texts}
        if self._client is not None:
            resp = self._client.post(self.endpoint, headers=headers, json=payload)
        else:
            resp = httpx.post(
                self.endpoint, headers=headers, json=payload, timeout=self._timeout
            )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]

"""Embeddings provider interface — the swap point for clustering embeddings.

Kept separate from the brain LLM (llm.py). v1 chooses between a hosted multilingual
model and a local sentence-transformers model (open decision, docs/build-prompt.md);
either fits behind this interface. See docs/v1-architecture.md (Section 7).
"""

from abc import ABC, abstractmethod


class EmbeddingsProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise NotImplementedError

"""Dedup and cluster items into stories. Deterministic + embeddings.

Groups items whose embeddings are highly similar within a bounded time window; a cluster
is one story and its members are the sources reporting it. Cross-run dedup uses a stable
content hash plus embedding similarity. Threshold and window come from config.
See docs/v1-architecture.md (Section 4.3).
"""


def cluster_items(items, provider, similarity_threshold: float, window_hours: int):
    raise NotImplementedError

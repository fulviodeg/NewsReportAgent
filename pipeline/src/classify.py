"""Classify step (LLM). One call per cluster: theme, companies, relevance score.

Output is validated against a Pydantic model; a malformed response is retried a bounded
number of times, then that single cluster is logged and skipped. Per-item isolation: one
failure never breaks the run. See docs/v1-architecture.md (Section 4.4).
"""


def classify_cluster(cluster, model: str):
    raise NotImplementedError

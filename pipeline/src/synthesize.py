"""Synthesize step (LLM). One call per cluster: Italian summary.

Technical terms stay in English; source links are preserved. Output is validated against a
Pydantic model requiring the summary text and at least one source link. Same per-item
isolation and retry discipline as classify. See docs/v1-architecture.md (Section 4.5).
"""


def synthesize_cluster(cluster, model: str):
    raise NotImplementedError

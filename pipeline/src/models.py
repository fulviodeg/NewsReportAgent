"""Pydantic schemas for structured, validated LLM output and internal data.

Both LLM steps return data validated against these models; a response that fails
validation is retried a bounded number of times, then logged and skipped.
See docs/v1-architecture.md (Sections 4 and 7).
"""

# TODO: define Item, Cluster, Classification (theme, companies, relevance),
# and Synthesis (italian summary + preserved source links) models.

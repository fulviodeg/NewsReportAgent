"""Pydantic schemas for structured, validated LLM output.

Both LLM steps return data validated against these models; a response that fails
validation is retried a bounded number of times, then the cluster is logged and skipped.
See docs/v1-architecture.md (Sections 4 and 7).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Classification(BaseModel):
    theme: str
    companies: list[str] = Field(default_factory=list)
    relevance: float = Field(ge=0.0, le=1.0)


class Synthesis(BaseModel):
    title: str = Field(min_length=1)          # concise Italian headline
    subtitle: str = Field(min_length=1)       # one-line Italian standfirst
    summary_it: str = Field(min_length=1)     # short description ("Espandi")
    summary_long: str = Field(min_length=1)   # deeper description ("View more")
    entities: list[str] = Field(default_factory=list)  # proper nouns to highlight
    source_links: list[str] = Field(min_length=1)  # at least one preserved link

    @field_validator("source_links")
    @classmethod
    def _links_are_http(cls, v: list[str]) -> list[str]:
        cleaned = [s for s in v if s.startswith("http://") or s.startswith("https://")]
        if not cleaned:
            raise ValueError("at least one valid http(s) source link is required")
        return cleaned

"""Classify step (LLM). One call per cluster: theme, companies, relevance score.

Output is validated against the Classification schema; the theme must be one of the
configured themes. Invalid output is retried a bounded number of times, then the cluster is
skipped (raised as ItemProcessingError for the caller to isolate). The CostTracker is
checked before each call so the daily cap can stop the run.
See docs/v1-architecture.md (Section 4.4).
"""

from __future__ import annotations

import sqlite3

from pydantic import ValidationError

from .llm import CostTracker, ItemProcessingError, LLMClient, extract_json
from .models import Classification

_SYSTEM = "You are a precise news classifier. Respond ONLY with a single JSON object."


def _messages(members: list[sqlite3.Row], themes: list[str]) -> list[dict]:
    stories = "\n".join(
        f"- {m['title']}: {(m['text'] or '')[:500]} ({m['link']})" for m in members
    )
    user = (
        "Classify the following news story into exactly one theme from this list:\n"
        f"{themes}\n"
        "Also list the company names mentioned and give a relevance score from 0 to 1.\n"
        'Return JSON of the form: {"theme": "<one theme from the list>", '
        '"companies": ["..."], "relevance": 0.0}.\n\n'
        f"Story items:\n{stories}"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def classify_cluster(
    llm: LLMClient,
    tracker: CostTracker,
    model: str,
    members: list[sqlite3.Row],
    allowed_themes: list[str],
    max_validation_retries: int = 2,
) -> Classification:
    messages = _messages(members, allowed_themes)
    last_err: Exception = ItemProcessingError("no attempt made")
    for _ in range(max_validation_retries + 1):
        tracker.check()  # raises CostCapExceeded -> stops the run
        res = llm.complete(model, messages)
        tracker.add(res.cost)
        try:
            parsed = Classification.model_validate_json(extract_json(res.content))
        except ValidationError as exc:
            last_err = exc
            continue
        if parsed.theme not in allowed_themes:
            last_err = ValueError(f"theme {parsed.theme!r} not in configured themes")
            continue
        return parsed
    raise ItemProcessingError(f"invalid classification after retries: {last_err}")

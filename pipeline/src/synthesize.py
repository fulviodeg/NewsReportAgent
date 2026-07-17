"""Synthesize step (LLM). One call per cluster: Italian summary.

Technical terms stay in English; source links are preserved. Output is validated against
the Synthesis schema (non-empty summary + at least one http source link). Same bounded
retry-then-skip and cost-cap discipline as classify. See docs/v1-architecture.md (§4.5).
"""

from __future__ import annotations

import sqlite3

from pydantic import ValidationError

from .llm import CostTracker, ItemProcessingError, LLMClient, extract_json
from .models import Synthesis

_SYSTEM = (
    "Sei un redattore che scrive sintesi di notizie in italiano, "
    "mantenendo i termini tecnici in inglese. Rispondi SOLO con un oggetto JSON."
)


def _messages(members: list[sqlite3.Row]) -> list[dict]:
    stories = "\n".join(
        f"- {m['title']}: {(m['text'] or '')[:800]} ({m['link']})" for m in members
    )
    links = [m["link"] for m in members if m["link"]]
    user = (
        "Scrivi una sintesi in italiano della seguente notizia (i termini tecnici "
        "restano in inglese). Conserva i link alle fonti.\n"
        'Restituisci JSON della forma: {"summary_it": "...", "source_links": ["https://..."]}.\n'
        f"Link delle fonti da conservare: {links}\n\n"
        f"Elementi della notizia:\n{stories}"
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def synthesize_cluster(
    llm: LLMClient,
    tracker: CostTracker,
    model: str,
    members: list[sqlite3.Row],
    max_validation_retries: int = 2,
) -> Synthesis:
    messages = _messages(members)
    last_err: Exception = ItemProcessingError("no attempt made")
    for _ in range(max_validation_retries + 1):
        tracker.check()  # raises CostCapExceeded -> stops the run
        res = llm.complete(model, messages)
        tracker.add(res.cost)
        try:
            return Synthesis.model_validate_json(extract_json(res.content))
        except ValidationError as exc:
            last_err = exc
            continue
    raise ItemProcessingError(f"invalid synthesis after retries: {last_err}")

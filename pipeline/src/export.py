"""Export the ready-to-show stories as a single JSON file. Deterministic.

For each story: Italian summary, theme, companies, sources with links, timestamps.
Written atomically (temp file then rename) so the dashboard never reads a half-written
file. This file is the only thing the dashboard reads. See docs/v1-architecture.md (§4.6).
"""


def export_json(stories, out_path: str) -> None:
    raise NotImplementedError

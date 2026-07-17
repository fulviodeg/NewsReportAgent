"""Scheduler entrypoint: two clocks (collection, processing) plus on-demand trigger.

The runtime is a fixed workflow, not an agent: at runtime no LLM decides which step
runs next. This module reads both cadences from config and drives the fixed sequence
collect -> parse -> dedup/cluster -> classify -> synthesize -> export -> persist.
See docs/v1-architecture.md (Sections 3-5).
"""


def run_collection() -> None:
    """Collection clock: poll mailbox, parse, store. No LLM."""
    raise NotImplementedError


def run_processing() -> None:
    """Processing clock (also the on-demand trigger): dedup/cluster, classify, synthesize, export."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()

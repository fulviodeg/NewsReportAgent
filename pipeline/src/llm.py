"""OpenRouter client: retry/backoff, cost tracking, daily cost cap.

The model id is a config value and is never hardcoded here. Transient errors retry with
exponential backoff; repeated identical failures stop the step. When the running cost for
a run would exceed the daily cap, the run stops and records an alert.
See docs/v1-architecture.md (Sections 7 and 8).

NOTE: OpenRouter may be unreachable from restricted/corporate networks. For offline
development a fake client implementing the same call surface can be swapped in here.
"""


def complete(model: str, prompt: str) -> str:
    """Call the configured model via OpenRouter and return the raw completion."""
    raise NotImplementedError

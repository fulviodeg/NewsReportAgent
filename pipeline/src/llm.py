"""OpenRouter client: retry/backoff, cost tracking, daily cost cap.

The model id is a config value and is never hardcoded here. Transient errors (timeout,
connect, 429/5xx) retry with exponential backoff; a non-transient error fails immediately.
The CostTracker seeds from today's recorded cost and enforces a configurable daily cap.
See docs/v1-architecture.md (Sections 7 and 8).

NOTE: OpenRouter may be unreachable from restricted/corporate networks. Tests drive this
module with httpx.MockTransport, so they run fully offline; real calls happen on the VPS.
Cost is read from the response `usage.cost` when the provider returns it (0.0 otherwise).
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def extract_json(text: str) -> str:
    """Best-effort extraction of a JSON object from an LLM response.

    Real models often wrap JSON in ```json fences or add surrounding prose; strip fences
    and fall back to the first '{' .. last '}' span so validation sees clean JSON.
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start : end + 1]
    return t


class LLMError(Exception):
    """A call failed in a way the caller should treat as this item's failure."""


class CostCapExceeded(Exception):
    """The daily cost cap has been reached; the run must stop."""


class ItemProcessingError(Exception):
    """A single cluster could not be processed (invalid output after retries)."""


class _Transient(Exception):
    def __init__(self, status: int):
        super().__init__(f"transient HTTP {status}")
        self.status = status


@dataclass
class LLMResult:
    content: str
    cost: float
    usage: dict = field(default_factory=dict)


class CostTracker:
    """Accumulates spend for the current run on top of what today already cost."""

    def __init__(self, prior_spent: float, daily_cap: float):
        self.prior = prior_spent
        self.run_cost = 0.0
        self.cap = daily_cap

    @property
    def total(self) -> float:
        return self.prior + self.run_cost

    def check(self) -> None:
        """Raise CostCapExceeded if the cap is already reached (call before each request)."""
        if self.total >= self.cap:
            raise CostCapExceeded(
                f"daily cost cap {self.cap} reached (spent {self.total:.4f})"
            )

    def add(self, cost: float) -> None:
        self.run_cost += cost


class LLMClient:
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        max_retries: int = 4,
        backoff_base: float = 1.0,
        client: Optional[httpx.Client] = None,
        sleep: Optional[Callable[[float], None]] = None,
        timeout: float = 60.0,
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._client = client
        self._sleep = sleep or time.sleep
        self._timeout = timeout

    def _post(self, headers: dict, payload: dict) -> httpx.Response:
        if self._client is not None:
            return self._client.post(self.endpoint, headers=headers, json=payload)
        return httpx.post(
            self.endpoint, headers=headers, json=payload, timeout=self._timeout
        )

    def complete(self, model: str, messages: list[dict], response_json: bool = True) -> LLMResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {"model": model, "messages": messages}
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        attempt = 0
        while True:
            try:
                resp = self._post(headers, payload)
                if resp.status_code in TRANSIENT_STATUS:
                    raise _Transient(resp.status_code)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                cost = float(usage.get("cost", 0.0) or 0.0)
                return LLMResult(content=content, cost=cost, usage=usage)
            except (httpx.TimeoutException, httpx.ConnectError, _Transient) as exc:
                if attempt >= self.max_retries:
                    raise LLMError(f"transient failure after {attempt} retries: {exc}")
                delay = self.backoff_base * (2**attempt) + random.uniform(0, self.backoff_base * 0.1)
                self._sleep(delay)
                attempt += 1
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"non-transient HTTP error: {exc}")

import httpx
import pytest

from src.llm import CostCapExceeded, CostTracker, LLMClient, LLMError


def _client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient(
        "https://openrouter.example/api",
        "sk-test",
        max_retries=4,
        backoff_base=1.0,
        client=http,
        sleep=lambda _s: None,  # instant backoff
    )


def _ok_response(content="{\"ok\": true}", cost=0.002):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
        },
    )


def test_complete_success_returns_content_and_cost():
    llm = _client(lambda req: _ok_response())
    res = llm.complete("some/model", [{"role": "user", "content": "hi"}])
    assert res.content == '{"ok": true}'
    assert res.cost == 0.002


def test_retries_transient_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return _ok_response()

    res = _client(handler).complete("m", [{"role": "user", "content": "x"}])
    assert res.content == '{"ok": true}'
    assert calls["n"] == 3


def test_timeout_then_success():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("timed out", request=req)
        return _ok_response()

    res = _client(handler).complete("m", [{"role": "user", "content": "x"}])
    assert res.content == '{"ok": true}'
    assert calls["n"] == 2


def test_persistent_transient_raises_after_bound():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(LLMError):
        _client(handler).complete("m", [{"role": "user", "content": "x"}])
    assert calls["n"] == 5  # initial try + 4 retries


def test_non_transient_fails_immediately():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    with pytest.raises(LLMError):
        _client(handler).complete("m", [{"role": "user", "content": "x"}])
    assert calls["n"] == 1  # no retries on non-transient errors


def test_cost_tracker_cap():
    t = CostTracker(prior_spent=4.5, daily_cap=5.0)
    t.check()  # 4.5 < 5.0 ok
    t.add(0.4)
    t.check()  # 4.9 < 5.0 ok
    t.add(0.2)  # now 5.1
    with pytest.raises(CostCapExceeded):
        t.check()

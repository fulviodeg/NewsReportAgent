import pytest

from src.classify import classify_cluster
from src.llm import CostCapExceeded, CostTracker, ItemProcessingError, LLMResult

THEMES = ["AI", "Fintech", "Other"]


class QueueLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, model, messages, response_json=True):
        self.calls += 1
        content, cost = self.responses.pop(0)
        return LLMResult(content, cost)


def _members():
    return [{"title": "Apple M5", "text": "body", "link": "https://x/1", "source_name": "A"}]


def test_valid_classification_parses_and_tracks_cost():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"theme":"AI","companies":["Acme"],"relevance":0.8}', 0.001)])
    c = classify_cluster(llm, tracker, "m", _members(), THEMES)
    assert c.theme == "AI"
    assert c.companies == ["Acme"]
    assert c.relevance == 0.8
    assert tracker.run_cost == 0.001


def test_invalid_then_valid_retries():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM(
        [
            ("not json at all", 0.001),
            ('{"theme":"AI","companies":[],"relevance":0.5}', 0.001),
        ]
    )
    c = classify_cluster(llm, tracker, "m", _members(), THEMES)
    assert c.theme == "AI"
    assert llm.calls == 2
    assert abs(tracker.run_cost - 0.002) < 1e-9


def test_always_invalid_raises_after_bound():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([("garbage", 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        classify_cluster(llm, tracker, "m", _members(), THEMES)
    assert llm.calls == 3  # 1 + 2 retries


def test_theme_not_in_config_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"theme":"Sports","companies":[],"relevance":0.9}', 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        classify_cluster(llm, tracker, "m", _members(), THEMES)


def test_relevance_out_of_range_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"theme":"AI","companies":[],"relevance":1.9}', 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        classify_cluster(llm, tracker, "m", _members(), THEMES)


def test_cost_cap_blocks_before_calling():
    tracker = CostTracker(prior_spent=5.0, daily_cap=5.0)
    llm = QueueLLM([('{"theme":"AI","companies":[],"relevance":0.5}', 0.001)])
    with pytest.raises(CostCapExceeded):
        classify_cluster(llm, tracker, "m", _members(), THEMES)
    assert llm.calls == 0

import pytest

from src.llm import CostTracker, ItemProcessingError, LLMResult
from src.synthesize import synthesize_cluster


class QueueLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, model, messages, response_json=True):
        self.calls += 1
        content, cost = self.responses.pop(0)
        return LLMResult(content, cost)


def _members():
    return [
        {"title": "Apple M5", "text": "body", "link": "https://x/1", "source_name": "A"},
        {"title": "Apple chip", "text": "body2", "link": "https://y/2", "source_name": "B"},
    ]


def test_valid_synthesis():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM(
        [('{"summary_it":"Sintesi in italiano","source_links":["https://x/1"]}', 0.002)]
    )
    s = synthesize_cluster(llm, tracker, "m", _members())
    assert s.summary_it == "Sintesi in italiano"
    assert s.source_links == ["https://x/1"]
    assert tracker.run_cost == 0.002


def test_missing_source_link_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"summary_it":"s","source_links":[]}', 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())


def test_non_http_link_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"summary_it":"s","source_links":["ftp://x/1"]}', 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())


def test_empty_summary_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([('{"summary_it":"","source_links":["https://x/1"]}', 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())

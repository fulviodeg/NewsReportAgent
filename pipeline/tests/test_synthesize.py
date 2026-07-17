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


_VALID = (
    '{"title":"Titolo","subtitle":"Sottotitolo","summary_it":"Sintesi in italiano",'
    '"summary_long":"Approfondimento esteso","source_links":["https://x/1"]}'
)


def test_valid_synthesis():
    tracker = CostTracker(0.0, 5.0)
    llm = QueueLLM([(_VALID, 0.002)])
    s = synthesize_cluster(llm, tracker, "m", _members())
    assert s.title == "Titolo"
    assert s.subtitle == "Sottotitolo"
    assert s.summary_it == "Sintesi in italiano"
    assert s.summary_long == "Approfondimento esteso"
    assert s.source_links == ["https://x/1"]
    assert tracker.run_cost == 0.002


def test_missing_source_link_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    bad = '{"title":"T","subtitle":"S","summary_it":"s","summary_long":"l","source_links":[]}'
    llm = QueueLLM([(bad, 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())


def test_non_http_link_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    bad = '{"title":"T","subtitle":"S","summary_it":"s","summary_long":"l","source_links":["ftp://x/1"]}'
    llm = QueueLLM([(bad, 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())


def test_missing_title_is_rejected():
    tracker = CostTracker(0.0, 5.0)
    bad = '{"subtitle":"S","summary_it":"s","summary_long":"l","source_links":["https://x/1"]}'
    llm = QueueLLM([(bad, 0.001)] * 3)
    with pytest.raises(ItemProcessingError):
        synthesize_cluster(llm, tracker, "m", _members())

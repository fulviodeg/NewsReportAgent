import json

import httpx

from src.embeddings import OpenAICompatibleEmbeddings, unit_normalize


def test_unit_normalize():
    v = unit_normalize([3.0, 4.0])
    assert abs((v[0] ** 2 + v[1] ** 2) - 1.0) < 1e-9


def test_embeddings_chunks_by_batch_size():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        calls.append(len(inputs))
        return httpx.Response(
            200,
            json={"data": [{"index": i, "embedding": [float(i)]} for i in range(len(inputs))]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddings(
        "https://api.example.com/v1/embeddings", "m", "k", client=client, batch_size=2
    )
    vectors = provider.embed(["a", "b", "c", "d", "e"])
    assert len(vectors) == 5
    assert calls == [2, 2, 1]  # chunked into batches of 2


def test_openai_compatible_embeddings_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddings(
        "https://api.example.com/v1/embeddings", "model-x", "sk-test", client=client
    )
    vectors = provider.embed(["first", "second"])

    # results are ordered by the response "index" field
    assert vectors[0] == [1.0, 0.0]
    assert vectors[1] == [0.3, 0.4]
    assert captured["body"] == {"model": "model-x", "input": ["first", "second"]}
    assert captured["auth"] == "Bearer sk-test"

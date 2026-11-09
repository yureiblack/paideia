"""Tests for OllamaProvider in app/llm.py, against a simulated Ollama.

Purpose: what each request asks of Ollama (the schema, a fixed temperature
and seed, the context size, a reply cap, no thinking aloud), what comes back,
and every way it can fail: retried with pauses when retrying can help, and
reported at once, in words a user can act on, when it cannot. No real model
is needed; httpx2's MockTransport plays Ollama.
"""

import json

import httpx2
import pytest
from pydantic import BaseModel, Field

from app.llm import REPLY_TOKENS, LLMError, OllamaProvider, Prompt

PROMPT = Prompt(name="test_prompt", version="v1", system="Be brief.", user="Hello?")


class Answer(BaseModel):
    words: list[str] = Field(min_length=1, max_length=3)


def ok(content: dict | str) -> httpx2.Response:
    text = content if isinstance(content, str) else json.dumps(content)
    return httpx2.Response(
        200, json={"message": {"role": "assistant", "content": text}}
    )


def provider(*replies, retries: int = 2):
    """An OllamaProvider whose Ollama answers each request with the next
    reply: a response, or an exception to raise. Returns the provider, the
    requests it sent and the pauses it took."""
    sent, pauses = [], []
    queue = list(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    llm = OllamaProvider(
        "http://ollama.test",
        "ministral-3:8b",
        context_tokens=16384,
        timeout_seconds=300,
        max_retries=retries,
        transport=httpx2.MockTransport(handle),
        sleep=pauses.append,
    )
    return llm, sent, pauses


def body(request: httpx2.Request) -> dict:
    return json.loads(request.content)


def test_a_request_sends_the_prompt_the_schema_and_fixed_options():
    llm, sent, _ = provider(ok({"words": ["hi"]}))

    generated = llm.generate_structured(PROMPT, Answer)

    [request] = sent
    assert request.url.path == "/api/chat"
    assert body(request) == {
        "model": "ministral-3:8b",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hello?"},
        ],
        "format": Answer.model_json_schema(),
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
            "seed": 7,
            "num_ctx": 16384,
            "num_predict": REPLY_TOKENS,
        },
    }
    assert generated.value == Answer(words=["hi"])
    assert (generated.model, generated.prompt_version) == (
        "ministral-3:8b",
        "test_prompt/v1",
    )
    assert generated.seconds >= 0


def test_connection_and_server_failures_are_retried_after_a_pause():
    llm, sent, pauses = provider(
        httpx2.ConnectError("refused"),
        httpx2.Response(500, json={"error": "out of memory"}),
        ok({"words": ["hi"]}),
    )

    assert llm.generate_structured(PROMPT, Answer).value.words == ["hi"]
    assert len(sent) == 3
    assert pauses == [1.0, 2.0]


def test_an_unreachable_ollama_says_how_to_start_it():
    llm, sent, _ = provider(*[httpx2.ConnectError("refused")] * 3, retries=2)

    with pytest.raises(LLMError, match="brew services start ollama"):
        llm.generate_structured(PROMPT, Answer)
    assert len(sent) == 3  # the first try and two retries


def test_a_timeout_says_how_long_it_waited():
    llm, _, _ = provider(*[httpx2.ReadTimeout("slow")] * 3)

    with pytest.raises(LLMError, match="within 300 seconds"):
        llm.generate_structured(PROMPT, Answer)


def test_a_server_error_that_persists_carries_ollamas_reason():
    llm, _, _ = provider(*[httpx2.Response(500, json={"error": "out of memory"})] * 3)

    with pytest.raises(LLMError, match="out of memory"):
        llm.generate_structured(PROMPT, Answer)


def test_a_missing_model_is_not_retried_and_says_how_to_download_it():
    llm, sent, pauses = provider(
        httpx2.Response(404, json={"error": "model 'ministral-3:8b' not found"})
    )

    with pytest.raises(LLMError, match="Run: ollama pull ministral-3:8b"):
        llm.generate_structured(PROMPT, Answer)
    assert (len(sent), pauses) == (1, [])


def test_a_refused_request_is_not_retried():
    llm, sent, _ = provider(httpx2.Response(400, json={"error": "invalid format"}))

    with pytest.raises(LLMError, match="invalid format"):
        llm.generate_structured(PROMPT, Answer)
    assert len(sent) == 1


def test_an_invalid_answer_is_retried_with_a_little_randomness():
    # Repeating the same request at temperature 0 would repeat the mistake.
    llm, sent, _ = provider(
        ok("not json at all"),
        ok({"words": []}),  # valid JSON, but breaks the schema
        ok({"words": ["hi"]}),
    )

    assert llm.generate_structured(PROMPT, Answer).value.words == ["hi"]
    options = [body(request)["options"] for request in sent]
    assert [(o["temperature"], o["seed"]) for o in options] == [
        (0, 7),
        (0.3, 8),
        (0.3, 9),
    ]


def test_answers_that_stay_invalid_are_reported():
    llm, _, _ = provider(*[ok("not json")] * 3)

    with pytest.raises(LLMError, match="did not have the expected form"):
        llm.generate_structured(PROMPT, Answer)


@pytest.mark.parametrize(
    ("reply", "problem"),
    [
        pytest.param(
            httpx2.Response(200, json={"models": [{"name": "ministral-3:8b"}]}),
            None,
            id="ready",
        ),
        pytest.param(
            httpx2.Response(200, json={"models": [{"name": "other:1b"}]}),
            "The model ministral-3:8b is not downloaded.",
            id="not downloaded",
        ),
        pytest.param(
            httpx2.ConnectError("refused"),
            "Ollama is not reachable at http://ollama.test.",
            id="not running",
        ),
    ],
)
def test_check_reports_whether_the_model_is_ready(reply, problem):
    llm, sent, _ = provider(reply)

    assert llm.check() == problem
    assert sent[0].url.path == "/api/tags"

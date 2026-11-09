"""The language model, as a replaceable service.

Purpose
-------
Everything that knows how a language model is called lives here, behind one
small interface: an LLMProvider takes a prompt and a Pydantic schema and
returns an answer that fits the schema, with the model's name, the prompt's
version and how long it took. Domain code (summaries now, roadmaps and
questions later) depends only on that interface, so the model behind it can
be swapped: Ollama on this machine today, a stand-in in the tests, a hosted
service one day, without touching domain logic.

The implementation talks to Ollama (https://ollama.com), which serves open
models locally. Decision record 08 explains the choice of model and every
setting below.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Generic, Protocol, TypeVar

import httpx2
from pydantic import BaseModel, ValidationError

from app.config import settings

# The longest answer a request may produce, in tokens. Every schema bounds
# its lists too: a model asked for structured output without limits can
# keep writing until the context is full.
REPLY_TOKENS = 2048

# A fixed seed with temperature 0 makes the same request give the same answer.
SEED = 7

# A retry after an invalid answer samples with a little randomness: at
# temperature 0 the model would simply repeat the same mistake.
RETRY_TEMPERATURE = 0.3

T = TypeVar("T", bound=BaseModel)

# One piece of writing at a time in this process: a document's summary or an
# environment's. The model serves one request at a time well on one machine,
# and work arriving together then queues instead of competing for memory.
ONE_AT_A_TIME = threading.Lock()


class LLMError(Exception):
    """The language model could not produce an answer. The message says why,
    in words a user can act on."""


@dataclass(frozen=True)
class Prompt:
    """A rendered prompt and the template version it came from."""

    name: str  # e.g. "document_summary"
    version: str  # e.g. "v1"
    system: str
    user: str

    @property
    def id(self) -> str:
        return f"{self.name}/{self.version}"


@dataclass(frozen=True)
class Generated(Generic[T]):
    """An answer and what produced it, so anything generated can be traced."""

    value: T
    model: str
    prompt_version: str
    seconds: float


class LLMProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def generate_structured(self, prompt: Prompt, schema: type[T]) -> Generated[T]:
        """An answer to the prompt that validates against the schema, or an
        LLMError."""
        ...

    def check(self) -> str | None:
        """None if the model is ready to use, otherwise the reason it is not."""
        ...


class OllamaProvider:
    """The LLMProvider used in production, talking to Ollama's HTTP API.

    Each request sends the schema as Ollama's format, so the model's output is
    constrained to valid JSON of that shape as it is generated, and the answer
    is validated again on arrival. Connection failures, timeouts, server
    errors and invalid answers are retried, with a pause between attempts; a
    model that is not downloaded is reported at once, since retrying cannot
    fix it.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        context_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        transport: httpx2.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._base_url = base_url
        self._model = model
        self._context_tokens = context_tokens
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx2.Client(
            base_url=base_url,
            timeout=httpx2.Timeout(timeout_seconds, connect=5.0),
            transport=transport,
        )

    @property
    def model_name(self) -> str:
        return self._model

    def _body(self, prompt: Prompt, schema: type[BaseModel], bad_answers: int) -> dict:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "format": schema.model_json_schema(),
            "stream": False,
            # Reasoning models would otherwise think aloud first, at length;
            # models without the switch ignore it.
            "think": False,
            "options": {
                "temperature": RETRY_TEMPERATURE if bad_answers else 0,
                "seed": SEED + bad_answers,
                "num_ctx": self._context_tokens,
                "num_predict": REPLY_TOKENS,
            },
        }

    def generate_structured(self, prompt: Prompt, schema: type[T]) -> Generated[T]:
        started = time.perf_counter()
        bad_answers = 0
        problem = LLMError("The language model could not be used.")
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(float(2 ** (attempt - 1)))  # 1 s, then 2 s, then 4 s
            try:
                response = self._client.post(
                    "/api/chat", json=self._body(prompt, schema, bad_answers)
                )
            except httpx2.ConnectError:
                problem = LLMError(
                    f"Could not reach Ollama at {self._base_url}. Is it running? "
                    "Start it with: brew services start ollama"
                )
                continue
            except httpx2.TimeoutException:
                problem = LLMError(
                    "The language model did not answer within "
                    f"{self._timeout_seconds:g} seconds."
                )
                continue
            if response.status_code == 404:
                raise LLMError(
                    f"The model {self._model} is not downloaded. "
                    f"Run: ollama pull {self._model}"
                )
            if response.status_code >= 500:
                problem = LLMError(
                    f"Ollama failed ({response.status_code}): {_error(response)}"
                )
                continue
            if response.status_code >= 400:
                raise LLMError(f"Ollama refused the request: {_error(response)}")
            try:
                content = response.json()["message"]["content"]
                value = schema.model_validate_json(content)
            except (KeyError, ValueError, ValidationError):
                bad_answers += 1
                problem = LLMError(
                    "The language model's answer did not have the expected form."
                )
                continue
            return Generated(
                value=value,
                model=self._model,
                prompt_version=prompt.id,
                seconds=time.perf_counter() - started,
            )
        raise problem

    def check(self) -> str | None:
        try:
            response = self._client.get("/api/tags", timeout=5.0)
            names = {model["name"] for model in response.json()["models"]}
        except (httpx2.HTTPError, ValueError, KeyError):
            return f"Ollama is not reachable at {self._base_url}."
        if self._model not in names:
            return f"The model {self._model} is not downloaded."
        return None


def _error(response: httpx2.Response) -> str:
    """Ollama's own error message, or the raw text if it sent none."""
    try:
        return str(response.json()["error"])
    except (ValueError, KeyError, TypeError):
        return response.text[:200]


@lru_cache
def default_provider() -> OllamaProvider:
    """The one provider per process, built from the settings."""
    return OllamaProvider(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_context_tokens,
        settings.llm_timeout_seconds,
        settings.llm_max_retries,
    )

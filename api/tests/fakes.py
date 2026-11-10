"""Stand-ins for the three models, for fast, offline tests.

FakeEmbedder turns each word into a fixed position in a 384-number vector, so
texts that share words get similar vectors and texts that share none get
unrelated ones. FakeReranker scores a passage by the share of the query's
words it contains. MockProvider answers prompts for the language model with
scripted or simple answers that fit the schema it is given. All are crude
next to the real models, but they are deterministic, instant, and need no
download.
"""

import hashlib
import math
import re
from collections.abc import Sequence

from app.config import settings


class FakeEmbedder:
    model_name = "fake-word-hash"

    def __init__(self):
        self.dimensions = settings.embedding_dimensions
        self.passages_embedded: list[str] = []  # every passage it was asked for

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z]+", text.lower()):
            slot = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vector[slot] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passages_embedded.extend(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class BrokenEmbedder(FakeEmbedder):
    """Fails like a model that could not be downloaded."""

    def embed_passages(self, texts):
        from app.embedding import EmbeddingError

        raise EmbeddingError(
            "Could not load the embedding model. No internet connection."
        )

    embed_query = embed_passages


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


class FakeReranker:
    model_name = "fake-word-overlap"

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []  # every (query, passages)

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        self.calls.append((query, list(passages)))
        wanted = _words(query)
        return [
            len(wanted & _words(passage)) / len(wanted) if wanted else 0.0
            for passage in passages
        ]


class BrokenReranker(FakeReranker):
    """Fails like a reranking model that could not be downloaded."""

    def score(self, query, passages):
        from app.reranking import RerankError

        raise RerankError("Could not load the reranking model. No internet connection.")


def allowed_numbers(schema) -> list[int]:
    """The passage numbers an answer schema allows, for summaries
    (KeyPoint) and concept extraction (ProposedConcept) alike."""
    defs = schema.model_json_schema()["$defs"]
    item = (defs.get("KeyPoint") or defs["ProposedConcept"])["properties"]["sources"]
    item = item["items"]
    if "enum" in item:
        return list(item["enum"])
    return list(range(item["minimum"], item["maximum"] + 1))


def pair_count(schema) -> int:
    """How many pairs a relationship answer schema asks about."""
    return schema.model_json_schema()["properties"]["decisions"]["maxItems"]


def relationship_answer(schema, choice: int, confidence: float) -> list[dict]:
    """The same choice for every pair a relationship schema asks about."""
    return [
        {"pair": n, "choice": choice, "confidence": confidence}
        for n in range(1, pair_count(schema) + 1)
    ]


def simple_answer(prompt, schema) -> dict:
    """A valid answer of the shape the schema asks for. A summary: one key
    point per allowed number, as few as the schema allows, each citing its
    number. Concepts: one per passage, "Concept 1" and so on, each citing
    its passage. Relationships: every pair related, with confidence 0.8."""
    properties = schema.model_json_schema()["properties"]
    if "decisions" in properties:
        return {"decisions": relationship_answer(schema, choice=5, confidence=0.8)}
    numbers = allowed_numbers(schema)
    if "concepts" in properties:
        return {
            "concepts": [
                {
                    "name": f"Concept {n}",
                    "definition": f"What passage {n} explains.",
                    "aliases": [],
                    "sources": [n],
                }
                for n in numbers
            ]
        }
    least = properties["key_points"]["minItems"]
    return {
        "overview": f"An overview of {len(numbers)} passages.",
        "key_points": [
            {"point": f"Point about passage {n}.", "sources": [n]}
            for n in numbers[:least]
        ],
    }


class MockProvider:
    """A language model that answers with answer(prompt, schema), by default
    simple_answer, and records every prompt and schema it was given."""

    def __init__(
        self, answer=simple_answer, problem: str | None = None, model_name="mock-llm"
    ):
        self.model_name = model_name
        self.answer = answer
        self.problem = problem  # what check() reports
        self.calls = []  # (prompt, schema) for every request

    def generate_structured(self, prompt, schema):
        from app.llm import Generated

        self.calls.append((prompt, schema))
        return Generated(
            value=schema.model_validate(self.answer(prompt, schema)),
            model=self.model_name,
            prompt_version=prompt.id,
            seconds=1.5,
        )

    def check(self):
        return self.problem


class FailingProvider(MockProvider):
    """Fails like a language model that is not running."""

    def generate_structured(self, prompt, schema):
        from app.llm import LLMError

        self.calls.append((prompt, schema))
        raise LLMError("Could not reach Ollama. Is it running?")

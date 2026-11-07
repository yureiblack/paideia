"""Stand-ins for the embedding and reranking models, for fast, offline tests.

FakeEmbedder turns each word into a fixed position in a 384-number vector, so
texts that share words get similar vectors and texts that share none get
unrelated ones. FakeReranker scores a passage by the share of the query's
words it contains. Both are crude next to the real models, which also match
meaning, but they are deterministic, instant, and need no download.
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

"""A stand-in Embedder for fast, offline tests.

It turns each word into a fixed position in a 384-number vector, so texts that
share words get similar vectors and texts that share none get unrelated ones.
That is crude next to a real model, which also matches meaning, but it is
deterministic, instant, and needs no download.
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

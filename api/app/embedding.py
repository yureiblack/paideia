"""Turning text into embeddings: lists of numbers that capture meaning.

Purpose
-------
Two passages about the same idea get similar embeddings even when they share
no words, which is what lets semantic search find "round robin" for a query
about "process scheduling". Everything that knows how embeddings are computed
lives here, behind a small interface: an Embedder turns passages and queries
into vectors of a fixed size. Nothing else imports the embedding library, so
another one could replace it by adding one class to this file.

The implementation runs BAAI/bge-small-en-v1.5 locally through fastembed and
ONNX Runtime: no external API, no cost per call, works offline once the model
has been downloaded. Decision record 05 explains why fastembed rather than
Sentence Transformers.
"""

import os
import threading
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import settings

# Embeddings are computed in batches of this many passages: large enough to be
# efficient, small enough to keep memory use modest.
BATCH_SIZE = 64


class EmbeddingError(Exception):
    """The embedding model could not be used. The message is shown to the user."""


class Embedder(Protocol):
    """Anything that can turn text into vectors of a fixed size."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """The Embedder used in production, built on fastembed.

    The model is loaded on first use rather than at startup: loading takes a
    moment, and the first ever use also downloads it, about 64 MB. Loading
    happens once per process, under a lock, so two first requests arriving
    together do not load it twice.
    """

    def __init__(self, model_name: str, dimensions: int, cache_dir: Path):
        self._model_name = model_name
        self._dimensions = dimensions
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            # Quiet Hugging Face's note that the download is anonymous, which
            # it is meant to be. Read when the library is imported, below.
            os.environ.setdefault("HF_HUB_VERBOSITY", "error")
            from fastembed import TextEmbedding

            try:
                model = TextEmbedding(self._model_name, cache_dir=str(self._cache_dir))
            except Exception as exc:
                raise EmbeddingError(
                    f"Could not load the embedding model {self._model_name}. The first "
                    "use downloads it, which needs an internet connection."
                ) from exc
            produced = len(next(iter(model.query_embed("dimension check"))))
            if produced != self._dimensions:
                raise EmbeddingError(
                    f"The embedding model {self._model_name} produces {produced} "
                    f"dimensions, but EMBEDDING_DIMENSIONS is {self._dimensions}."
                )
            self._model = model
            return model

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in order. Vectors have length 1, so cosine
        similarity is a plain dot product."""
        if not texts:
            return []
        model = self._load()
        return [
            v.tolist() for v in model.passage_embed(list(texts), batch_size=BATCH_SIZE)
        ]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        return next(iter(model.query_embed(text))).tolist()


@lru_cache
def default_embedder() -> FastEmbedEmbedder:
    """The one embedder per process, built from the settings."""
    return FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dimensions, settings.model_dir
    )

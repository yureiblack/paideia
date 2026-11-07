"""Reranking: scoring how well each passage answers a query.

Purpose
-------
Keyword search and semantic search are fast because they never look at a
query and a passage together: they compare words, or vectors computed in
advance. A cross-encoder reads the query and one passage as a single input and
judges how well the passage answers it. That is far more precise, and far too
slow to run over every chunk, so search runs it only on the few dozen
candidates the fast methods found, and orders the final results by it.

As with embeddings, everything that knows how reranking is computed lives
here, behind a small interface. The implementation runs
ms-marco-MiniLM-L-6-v2 locally through fastembed: no external API, works
offline once downloaded. Decision record 06 explains the choice.
"""

import math
import os
import threading
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import settings

BATCH_SIZE = 64


class RerankError(Exception):
    """The reranking model could not be used. The message is shown to the user."""


class Reranker(Protocol):
    """Anything that can score passages against a query."""

    @property
    def model_name(self) -> str: ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """One score per passage, in order, between 0 and 1: higher means a
        better answer to the query."""
        ...


def _sigmoid(x: float) -> float:
    """Squash any number into 0 to 1, keeping the order. Written with tanh so
    a very large or very small input can never overflow."""
    return 0.5 * (1.0 + math.tanh(x / 2.0))


class FastEmbedReranker:
    """The Reranker used in production, built on fastembed.

    Loaded on first use, once per process, under a lock, like the embedder.
    The first ever use downloads the model, about 87 MB.
    """

    def __init__(self, model_name: str, cache_dir: Path):
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            os.environ.setdefault("HF_HUB_VERBOSITY", "error")
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            try:
                self._model = TextCrossEncoder(
                    self._model_name, cache_dir=str(self._cache_dir)
                )
            except Exception as exc:
                raise RerankError(
                    f"Could not load the reranking model {self._model_name}. The "
                    "first use downloads it, which needs an internet connection."
                ) from exc
            return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """The model's raw output has no fixed range (on the evaluation
        fixture, about -11 to +9) and only its order matters. A sigmoid turns
        it into 0 to 1, easier to read, in the same order. It is not a
        calibrated probability."""
        if not passages:
            return []
        model = self._load()
        raw = model.rerank(query, list(passages), batch_size=BATCH_SIZE)
        return [_sigmoid(float(value)) for value in raw]


@lru_cache
def default_reranker() -> FastEmbedReranker:
    """The one reranker per process, built from the settings."""
    return FastEmbedReranker(settings.rerank_model, settings.model_dir)

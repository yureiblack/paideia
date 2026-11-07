"""Tests for app/embedding.py with the real model.

Purpose: prove the production embedder loads the configured model, produces
vectors of the configured size, and fails with a clear message when the size
is wrong. The first run downloads the model, about 64 MB, into MODEL_DIR;
later runs reuse it.
"""

import math

import pytest

from app.config import settings
from app.embedding import EmbeddingError, FastEmbedEmbedder, default_embedder


@pytest.fixture(scope="module")
def embedder() -> FastEmbedEmbedder:
    return default_embedder()


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_passages_become_unit_vectors_of_the_configured_size(embedder):
    vectors = embedder.embed_passages(["First passage.", "Second passage."])

    assert len(vectors) == 2
    assert all(len(v) == settings.embedding_dimensions for v in vectors)
    assert all(
        math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-3)
        for v in vectors
    )


def test_no_passages_means_no_work(embedder):
    assert embedder.embed_passages([]) == []


# Chunk-length passages on five topics, none using the words "process" or
# "scheduling". With one-sentence passages the small model's scores bunch
# together and a test on them passes or fails by chance; with passages the
# size of real chunks the scheduling one leads clearly. The model is
# deterministic, so this test is stable.
TOPICS = {
    "scheduling": (
        "The CPU decides which ready task runs next. Round robin gives every task a "
        "fixed time quantum and then preempts it, while shortest job first minimises "
        "the average waiting time. Priorities can starve low-priority work unless "
        "aging raises them over time."
    ),
    "paging": (
        "Paging divides physical memory into fixed-size frames. Each virtual page is "
        "mapped to a frame through the page table, and the translation lookaside "
        "buffer caches recent translations to keep address lookups fast."
    ),
    "file systems": (
        "A file system organises data on disk into files and directories. Inodes "
        "record where each file's blocks live, and journaling protects the metadata "
        "against crashes during writes."
    ),
    "deadlock": (
        "A deadlock needs four conditions at once: mutual exclusion, hold and wait, "
        "no preemption and circular wait. Breaking any one of them, for example by "
        "ordering lock acquisition, prevents it."
    ),
    "networking": (
        "TCP provides reliable, ordered delivery over IP using sequence numbers, "
        "acknowledgements and retransmission, with congestion control adjusting the "
        "sending rate."
    ),
}


@pytest.mark.parametrize(
    "query",
    [
        "Find material related to process scheduling",  # the roadmap's wording
        "process scheduling",
        "how does the operating system choose which process runs",
    ],
)
def test_meaning_finds_scheduling_without_its_keywords(embedder, query):
    assert not any(
        w in text.lower() for text in TOPICS.values() for w in ("process", "schedul")
    )
    query_vector = embedder.embed_query(query)
    vectors = dict(
        zip(TOPICS, embedder.embed_passages(list(TOPICS.values())), strict=True)
    )

    ranked = sorted(TOPICS, key=lambda topic: -cosine(query_vector, vectors[topic]))

    assert ranked[0] == "scheduling"


def test_a_wrong_dimension_setting_is_refused_with_a_clear_message():
    wrong = FastEmbedEmbedder(settings.embedding_model, 768, settings.model_dir)

    with pytest.raises(EmbeddingError, match="produces 384 dimensions"):
        wrong.embed_query("anything")

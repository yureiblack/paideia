"""Retrieval quality on the labelled fixture, with the real models.

Purpose: the roadmap's retrieval evaluation. Hybrid search, as the app runs
it, must put the right passage at or near the top nearly every time, must get
every question's answer in front of the reranker, and must do better than
either search alone, with or without the reranker. The measured scores are in
decision record 06; python -m tests.retrieval_eval prints them.
"""

from sqlalchemy.orm import Session

from app.embedding import default_embedder
from app.models import Environment
from app.reranking import default_reranker
from tests.retrieval_eval import evaluate, format_table, load_fixture


def test_hybrid_search_beats_each_search_alone(session: Session):
    embedder, reranker = default_embedder(), default_reranker()
    environment = Environment(name="Retrieval evaluation")
    session.add(environment)
    session.flush()
    keys = load_fixture(session, environment.id, embedder)

    scores = evaluate(session, environment.id, embedder, reranker, keys)

    table = "\n" + format_table(scores)
    hybrid = scores["hybrid"]
    assert hybrid.mrr >= 0.95, table
    assert hybrid.reached == 1.0, table
    for alone in ("keyword", "semantic", "fusion"):
        assert hybrid.mrr > scores[alone].mrr, table
    for fed_by_one in ("keyword+rerank", "semantic+rerank"):
        assert hybrid.mrr >= scores[fed_by_one].mrr, table
        assert hybrid.reached >= scores[fed_by_one].reached, table
    # Fusion alone already beats each search alone: they fail on different
    # questions.
    assert scores["fusion"].mrr > max(scores["keyword"].mrr, scores["semantic"].mrr)
    # The stages before the reranker must pull their weight too, or a weaker
    # one would hide behind it. The floors sit a little under the measured
    # scores in decision record 06 (keyword 0.885, fusion 0.928); ranking
    # keyword matches with ts_rank_cd instead, for one, gives 0.835 and 0.876.
    assert scores["keyword"].mrr >= 0.86, table
    assert scores["fusion"].mrr >= 0.90, table

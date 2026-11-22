"""Tests for computed exercises as practice (decision record 27): chosen when
practice is prepared, shown with fresh numbers, marked exactly through the
API, and counted like any other item.

Purpose: the model's choice is kept only where the concept's passages use
the type's words, and not asked at all where no passage could fit; a failed
choice leaves the written items; an exercise is shown with the numbers of
its variant and marked against them, with the worked solution; every review
shows new numbers; wrong, partial, malformed and out-of-date answers are
each handled; and an exercise counts in the learner's state.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import exercises
from app.llm import LLMError
from app.models import Attempt, GeneratedArtifact, LearningItem
from tests import pdfs
from tests.test_concepts import concept
from tests.test_concepts_api import environment, upload
from tests.test_graph import RULES
from tests.test_practice import Practising

LINEAR = pdfs.html_pdf(
    "<h2>Determinants</h2><p>The determinant of a square matrix is zero exactly "
    "when the matrix is not invertible. Expanding along a row computes it.</p>",
    "<h2>Deadlock</h2><p>A deadlock needs mutual exclusion, hold and wait, no "
    "preemption and a circular wait.</p>",
    "<h2>Rank</h2><p>The rank of a matrix counts its pivots; a square matrix of "
    "full rank has an inverse and a nonzero determinant.</p>",
)


class Exercising(Practising):
    """Practising, which chooses exercise types by concept name, or fails to."""

    def __init__(self, *args, choose=None, fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.choose = choose or {}
        self.fail = fail

    def _answer(self, prompt, schema):
        if prompt.name == "exercise_types":
            if self.fail:
                raise LLMError("Could not reach Ollama. Is it running?")
            name = prompt.user.split("\n", 1)[0].removeprefix("Concept: ").split(":")[0]
            return {"exercises": self.choose.get(name, [])}
        return super()._answer(prompt, schema)

    def exercise_calls(self):
        return [p for p, _ in self.calls if p.name == "exercise_types"]


@pytest.fixture
def llm():
    return Exercising(
        RULES,
        # Determinant also cites the passage on deadlock, which fits no type.
        [
            [
                concept("Determinant", [1, 2]),
                concept("Deadlock", [2]),
                concept("Rank", [3]),
            ]
        ],
        choose={
            "Determinant": ["determinant", "eigen"],
            "Deadlock": ["solve_system"],
            "Rank": ["rank", "inverse", "determinant"],
        },
    )


def prepared(client: TestClient, name: str) -> tuple[str, str]:
    env = environment(client)
    upload(client, env, "linear.pdf", LINEAR)
    concepts = client.get(f"/api/environments/{env}/concepts").json()["concepts"]
    concept_id = next(c["id"] for c in concepts if c["name"] == name)
    response = client.post(f"/api/concepts/{concept_id}/practice")
    assert response.status_code in (200, 202), response.text
    return env, concept_id


def stage_items(client: TestClient, env: str, concept_id: str) -> list[dict]:
    return client.get(
        f"/api/environments/{env}/practice/session", params={"concept_id": concept_id}
    ).json()


def exercise_item(client: TestClient, env: str, concept_id: str) -> dict:
    return next(
        i for i in stage_items(client, env, concept_id) if i["kind"] == "exercise"
    )


def answer(client: TestClient, item: dict, cells: list[str], variant=None):
    variant = item["exercise"]["variant"] if variant is None else variant
    return client.post(
        f"/api/learning-items/{item['id']}/attempts",
        json={"cells": cells, "variant": variant},
    )


def solution(item: dict) -> list[str]:
    shown = exercises.exercise(
        item["exercise"]["type"], f"{item['id']}:{item['exercise']['variant']}"
    )
    return [str(x) for x in shown.solution.numbers]


# --- choosing ---------------------------------------------------------------------------


def test_the_models_choice_is_kept_only_where_the_passages_use_its_words(
    client, llm, session: Session
):
    env, concept_id = prepared(client, "Determinant")

    kinds = sorted(i["kind"] for i in stage_items(client, env, concept_id))
    assert kinds == [
        "exercise",
        "flashcard",
        "multiple_choice",
        "short_answer",
        "true_false",
    ]
    assert exercise_item(client, env, concept_id)["exercise"]["type"] == "determinant"
    generation = session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.artifact_type == "practice_set"
        )
    )
    assert generation.metadata_json["exercises"] == ["determinant"]
    assert generation.metadata_json["exercises_refused"] == ["eigen"]


def test_a_concept_gets_at_most_two_exercises(client, llm):
    # Three fit its passage; the first two the model chose are kept.
    env, concept_id = prepared(client, "Rank")

    chosen = [
        i["exercise"]["type"]
        for i in stage_items(client, env, concept_id)
        if i["kind"] == "exercise"
    ]
    assert sorted(chosen) == ["inverse", "rank"]


def test_a_concept_whose_passages_fit_no_exercise_is_never_asked(client, llm):
    env, concept_id = prepared(client, "Deadlock")

    assert llm.exercise_calls() == []
    assert all(i["kind"] != "exercise" for i in stage_items(client, env, concept_id))


def test_a_choice_that_fails_leaves_the_written_items(client, session: Session):
    from app.main import app
    from app.routers.deps import get_llm

    failing = Exercising(RULES, [[concept("Determinant", [1])]], fail=True)
    app.dependency_overrides[get_llm] = lambda: failing

    env, concept_id = prepared(client, "Determinant")

    assert len(stage_items(client, env, concept_id)) == 4
    generation = session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.artifact_type == "practice_set"
        )
    )
    assert generation.status == "ready"
    assert generation.metadata_json["exercises_error"] == (
        "Could not reach Ollama. Is it running?"
    )


# --- answering ----------------------------------------------------------------------------


def test_an_exercise_is_marked_exactly_with_its_worked_solution(client, llm):
    env, concept_id = prepared(client, "Determinant")
    item = exercise_item(client, env, concept_id)

    response = answer(client, item, solution(item))

    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["correct"], result["graded_by"], result["right"]) == (
        True,
        "key",
        [True],
    )
    assert result["answer"].startswith("\\(\\det A = ")
    assert result["steps"] and result["steps"][-1].endswith("\\]")
    # It cites the passage on determinants, which its type was checked against.
    assert [s["heading"] for s in result["sources"]] == ["Determinants"]


def test_a_review_shows_new_numbers(client, llm):
    env, concept_id = prepared(client, "Determinant")
    first = exercise_item(client, env, concept_id)
    answer(client, first, solution(first))

    again = exercise_item(client, env, concept_id)

    assert again["exercise"]["variant"] == 1
    assert again["prompt"] != first["prompt"]


def test_a_wrong_answer_is_wrong_and_explained(client, llm):
    env, concept_id = prepared(client, "Determinant")
    item = exercise_item(client, env, concept_id)
    wrong = str(int(solution(item)[0]) + 1)

    result = answer(client, item, [wrong]).json()

    assert (result["correct"], result["right"]) == (False, [False])
    assert result["steps"]
    # A concept missed on its last answer needs attention.
    overview = client.get(f"/api/environments/{env}/practice").json()
    assert [c["name"] for c in overview["needs_attention"]] == ["Determinant"]


@pytest.mark.parametrize(
    "cells, variant, reason",
    [
        (["two"], None, "Cell 1 is not a number"),
        (["1", "2"], None, "The answer needs 1 numbers; 2 came."),
        (["1"], 5, "This exercise's numbers are out of date: load it again."),
    ],
)
def test_an_unreadable_or_out_of_date_answer_is_refused_and_not_recorded(
    client, llm, session: Session, cells, variant, reason
):
    env, concept_id = prepared(client, "Determinant")
    item = exercise_item(client, env, concept_id)

    response = answer(client, item, cells, variant)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(reason)
    attempts = session.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.item_id == uuid.UUID(item["id"]))
    )
    assert attempts == 0


def test_the_kind_of_an_exercise_item_is_stored(session: Session, client, llm):
    prepared(client, "Determinant")

    stored = session.scalar(select(LearningItem).where(LearningItem.kind == "exercise"))

    assert stored.content == {"exercise": "determinant"}
    assert stored.difficulty == 3
    assert stored.prompt_version == "exercise_types/v1"

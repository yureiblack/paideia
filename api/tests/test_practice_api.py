"""Tests for the practice endpoints.

Purpose: the HTTP contract with a stand-in model. Preparing practice writes
items in the background; a session never sends the key of an item the
backend grades; answers come back graded, with sources identical to source
previews; replaced items cannot be answered; bad requests are refused; "due
today" follows the end of the learner's own day.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.test_concepts import concept
from tests.test_concepts_api import environment, upload
from tests.test_graph import RULES, SCHEDULING_CONCEPTS
from tests.test_graph_api import SCHEDULING, SYNCHRONIZATION
from tests.test_practice import Practising


@pytest.fixture
def llm():
    # The second lecture explains threads too.
    return Practising(RULES, [SCHEDULING_CONCEPTS, [concept("Thread", [1])]])


def concept_ids(client: TestClient, env: str) -> dict[str, str]:
    concepts = client.get(f"/api/environments/{env}/concepts").json()["concepts"]
    return {c["name"]: c["id"] for c in concepts}


def overview(client: TestClient, env: str) -> dict:
    return client.get(f"/api/environments/{env}/practice").json()


def test_preparing_practice_writes_items_in_the_background(client: TestClient, llm):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)

    response = client.post(
        f"/api/environments/{env}/practice", json={"concept_ids": list(ids.values())}
    )
    body = overview(client, env)

    assert response.status_code == 202
    assert {c["name"]: c["state"] for c in response.json()["concepts"]} == {
        "Round Robin": "pending",
        "Thread": "pending",
        "Time Quantum": "pending",
    }
    assert (body["items"], body["new_concepts"], body["due_concepts"]) == (12, 3, 0)
    assert {c["state"] for c in body["concepts"]} == {"ready"}
    again = client.post(f"/api/concepts/{ids['Thread']}/practice")
    assert again.status_code == 200
    assert len(llm.practice_calls()) == 3


def test_a_session_hides_the_key_and_answers_come_back_graded(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(f"/api/concepts/{ids['Thread']}/practice")

    due = client.get(f"/api/environments/{env}/practice/session").json()
    items = client.get(
        f"/api/environments/{env}/practice/session",
        params={"concept_id": ids["Thread"]},
    ).json()

    assert len(due) == 2  # one new concept: two items
    assert len(items) == 4
    by_kind = {i["kind"]: i for i in items}
    assert by_kind["multiple_choice"]["answer"] is None
    assert len(by_kind["multiple_choice"]["options"]) == 4
    assert by_kind["true_false"]["answer"] is None
    assert by_kind["flashcard"]["answer"]  # the learner marks it after seeing it
    response = client.post(
        f"/api/learning-items/{by_kind['true_false']['id']}/attempts",
        json={"truth": True, "seconds": 3},
    )
    result = response.json()
    assert response.status_code == 200
    assert result["graded_by"] == "key"
    assert result["answer"] in ("True", "False")
    assert result["correct"] is (result["answer"] == "True")
    [citation] = result["sources"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]


def test_a_stage_session_takes_its_concepts(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(
        f"/api/environments/{env}/practice", json={"concept_ids": list(ids.values())}
    )

    items = client.get(
        f"/api/environments/{env}/practice/session",
        params={"concept_id": [ids["Thread"], ids["Time Quantum"]]},
    ).json()

    assert {i["concept"]["name"] for i in items} == {"Thread", "Time Quantum"}
    assert len(items) == 8


def test_bad_answers_and_replaced_items_are_refused(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(f"/api/concepts/{ids['Thread']}/practice")
    items = client.get(
        f"/api/environments/{env}/practice/session",
        params={"concept_id": ids["Thread"]},
    ).json()
    choice = next(i for i in items if i["kind"] == "multiple_choice")

    wrong_kind = client.post(
        f"/api/learning-items/{choice['id']}/attempts", json={"knew": True}
    )
    out_of_range = client.post(
        f"/api/learning-items/{choice['id']}/attempts", json={"choice": 4}
    )
    unknown = client.post(
        f"/api/learning-items/{uuid.uuid4()}/attempts", json={"knew": True}
    )
    empty = client.post(f"/api/environments/{env}/practice", json={"concept_ids": []})
    upload(client, env, "sync.pdf", SYNCHRONIZATION)  # Thread's passages change
    replaced = client.post(
        f"/api/learning-items/{choice['id']}/attempts", json={"choice": 0}
    )

    assert wrong_kind.status_code == 422
    assert out_of_range.status_code == 422
    assert unknown.status_code == 404
    assert empty.status_code == 422
    assert replaced.status_code == 409
    thread = next(c for c in overview(client, env)["concepts"] if c["name"] == "Thread")
    assert thread["state"] == "outdated"


def test_due_today_is_the_learners_own_day(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(f"/api/concepts/{ids['Thread']}/practice")
    [first, second] = client.get(f"/api/environments/{env}/practice/session").json()
    for item in (first, second):
        client.post(
            f"/api/learning-items/{item['id']}/attempts",
            json={"knew": True, "choice": 0, "truth": True},
        )

    now = client.get(f"/api/environments/{env}/practice").json()
    end_of_day = (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat()
    tomorrow = client.get(
        f"/api/environments/{env}/practice", params={"until": end_of_day}
    ).json()
    naive = client.get(
        f"/api/environments/{env}/practice", params={"until": "2026-11-11T23:59:59"}
    )

    thread = next(c for c in now["concepts"] if c["name"] == "Thread")
    assert (thread["review"], thread["exposures"], now["due_concepts"]) == (
        "scheduled",
        2,
        0,
    )
    assert tomorrow["due_concepts"] == 1
    assert naive.status_code == 422

"""Tests for today's study plan, through the API, with a stand-in model.

Purpose: the plan follows what was stored: concepts missed are strengthened,
concepts due today reviewed, the next roadmap stage learned, a new document
skimmed; a budget moves what does not fit to later; the learner's own
answer times are used once there are enough; bad requests are refused.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services import planner
from tests.test_concepts import concept
from tests.test_concepts_api import environment, upload
from tests.test_graph import RULES, SCHEDULING_CONCEPTS
from tests.test_graph_api import SCHEDULING, SYNCHRONIZATION
from tests.test_practice import Practising
from tests.test_practice_api import concept_ids


@pytest.fixture
def llm():
    sync = [concept("Mutex", [1]), concept("Semaphore", [2])]
    return Practising(RULES, [SCHEDULING_CONCEPTS, sync])


def tomorrow() -> str:
    return (datetime.now(UTC) + timedelta(days=1, hours=1)).isoformat()


def plan(client: TestClient, env: str, **params) -> dict:
    response = client.get(f"/api/environments/{env}/plan", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def answer_all(client: TestClient, env: str, concept_id: str, knew: bool, seconds=None):
    items = client.get(
        f"/api/environments/{env}/practice/session", params={"concept_id": concept_id}
    ).json()
    for item in items:
        client.post(
            f"/api/learning-items/{item['id']}/attempts",
            json={
                "knew": knew,
                "choice": 0 if knew else 1,
                "truth": knew,
                "seconds": seconds,
            },
        )


def test_the_plan_follows_the_learners_state_and_the_material(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(
        f"/api/environments/{env}/practice",
        json={"concept_ids": [ids["Thread"], ids["Round Robin"]]},
    )
    answer_all(client, env, ids["Thread"], knew=True)
    answer_all(client, env, ids["Round Robin"], knew=False)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)

    body = plan(client, env, until=tomorrow())

    kinds = [(s["kind"], [c["name"] for c in s["concepts"]]) for s in body["sessions"]]
    assert kinds[0] == ("strengthen", ["Round Robin"])
    assert kinds[1] == ("review", ["Thread"])
    assert kinds[2][0] == "learn" and "Time Quantum" in kinds[2][1]
    learn = body["sessions"][2]
    assert (learn["stage"], learn["needs_preparing"]) == (1, True)
    skim = body["sessions"][-1]
    assert (skim["kind"], skim["document"]["filename"]) == ("skim", "sync.pdf")
    assert {c["name"] for c in skim["concepts"]} == {"Mutex", "Semaphore"}
    assert all(s["minutes"] >= 1 and s["rationale"] for s in body["sessions"])
    assert body["minutes"] == sum(s["minutes"] for s in body["sessions"])
    assert (body["later"], body["budget"]) == ([], None)


def test_a_budget_moves_what_does_not_fit_to_later(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)
    full = plan(client, env)
    longest = max(s["minutes"] for s in full["sessions"])

    tight = plan(client, env, minutes=max(5, longest - 1))

    assert tight["budget"] == max(5, longest - 1)
    assert tight["minutes"] <= tight["budget"]
    assert len(tight["sessions"]) + len(tight["later"]) == len(full["sessions"])


def test_the_learners_own_answer_times_count_once_there_are_enough(
    client: TestClient, session
):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)
    client.post(
        f"/api/environments/{env}/practice", json={"concept_ids": list(ids.values())}
    )
    for _ in range(2):  # six quick answers of each kind
        for concept_id in ids.values():
            answer_all(client, env, concept_id, knew=True, seconds=6)

    timed = planner._timed(session, uuid.UUID(env))
    [review] = [
        s
        for s in plan(client, env, until=tomorrow())["sessions"]
        if s["kind"] == "review"
    ]

    assert {kind: len(times) for kind, times in timed.items()} == dict.fromkeys(
        ("short_answer", "multiple_choice", "true_false", "flashcard"), 6
    )
    # Three concepts, two answers each, at 6 s: one minute. At the default
    # pace it would be six.
    assert (len(review["concepts"]), review["minutes"]) == (3, 1)


def test_bad_requests_are_refused(client: TestClient):
    env = environment(client)

    assert (
        client.get(f"/api/environments/{env}/plan", params={"minutes": 2}).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/environments/{env}/plan", params={"until": "2026-11-12T23:59:59"}
        ).status_code
        == 422
    )
    assert client.get(f"/api/environments/{uuid.uuid4()}/plan").status_code == 404
    assert plan(client, env) == {
        "sessions": [],
        "later": [],
        "minutes": 0,
        "budget": None,
    }

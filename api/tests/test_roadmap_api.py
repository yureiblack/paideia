"""Tests for the learning roadmap endpoints.

Purpose: the HTTP contract with a stand-in model. The roadmap builds itself
after the graph; its citations are the ones search returns; asking again
asks nothing; deleting a document keeps the titles of the stages it did not
change; a failure shows plain titles and is retried on request.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.llm import LLMError
from app.main import app
from app.routers.deps import get_llm
from tests.test_concepts_api import environment, upload
from tests.test_graph import RULES, SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS
from tests.test_graph_api import SCHEDULING, SYNCHRONIZATION
from tests.test_roadmap import Titling


@pytest.fixture
def llm():
    return Titling(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])


def roadmap(client: TestClient, env: str) -> dict:
    return client.get(f"/api/environments/{env}/roadmap").json()


def outline(body: dict) -> list[tuple[str, list[str]]]:
    return [(s["title"], [c["name"] for c in s["concepts"]]) for s in body["stages"]]


def test_the_roadmap_builds_itself_after_the_graph(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)

    body = roadmap(client, env)

    # One upload at a time: the second lecture's stage was titled on its own.
    assert body["state"] == "up_to_date"
    assert outline(body) == [
        ("Topic 1", ["Thread", "Round Robin", "Time Quantum"]),
        ("Topic 1", ["Critical Section", "Mutex", "Semaphore"]),
    ]
    rr = body["stages"][0]["concepts"][1]
    assert [c["name"] for c in rr["builds_on"]] == ["Thread"]
    [citation] = rr["evidence"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]
    assert [d["filename"] for d in body["stages"][0]["documents"]] == ["scheduling.pdf"]


def test_asking_again_asks_nothing(client: TestClient, llm):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    calls = len(llm.calls)

    response = client.post(f"/api/environments/{env}/roadmap")

    assert response.status_code == 200
    assert response.json()["state"] == "up_to_date"
    assert len(llm.calls) == calls


def test_deleting_a_document_keeps_the_titles_of_the_stages_left(
    client: TestClient, llm
):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    sync = upload(client, env, "sync.pdf", SYNCHRONIZATION)
    calls = len(llm.calls)

    client.delete(f"/api/documents/{sync['id']}")

    body = roadmap(client, env)
    assert body["state"] == "up_to_date"
    assert outline(body) == [("Topic 1", ["Thread", "Round Robin", "Time Quantum"])]
    assert len(llm.calls) == calls


class FailsOnce(Titling):
    """Titles stages only after failing the first time."""

    failed = False

    def generate_structured(self, prompt, schema):
        if prompt.name == "roadmap_stages" and not self.failed:
            self.failed = True
            raise LLMError("The model stopped answering.")
        return super().generate_structured(prompt, schema)


def test_a_failure_shows_plain_titles_and_is_retried_on_request(client: TestClient):
    llm = FailsOnce(RULES, [SCHEDULING_CONCEPTS])
    app.dependency_overrides[get_llm] = lambda: llm
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)

    failed = roadmap(client, env)
    response = client.post(f"/api/environments/{env}/roadmap")

    assert (failed["state"], failed["error"]) == (
        "failed",
        "The model stopped answering.",
    )
    assert outline(failed) == [
        ("Thread and 2 more", ["Thread", "Round Robin", "Time Quantum"])
    ]
    assert response.status_code == 202
    assert response.json()["state"] == "updating"
    assert outline(roadmap(client, env))[0][0] == "Topic 1"


def test_an_environment_without_concepts_has_no_roadmap(client: TestClient):
    env = environment(client)

    body = roadmap(client, env)
    response = client.post(f"/api/environments/{env}/roadmap")

    assert (body["state"], body["stages"]) == ("none", [])
    assert response.status_code == 422


def test_an_unknown_environment_is_not_found(client: TestClient):
    assert client.get(f"/api/environments/{uuid.uuid4()}/roadmap").status_code == 404

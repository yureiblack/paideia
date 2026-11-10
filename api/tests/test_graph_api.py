"""Tests for the knowledge graph endpoints.

Purpose: the HTTP contract with a stand-in model. The graph builds itself
once concepts are extracted; a concept's neighbourhood lists its
relationships with the same citations search returns; asking again asks the
model nothing; deleting a document rebuilds the graph from what is left; a
failed build is retried on request, and retrying a document's concepts
rebuilds the graph too.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.llm import LLMError
from app.main import app
from app.routers.deps import get_llm
from tests import pdfs
from tests.fakes import FailingProvider
from tests.test_concepts_api import environment, upload
from tests.test_graph import (
    RULES,
    SCHEDULING_CONCEPTS,
    SYNCHRONIZATION_CONCEPTS,
    Deciding,
)

SCHEDULING = pdfs.html_pdf(
    "<h2>Threads</h2><p>A thread is a sequence of execution within a process.</p>",
    "<h2>Round robin</h2><p>Round robin gives every thread a time quantum in turn.</p>",
)
SYNCHRONIZATION = pdfs.html_pdf(
    "<h2>Mutex</h2><p>A mutex lets one of the threads into the critical section.</p>",
    "<h2>Semaphores</h2><p>A semaphore counts the resources available.</p>",
)


@pytest.fixture
def llm():
    return Deciding(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])


def graph(client: TestClient, env: str) -> dict:
    return client.get(f"/api/environments/{env}/graph").json()


def named(body: dict) -> set[tuple[str, str, str]]:
    names = {n["id"]: n["name"] for n in body["nodes"]}
    return {
        (names[e["source"]], e["relationship_type"], names[e["target"]])
        for e in body["edges"]
    }


def concept_id(body: dict, name: str) -> str:
    return next(n["id"] for n in body["nodes"] if n["name"] == name)


def test_the_graph_builds_itself_once_concepts_are_extracted(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)

    body = graph(client, env)

    assert (body["state"], body["pairs"], body["asked"]) == ("up_to_date", 3, 3)
    assert [n["name"] for n in body["nodes"]] == [
        "Round Robin",
        "Thread",
        "Time Quantum",
    ]
    assert named(body) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }
    near = client.get(
        f"/api/concepts/{concept_id(body, 'Round Robin')}/neighbourhood"
    ).json()
    assert near["concept"]["name"] == "Round Robin"
    [thread] = near["prerequisites"]
    assert (thread["name"], thread["depth"], thread["confidence"]) == ("Thread", 1, 0.9)
    [citation] = thread["evidence"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]
    assert [p["name"] for p in near["parts"]] == ["Time Quantum"]
    assert near["dependents"] == near["related"] == near["part_of"] == []


def test_asking_again_asks_the_model_nothing(client: TestClient, llm):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    calls = len(llm.calls)

    response = client.post(f"/api/environments/{env}/graph")

    assert response.status_code == 200
    assert response.json()["state"] == "up_to_date"
    assert len(llm.calls) == calls


def test_a_new_document_adds_to_the_graph_and_deleting_it_takes_it_away(
    client: TestClient, llm
):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    sync = upload(client, env, "sync.pdf", SYNCHRONIZATION)

    body = graph(client, env)
    assert ("Thread", "PREREQUISITE_OF", "Mutex") in named(body)
    assert (body["pairs"], body["asked"]) == (6, 3)
    calls = len(llm.calls)

    client.delete(f"/api/documents/{sync['id']}")

    body = graph(client, env)
    assert body["state"] == "up_to_date"
    assert named(body) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }
    assert len(llm.calls) == calls


class FailsOnce(Deciding):
    """Classifies relationships only after failing the first time."""

    failed = False

    def generate_structured(self, prompt, schema):
        if prompt.name == "relationship" and not self.failed:
            self.failed = True
            raise LLMError("The model stopped answering.")
        return super().generate_structured(prompt, schema)


def test_a_failed_build_is_retried_on_request(client: TestClient):
    llm = FailsOnce(RULES, [SCHEDULING_CONCEPTS])
    app.dependency_overrides[get_llm] = lambda: llm
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)

    failed = graph(client, env)
    response = client.post(f"/api/environments/{env}/graph")

    assert (failed["state"], failed["error"]) == (
        "failed",
        "The model stopped answering.",
    )
    assert failed["edges"] == []
    assert response.status_code == 202
    assert response.json()["state"] == "updating"
    assert graph(client, env)["state"] == "up_to_date"


def test_retrying_a_documents_concepts_rebuilds_the_graph(client: TestClient, llm):
    app.dependency_overrides[get_llm] = FailingProvider
    env = environment(client)
    document = upload(client, env, "scheduling.pdf", SCHEDULING)
    assert graph(client, env)["state"] == "none"

    app.dependency_overrides[get_llm] = lambda: llm
    client.post(f"/api/documents/{document['id']}/concepts")

    body = graph(client, env)
    assert body["state"] == "up_to_date"
    assert len(body["edges"]) == 2


def test_an_environment_without_connected_concepts_has_no_graph(client: TestClient):
    env = environment(client)

    body = graph(client, env)
    response = client.post(f"/api/environments/{env}/graph")

    assert (body["state"], body["nodes"], body["edges"]) == ("none", [], [])
    assert response.status_code == 422


def test_an_unknown_concept_or_environment_is_not_found(client: TestClient):
    assert client.get(f"/api/concepts/{uuid.uuid4()}/neighbourhood").status_code == 404
    assert client.get(f"/api/environments/{uuid.uuid4()}/graph").status_code == 404

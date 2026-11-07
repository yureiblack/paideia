"""Tests for POST /api/search in app/routers/search.py.

Purpose: prove the HTTP contract the Search tab relies on: the result shape,
ordering, top_k, environment isolation, input validation, a clear 503 when
the model is unavailable, and the roadmap's acceptance query end to end with
the real model.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.embedding import default_embedder
from app.main import app
from app.routers.search import get_embedder
from tests import pdfs
from tests.fakes import BrokenEmbedder


def environment(client: TestClient, name: str = "Operating Systems") -> str:
    return client.post("/api/environments", json={"name": name}).json()["id"]


def upload(client: TestClient, env: str, data: bytes) -> dict:
    response = client.post(
        f"/api/environments/{env}/documents",
        params={"filename": "lecture.pdf"},
        content=data,
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def search(client: TestClient, env: str, query: str, top_k: int | None = None):
    body = {"environment_id": env, "query": query}
    if top_k is not None:
        body["top_k"] = top_k
    return client.post("/api/search", json=body)


LECTURE = pdfs.html_pdf(
    "<h2>Scheduling</h2><p>Round robin gives every task a time quantum.</p>"
    "<h2>Paging</h2><p>Paging maps pages to frames.</p>",
    "<h2>Deadlock</h2><p>Four conditions cause a deadlock.</p>",
)


def test_results_carry_the_roadmap_fields_and_where_they_came_from(client: TestClient):
    env = environment(client)
    document = upload(client, env, LECTURE)

    response = search(client, env, "deadlock conditions")

    assert response.status_code == 200
    first = response.json()["results"][0]
    assert set(first) == {
        "chunk_id",
        "document_id",
        "filename",
        "page_start",
        "page_end",
        "heading",
        "text",
        "score",
    }
    assert first["document_id"] == document["id"]
    assert first["filename"] == "lecture.pdf"
    assert (first["heading"], first["page_start"], first["page_end"]) == (
        "Deadlock",
        2,
        2,
    )


def test_results_are_ordered_and_limited(client: TestClient):
    env = environment(client)
    upload(client, env, LECTURE)

    results = search(client, env, "paging frames", top_k=2).json()["results"]

    assert len(results) == 2
    assert results[0]["heading"] == "Paging"
    assert results[0]["score"] >= results[1]["score"]


def test_another_environment_is_never_searched(client: TestClient):
    mine, theirs = environment(client, "Mine"), environment(client, "Theirs")
    upload(client, theirs, LECTURE)

    assert search(client, mine, "deadlock").json() == {"results": []}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"query": "x"}, id="no environment"),
        pytest.param(
            {"environment_id": "not-a-uuid", "query": "x"}, id="malformed environment"
        ),
        pytest.param({"query": ""}, id="empty query"),
        pytest.param({"query": "   "}, id="blank query"),
        pytest.param({"query": "x" * 501}, id="query too long"),
        pytest.param({"query": "x", "top_k": 0}, id="top_k zero"),
        pytest.param({"query": "x", "top_k": 51}, id="top_k too large"),
        pytest.param({"query": "x", "mode": "fuzzy"}, id="unknown field"),
    ],
)
def test_invalid_requests_are_a_422(client: TestClient, body: dict, request):
    env = environment(client)
    # Every case but the two about the environment gets a valid one added.
    if request.node.callspec.id not in ("no environment", "malformed environment"):
        body = {"environment_id": env, **body}

    response = client.post("/api/search", json=body)

    assert response.status_code == 422


def test_an_unknown_environment_is_a_404(client: TestClient):
    response = search(client, str(uuid.uuid4()), "anything")

    assert response.status_code == 404
    assert response.json() == {"detail": "Environment not found"}


def test_an_unavailable_model_is_a_503_with_the_reason(client: TestClient):
    env = environment(client)
    app.dependency_overrides[get_embedder] = BrokenEmbedder

    response = search(client, env, "anything")

    assert response.status_code == 503
    assert "No internet connection" in response.json()["detail"]


def test_the_roadmaps_acceptance_query_with_the_real_model(client: TestClient):
    # "Find material related to process scheduling", answered without an exact
    # keyword match: no section below uses "process" or "scheduling".
    app.dependency_overrides[get_embedder] = default_embedder
    env = environment(client)
    lecture = pdfs.html_pdf(
        "<h2>CPU time sharing</h2><p>The CPU decides which ready task runs next. Round"
        " robin gives every task a fixed time quantum and then preempts it, while"
        " shortest job first minimises the average waiting time.</p>",
        "<h2>Virtual memory</h2><p>Paging divides physical memory into fixed-size frames."
        " Each virtual page is mapped to a frame through the page table.</p>",
        "<h2>Storage</h2><p>A file system organises data on disk into files and"
        " directories, and journaling protects metadata against crashes.</p>",
    )
    document = upload(client, env, lecture)
    assert client.get(f"/api/documents/{document['id']}").json()["status"] == "ready"

    results = search(client, env, "Find material related to process scheduling").json()[
        "results"
    ]

    assert results[0]["heading"] == "CPU time sharing"
    assert "process" not in results[0]["text"].lower()
    assert "schedul" not in results[0]["text"].lower()

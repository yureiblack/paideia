"""Tests for the concept endpoints.

Purpose: the HTTP contract with a stand-in model. Concepts are extracted by
themselves once a document is read; the environment's inventory lists each
with its documents and evidence, the same citations search returns; asking
again extracts nothing new; a failed extraction is retried on request;
deleting a document removes the concepts only it mentioned.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.main import app
from app.models import Document
from app.routers.deps import get_llm
from tests import pdfs
from tests.fakes import FailingProvider

MEMORY = pdfs.html_pdf(
    "<h2>Paging</h2><p>Paging maps pages to frames.</p>",
    "<h2>TLB</h2><p>The TLB caches page translations.</p>",
)
THREADS = pdfs.html_pdf("<h2>Threads</h2><p>Threads share an address space.</p>")


def environment(client: TestClient) -> str:
    return client.post("/api/environments", json={"name": "Operating Systems"}).json()[
        "id"
    ]


def upload(client: TestClient, env: str, name: str, data: bytes) -> dict:
    response = client.post(
        f"/api/environments/{env}/documents",
        params={"filename": name},
        content=data,
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def inventory(client: TestClient, env: str) -> dict:
    return client.get(f"/api/environments/{env}/concepts").json()


def test_concepts_are_extracted_once_a_document_is_read(client: TestClient):
    env = environment(client)
    document = upload(client, env, "memory.pdf", MEMORY)

    body = inventory(client, env)

    [state] = body["documents"]
    assert (state["filename"], state["status"], state["kept"]) == (
        "memory.pdf",
        "ready",
        2,
    )
    assert [c["name"] for c in body["concepts"]] == ["Concept 1", "Concept 2"]
    first = body["concepts"][0]
    assert first["documents"] == [
        {"document_id": document["id"], "filename": "memory.pdf"}
    ]
    [citation] = first["evidence"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]
    own = client.get(f"/api/documents/{document['id']}/concepts").json()
    assert own["extraction"]["status"] == "ready"
    assert [c["id"] for c in own["concepts"]] == [c["id"] for c in body["concepts"]]


def test_asking_again_extracts_nothing_new(client: TestClient, llm):
    env = environment(client)
    document = upload(client, env, "memory.pdf", MEMORY)
    calls = len(llm.calls)

    response = client.post(f"/api/documents/{document['id']}/concepts")

    assert response.status_code == 200
    assert len(llm.calls) == calls


def test_a_failed_extraction_is_tried_again_when_asked(client: TestClient, llm):
    env = environment(client)
    app.dependency_overrides[get_llm] = FailingProvider
    document = upload(client, env, "memory.pdf", MEMORY)
    [state] = inventory(client, env)["documents"]
    assert (state["status"], state["error"]) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )

    app.dependency_overrides[get_llm] = lambda: llm
    response = client.post(f"/api/documents/{document['id']}/concepts")

    assert response.status_code == 202
    assert inventory(client, env)["documents"][0]["status"] == "ready"


def test_deleting_a_document_removes_the_concepts_only_it_mentioned(
    client: TestClient,
):
    env = environment(client)
    memory = upload(client, env, "memory.pdf", MEMORY)
    upload(client, env, "threads.pdf", THREADS)
    # Both documents' passage 1 becomes "Concept 1": shared. "Concept 2" is
    # memory.pdf's alone.
    assert [len(c["documents"]) for c in inventory(client, env)["concepts"]] == [2, 1]

    client.delete(f"/api/documents/{memory['id']}")

    [left] = inventory(client, env)["concepts"]
    assert left["name"] == "Concept 1"
    assert [d["filename"] for d in left["documents"]] == ["threads.pdf"]


def test_a_document_not_read_yet_cannot_be_asked_for_concepts(
    client: TestClient, session: Session
):
    env = environment(client)
    document = upload(client, env, "memory.pdf", MEMORY)
    session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document["id"]))
        .values(status="processing")
    )
    session.flush()

    response = client.post(f"/api/documents/{document['id']}/concepts")

    assert response.status_code == 409
    state = client.get(f"/api/documents/{document['id']}/concepts").json()
    assert (state["extraction"]["document_status"], state["extraction"]["status"]) == (
        "processing",
        "none",
    )


def test_unknown_ids_are_404s(client: TestClient):
    unknown = str(uuid.uuid4())
    assert client.get(f"/api/environments/{unknown}/concepts").status_code == 404
    assert client.get(f"/api/documents/{unknown}/concepts").status_code == 404
    assert client.post(f"/api/documents/{unknown}/concepts").status_code == 404

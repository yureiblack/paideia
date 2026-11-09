"""Tests for the summary endpoints and GET /health/llm.

Purpose: the HTTP contract with a stand-in model. A document is summarized as
soon as it is read; asking again returns the same summary; a failed one is
written again when asked; a new model's summary becomes current and the old
one stays in the history; and each refusal has its status code and reason.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.main import app
from app.models import Document, GeneratedArtifact
from app.routers.deps import get_llm
from app.services import summaries
from tests import pdfs
from tests.fakes import FailingProvider, MockProvider

LECTURE = pdfs.html_pdf(
    "<h2>Scheduling</h2><p>Round robin gives every task a time quantum.</p>",
    "<h2>Paging</h2><p>Paging maps pages to frames.</p>",
    "<h2>Deadlock</h2><p>Four conditions cause a deadlock.</p>",
)


def uploaded(client: TestClient) -> dict:
    env = client.post("/api/environments", json={"name": "Operating Systems"}).json()
    response = client.post(
        f"/api/environments/{env['id']}/documents",
        params={"filename": "Lecture 4.pdf"},
        content=LECTURE,
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def summary(client: TestClient, document_id: str):
    return client.get(f"/api/documents/{document_id}/summary")


def ask(client: TestClient, document_id: str):
    return client.post(f"/api/documents/{document_id}/summary")


def test_a_document_is_summarized_as_soon_as_it_is_read(client: TestClient):
    document = uploaded(client)

    response = summary(client, document["id"])

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "document_id",
        "status",
        "error",
        "overview",
        "key_points",
        "model",
        "prompt_versions",
        "source_version",
        "sections",
        "seconds",
        "current",
        "created_at",
        "updated_at",
        "earlier_versions",
    }
    assert (body["status"], body["current"], body["earlier_versions"]) == (
        "ready",
        True,
        0,
    )
    assert (body["model"], body["prompt_versions"]) == (
        "mock-llm",
        ["document_summary/v1"],
    )
    [citation] = body["key_points"][0]["citations"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]
    assert citation["document_version"] == document["sha256"]


def test_asking_for_a_ready_summary_returns_it_without_writing_again(
    client: TestClient, llm: MockProvider
):
    document = uploaded(client)
    written = len(llm.calls)

    response = ask(client, document["id"])

    assert response.status_code == 200
    assert response.json()["id"] == summary(client, document["id"]).json()["id"]
    assert len(llm.calls) == written


def test_a_failed_summary_is_written_again_when_asked(client: TestClient, llm):
    app.dependency_overrides[get_llm] = FailingProvider
    document = uploaded(client)
    failed = summary(client, document["id"]).json()
    assert (failed["status"], failed["error"]) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )

    app.dependency_overrides[get_llm] = lambda: llm
    response = ask(client, document["id"])

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    retried = summary(client, document["id"]).json()  # written in the background
    assert (retried["id"], retried["status"]) == (failed["id"], "ready")


def test_a_new_model_writes_a_new_summary_and_keeps_the_old_one(
    client: TestClient, session: Session
):
    document = uploaded(client)
    old = summary(client, document["id"]).json()
    # Postgres's now() is frozen for the whole test's transaction: date the
    # first summary a minute back so the history has an order to show.
    session.execute(
        update(GeneratedArtifact)
        .where(GeneratedArtifact.id == uuid.UUID(old["id"]))
        .values(created_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    session.flush()

    app.dependency_overrides[get_llm] = lambda: MockProvider(model_name="newer")
    assert summary(client, document["id"]).status_code == 404  # none by it yet
    assert ask(client, document["id"]).status_code == 202
    new = summary(client, document["id"]).json()

    assert (new["model"], new["status"], new["earlier_versions"]) == (
        "newer",
        "ready",
        1,
    )
    history = client.get(f"/api/documents/{document['id']}/summaries").json()
    assert [(s["id"], s["current"]) for s in history] == [
        (new["id"], True),
        (old["id"], False),
    ]


def test_a_document_not_read_yet_has_no_summary_and_cannot_be_asked_for_one(
    client: TestClient, session: Session
):
    document = uploaded(client)
    session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document["id"]))
        .values(status="processing")
    )
    session.flush()

    assert summary(client, document["id"]).json() == {"detail": "No summary yet."}
    response = ask(client, document["id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "This document has not been read yet."


def test_a_document_too_long_is_a_422_with_the_reason(client: TestClient, monkeypatch):
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 5)
    monkeypatch.setattr(summaries, "MAX_SECTIONS", 1)
    document = uploaded(client)
    assert summary(client, document["id"]).json()["status"] == "failed"

    response = ask(client, document["id"])

    assert response.status_code == 422
    assert "too long to summarize" in response.json()["detail"]


def test_an_unknown_document_is_a_404(client: TestClient):
    unknown = str(uuid.uuid4())
    assert summary(client, unknown).status_code == 404
    assert ask(client, unknown).status_code == 404
    assert client.get(f"/api/documents/{unknown}/summaries").status_code == 404


def test_the_model_status_says_whether_the_model_is_ready(client: TestClient):
    assert client.get("/health/llm").json() == {"status": "ok", "model": "mock-llm"}

    app.dependency_overrides[get_llm] = lambda: MockProvider(
        problem="The model ministral-3:8b is not downloaded."
    )
    response = client.get("/health/llm")

    assert response.status_code == 503
    assert response.json() == {"detail": "The model ministral-3:8b is not downloaded."}

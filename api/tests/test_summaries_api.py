"""Tests for POST /api/documents/{id}/summary and GET /health/llm.

Purpose: the HTTP contract with a stand-in model: the summary's shape, its
citations being the same objects search returns, and each refusal's status
code and reason; and the model status the header shows.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.main import app
from app.models import Document
from app.routers.summaries import get_llm
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


def summarize(client: TestClient, document_id: str):
    return client.post(f"/api/documents/{document_id}/summary")


def test_a_summary_cites_each_point_with_the_same_objects_search_returns(
    client: TestClient,
):
    document = uploaded(client)

    response = summarize(client, document["id"])

    assert response.status_code == 200
    summary = response.json()
    assert set(summary) == {
        "document_id",
        "overview",
        "key_points",
        "model",
        "prompt_versions",
        "sections",
        "seconds",
        "generated_at",
    }
    assert (summary["model"], summary["prompt_versions"]) == (
        "mock-llm",
        ["document_summary/v1"],
    )
    [first, *_] = summary["key_points"]
    [citation] = first["citations"]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]
    assert citation["document_version"] == document["sha256"]


def test_an_unknown_document_is_a_404(client: TestClient):
    assert summarize(client, str(uuid.uuid4())).status_code == 404


def test_a_document_not_read_yet_is_a_409(client: TestClient, session: Session):
    document = uploaded(client)
    session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document["id"]))
        .values(status="processing")
    )
    session.flush()

    response = summarize(client, document["id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "This document has not been read yet."


def test_a_document_too_long_is_a_422_with_the_reason(client: TestClient, monkeypatch):
    document = uploaded(client)
    monkeypatch.setattr(summaries, "SECTION_TOKENS", 5)
    monkeypatch.setattr(summaries, "MAX_SECTIONS", 1)

    response = summarize(client, document["id"])

    assert response.status_code == 422
    assert "too long to summarize on request" in response.json()["detail"]


def test_an_unavailable_model_is_a_503_with_the_reason(client: TestClient):
    document = uploaded(client)
    app.dependency_overrides[get_llm] = FailingProvider

    response = summarize(client, document["id"])

    assert response.status_code == 503
    assert "Is it running?" in response.json()["detail"]


def test_the_model_status_says_whether_the_model_is_ready(client: TestClient):
    assert client.get("/health/llm").json() == {"status": "ok", "model": "mock-llm"}

    app.dependency_overrides[get_llm] = lambda: MockProvider(
        problem="The model ministral-3:8b is not downloaded."
    )
    response = client.get("/health/llm")

    assert response.status_code == 503
    assert response.json() == {"detail": "The model ministral-3:8b is not downloaded."}

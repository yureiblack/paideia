"""Tests for the environment summary endpoints.

Purpose: the HTTP contract with a stand-in model. Uploads keep the summary
up to date by themselves; asking again writes nothing new; deleting a
document rebuilds it, or returns to an earlier summary when the material is
what it was then; waiting and failed states are reported, and Try again
recovers; an empty environment has nothing to summarize.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.llm import LLMError
from app.main import app
from app.models import Document
from app.routers.deps import get_llm
from tests import pdfs
from tests.fakes import FailingProvider, MockProvider

SCHEDULING = pdfs.html_pdf(
    "<h2>Round robin</h2><p>Round robin gives every task a time quantum.</p>",
    "<h2>Shortest job first</h2><p>Shortest job first runs the shortest burst.</p>",
)
MEMORY = pdfs.html_pdf(
    "<h2>Paging</h2><p>Paging maps pages to frames.</p>",
    "<h2>TLB</h2><p>The TLB caches page translations.</p>",
)


class FailsOnTheWholeEnvironment(MockProvider):
    """Writes document summaries, fails on environment summaries."""

    def generate_structured(self, prompt, schema):
        if prompt.name == "environment_summary":
            raise LLMError("The language model did not answer within 300 seconds.")
        return super().generate_structured(prompt, schema)


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


def state(client: TestClient, env: str) -> dict:
    return client.get(f"/api/environments/{env}/summary").json()


def test_uploads_keep_the_environment_summary_up_to_date(client: TestClient):
    env = environment(client)
    upload(client, env, "a.pdf", SCHEDULING)
    upload(client, env, "b.pdf", MEMORY)

    body = state(client, env)

    assert (body["state"], body["waiting_for"], body["earlier_versions"]) == (
        "up_to_date",
        0,
        1,
    )
    summary = body["summary"]
    assert summary["current"] is True
    assert {d["filename"] for d in summary["based_on"]} == {"a.pdf", "b.pdf"}
    citation = summary["key_points"][0]["citations"][0]
    preview = client.get(f"/api/chunks/{citation['chunk_id']}/preview").json()
    assert citation == preview["citation"]


def test_asking_again_when_up_to_date_writes_nothing(client: TestClient, llm):
    env = environment(client)
    upload(client, env, "a.pdf", SCHEDULING)
    calls = len(llm.calls)

    response = client.post(f"/api/environments/{env}/summary")

    assert response.status_code == 200
    assert response.json()["state"] == "up_to_date"
    assert len(llm.calls) == calls


def test_deleting_a_document_returns_to_the_summary_of_what_is_left(
    client: TestClient, llm
):
    env = environment(client)
    upload(client, env, "a.pdf", SCHEDULING)
    first = state(client, env)["summary"]
    second = upload(client, env, "b.pdf", MEMORY)
    calls = len(llm.calls)

    client.delete(f"/api/documents/{second['id']}")

    body = state(client, env)
    # The material is again exactly what the first summary was built from:
    # that summary is current again, and nothing new was written.
    assert body["state"] == "up_to_date"
    assert body["summary"]["id"] == first["id"]
    assert len(llm.calls) == calls
    history = client.get(f"/api/environments/{env}/summaries").json()
    assert [h["current"] for h in history].count(True) == 1
    assert len(history) == 2


def test_deleting_a_document_rebuilds_the_summary_from_what_is_left(
    client: TestClient,
):
    env = environment(client)
    first = upload(client, env, "a.pdf", SCHEDULING)
    upload(client, env, "b.pdf", MEMORY)

    client.delete(f"/api/documents/{first['id']}")

    # Material never summarized on its own before: rebuilt by the deletion.
    body = state(client, env)
    assert body["state"] == "up_to_date"
    assert [d["filename"] for d in body["summary"]["based_on"]] == ["b.pdf"]


def test_a_document_summary_written_on_request_updates_the_environment(
    client: TestClient, llm
):
    env = environment(client)
    app.dependency_overrides[get_llm] = FailingProvider
    document = upload(client, env, "a.pdf", SCHEDULING)
    assert state(client, env)["state"] == "none"  # its summary failed

    app.dependency_overrides[get_llm] = lambda: llm
    client.post(f"/api/documents/{document['id']}/summary")

    body = state(client, env)
    assert body["state"] == "up_to_date"
    assert [d["filename"] for d in body["summary"]["based_on"]] == ["a.pdf"]


def test_while_a_document_is_being_read_the_summary_waits(
    client: TestClient, session: Session
):
    env = environment(client)
    upload(client, env, "a.pdf", SCHEDULING)
    document = upload(client, env, "b.pdf", MEMORY)
    session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document["id"]))
        .values(status="processing")
    )
    session.flush()

    body = state(client, env)

    assert (body["state"], body["waiting_for"]) == ("waiting", 1)
    assert body["summary"] is not None  # the newest one, while it waits
    assert body["summary"]["current"] is False


def test_a_failed_summary_is_reported_and_try_again_recovers(client: TestClient, llm):
    env = environment(client)
    upload(client, env, "a.pdf", SCHEDULING)
    app.dependency_overrides[get_llm] = FailsOnTheWholeEnvironment
    upload(client, env, "b.pdf", MEMORY)

    failed = state(client, env)
    assert (failed["state"], failed["error"]) == (
        "failed",
        "The language model did not answer within 300 seconds.",
    )
    assert failed["summary"]["current"] is False  # the older one still shown

    app.dependency_overrides[get_llm] = lambda: llm
    response = client.post(f"/api/environments/{env}/summary")

    assert response.status_code == 202
    assert state(client, env)["state"] == "up_to_date"


def test_an_empty_environment_has_nothing_to_summarize(client: TestClient):
    env = environment(client)

    assert state(client, env) == {
        "state": "none",
        "waiting_for": 0,
        "error": None,
        "summary": None,
        "not_included": [],
        "earlier_versions": 0,
    }
    response = client.post(f"/api/environments/{env}/summary")
    assert response.status_code == 422
    assert "no summarized material" in response.json()["detail"]


def test_an_unknown_environment_is_a_404(client: TestClient):
    unknown = str(uuid.uuid4())
    assert client.get(f"/api/environments/{unknown}/summary").status_code == 404
    assert client.post(f"/api/environments/{unknown}/summary").status_code == 404
    assert client.get(f"/api/environments/{unknown}/summaries").status_code == 404

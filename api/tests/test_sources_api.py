"""Tests for GET /api/chunks/{chunk_id}/preview in app/routers/sources.py.

Purpose: the roadmap's acceptance flow over HTTP. A search result's citation
opens to its document and page with the passage highlighted, the preview
cites it with exactly the same object, and a passage that is gone, or an id
that is not one, gets a clear answer.
"""

import uuid

from fastapi.testclient import TestClient

from tests import pdfs

LECTURE = pdfs.html_pdf(
    "<h2>Scheduling</h2><p>Round robin gives every task a time quantum.</p>",
    "<h2>Deadlock</h2><p>Four conditions cause a deadlock.</p>",
)


def environment(client: TestClient) -> str:
    return client.post("/api/environments", json={"name": "Operating Systems"}).json()[
        "id"
    ]


def upload(client: TestClient, env: str) -> dict:
    response = client.post(
        f"/api/environments/{env}/documents",
        params={"filename": "Lecture 4.pdf"},
        content=LECTURE,
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_search_result_opens_to_its_page_with_the_passage_highlighted(
    client: TestClient,
):
    env = environment(client)
    upload(client, env)
    [result, *_] = client.post(
        "/api/search", json={"environment_id": env, "query": "deadlock"}
    ).json()["results"]
    citation = result["citation"]

    response = client.get(f"/api/chunks/{citation['chunk_id']}/preview")

    assert response.status_code == 200
    preview = response.json()
    assert preview["citation"] == citation  # the same source object everywhere
    assert (citation["filename"], citation["page_start"]) == ("Lecture 4.pdf", 2)
    [page] = preview["pages"]
    assert page["page_number"] == 2
    start, end = page["highlight_start"], page["highlight_end"]
    assert page["content"][start:end] == citation["excerpt"]


def test_a_passage_whose_document_was_deleted_is_a_404_with_the_reason(
    client: TestClient,
):
    env = environment(client)
    document = upload(client, env)
    chunk_id = client.get(f"/api/documents/{document['id']}/chunks").json()[0]["id"]
    client.delete(f"/api/documents/{document['id']}")

    response = client.get(f"/api/chunks/{chunk_id}/preview")

    assert response.status_code == 404
    assert "no longer in its document" in response.json()["detail"]


def test_an_unknown_chunk_is_a_404_and_a_malformed_id_a_422(client: TestClient):
    assert client.get(f"/api/chunks/{uuid.uuid4()}/preview").status_code == 404
    assert client.get("/api/chunks/not-a-uuid/preview").status_code == 422

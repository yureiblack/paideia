"""Tests for the document endpoints in app/routers/documents.py.

Purpose: prove the HTTP contract the Materials tab relies on: uploading as a
raw body, the status a document passes through, page text, and the 404, 409,
413, 415 and 422 errors. Requests run through the real app, parser and
storage, against the test database and a temporary data folder.
"""

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, DocumentPage
from tests import pdfs


def new_environment(client: TestClient, name: str = "Operating Systems") -> str:
    return client.post("/api/environments", json={"name": name}).json()["id"]


def upload(
    client: TestClient, environment_id: str, data: bytes, filename="lecture.pdf"
):
    return client.post(
        f"/api/environments/{environment_id}/documents",
        params={"filename": filename},
        content=data,
        headers={"Content-Type": "application/pdf"},
    )


def uploaded(
    client: TestClient, environment_id: str, data: bytes, filename="lecture.pdf"
):
    response = upload(client, environment_id, data, filename)
    assert response.status_code == 201, response.text
    return response.json()


def current(client: TestClient, document: dict) -> dict:
    return client.get(f"/api/documents/{document['id']}").json()


@pytest.fixture
def env(client: TestClient) -> str:
    return new_environment(client)


# --- upload and parse -------------------------------------------------------


def test_upload_answers_at_once_then_parses_in_the_background(
    client: TestClient, env: str
):
    response = upload(client, env, pdfs.pdf("Processes", "Threads"))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "uploaded"
    assert body["filename"] == "lecture.pdf"
    assert body["environment_id"] == env
    # The test client runs background tasks before returning, so the parse
    # has finished by now.
    after = current(client, body)
    assert after["status"] == "ready"
    assert after["page_count"] == 2
    assert after["pages_with_text"] == 2


def test_pages_come_back_numbered_and_in_order(client: TestClient, env: str):
    document = uploaded(client, env, pdfs.pdf("One", "Two", "Three"))

    pages = client.get(f"/api/documents/{document['id']}/pages").json()

    assert [page["page_number"] for page in pages] == [1, 2, 3]
    assert [page["content"].strip() for page in pages] == ["One", "Two", "Three"]


def test_list_shows_the_environments_documents_only(client: TestClient, env: str):
    other = new_environment(client, "Economics")
    mine = {uploaded(client, env, pdfs.pdf(name))["id"] for name in ["a", "b"]}
    uploaded(client, other, pdfs.pdf("c"))

    listed = {d["id"] for d in client.get(f"/api/environments/{env}/documents").json()}

    assert listed == mine


def test_text_containing_nul_characters_is_stored(client: TestClient, env: str):
    # Postgres refuses NUL in text; without the parser stripping it, this
    # perfectly good PDF would fail with a database error.
    document = uploaded(client, env, pdfs.pdf("a\x00b"))

    assert current(client, document)["status"] == "ready"
    pages = client.get(f"/api/documents/{document['id']}/pages").json()
    assert pages[0]["content"].strip() == "ab"


def test_a_scanned_pdf_is_ready_with_no_text(client: TestClient, env: str):
    document = current(client, uploaded(client, env, pdfs.scanned_pdf()))

    assert (document["status"], document["pages_with_text"]) == ("ready", 0)


def test_a_repaired_pdf_is_ready_and_flagged(client: TestClient, env: str):
    document = current(client, uploaded(client, env, pdfs.cut(pdfs.long_pdf(200), 0.9)))

    assert (document["status"], document["repaired"]) == ("ready", True)


def test_a_password_protected_pdf_fails_with_a_reason(client: TestClient, env: str):
    document = current(client, uploaded(client, env, pdfs.encrypted_pdf()))

    assert document["status"] == "failed"
    assert document["error"] == "The PDF is password-protected."


# --- refused uploads --------------------------------------------------------


def test_the_same_file_twice_is_a_409_naming_the_first(client: TestClient, env: str):
    data = pdfs.pdf("x")  # one set of bytes; each generated PDF has a random id
    uploaded(client, env, data, "first.pdf")

    response = upload(client, env, data, "second.pdf")

    assert response.status_code == 409
    assert "first.pdf" in response.json()["detail"]


def test_the_same_file_in_another_environment_is_fine(client: TestClient, env: str):
    data = pdfs.pdf("x")
    uploaded(client, env, data)

    assert upload(client, new_environment(client, "Economics"), data).status_code == 201


def test_a_declared_oversize_is_refused_with_413(
    client: TestClient, env: str, monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    response = upload(client, env, b"%PDF-1.7\n" + b"x" * (2 * 1024 * 1024))

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]
    assert client.get(f"/api/environments/{env}/documents").json() == []


def test_an_undeclared_oversize_is_stopped_while_streaming(
    client: TestClient, env: str, monkeypatch: pytest.MonkeyPatch, data_dir: Path
):
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    def chunks():  # a generator body has no Content-Length
        yield b"%PDF-1.7\n"
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    response = client.post(
        f"/api/environments/{env}/documents",
        params={"filename": "big.pdf"},
        content=chunks(),
    )

    assert response.status_code == 413
    assert list((data_dir / "tmp").glob("*")) == []


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"hello, not a pdf\n" * 200, id="text"),
        pytest.param(pdfs.png(), id="png renamed .pdf"),
    ],
)
def test_a_non_pdf_is_refused_with_415(client: TestClient, env: str, data: bytes):
    response = upload(client, env, data)

    assert response.status_code == 415
    assert client.get(f"/api/environments/{env}/documents").json() == []


def test_a_path_in_the_filename_is_reduced_to_the_name(client: TestClient, env: str):
    document = uploaded(client, env, pdfs.pdf("x"), filename="../../etc/notes.pdf")

    assert document["filename"] == "notes.pdf"


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({}, id="missing"),
        pytest.param({"filename": ""}, id="empty"),
        pytest.param({"filename": "/"}, id="a path with no name"),
        pytest.param({"filename": "x" * 256}, id="too long"),
    ],
)
def test_a_bad_filename_is_a_422(client: TestClient, env: str, params: dict):
    response = client.post(
        f"/api/environments/{env}/documents", params=params, content=pdfs.pdf("x")
    )

    assert response.status_code == 422


def test_uploading_into_an_unknown_environment_is_a_404(client: TestClient):
    assert upload(client, str(uuid.uuid4()), pdfs.pdf("x")).status_code == 404


def test_the_api_docs_offer_a_file_picker_for_uploads(client: TestClient):
    spec = client.get("/openapi.json").json()
    body = spec["paths"]["/api/environments/{environment_id}/documents"]["post"][
        "requestBody"
    ]

    assert body["content"]["application/pdf"]["schema"]["format"] == "binary"


# --- reprocess --------------------------------------------------------------


def test_reprocess_queues_a_failed_document_again(client: TestClient, env: str):
    document = uploaded(client, env, pdfs.encrypted_pdf())

    response = client.post(f"/api/documents/{document['id']}/reprocess")

    assert response.status_code == 202
    assert response.json()["status"] == "uploaded"
    assert current(client, document)["status"] == "failed"  # still locked, still fails


def test_reprocess_during_a_live_parse_is_a_409(
    client: TestClient, env: str, session: Session
):
    document = uploaded(client, env, pdfs.pdf("x"))
    row = session.get(Document, uuid.UUID(document["id"]))
    row.status = "processing"
    session.commit()

    response = client.post(f"/api/documents/{document['id']}/reprocess")

    assert response.status_code == 409


# --- chunks -----------------------------------------------------------------


LECTURE = pdfs.html_pdf(
    "<h1>Processes</h1><p>A process is a program in execution.</p>"
    "<h2>States</h2><p>New, ready, running, waiting and terminated.</p>",
    "<h2>Scheduling</h2><p>The scheduler picks the next ready process.</p>",
)


def test_chunks_follow_the_headings_in_reading_order(client: TestClient, env: str):
    document = uploaded(client, env, LECTURE)

    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()

    # Each heading with a paragraph under it opens its own chunk.
    assert [c["ordinal"] for c in chunks] == [0, 1, 2]
    assert [c["heading"] for c in chunks] == ["Processes", "States", "Scheduling"]
    assert chunks[0]["content"] == "Processes\n\nA process is a program in execution."
    assert (chunks[2]["page_start"], chunks[2]["page_end"]) == (2, 2)


def test_chunk_offsets_point_at_their_text_in_the_pages(client: TestClient, env: str):
    document = uploaded(client, env, LECTURE)
    pages = {
        p["page_number"]: p["content"]
        for p in client.get(f"/api/documents/{document['id']}/pages").json()
    }

    for chunk in client.get(f"/api/documents/{document['id']}/chunks").json():
        assert chunk["page_start"] == chunk["page_end"]
        text = pages[chunk["page_start"]][chunk["char_start"] : chunk["char_end"]]
        assert text == chunk["content"]


def test_reprocessing_the_same_pdf_gives_the_same_chunks(client: TestClient, env: str):
    # The roadmap's acceptance test: run 1 gives N chunks, run 2 the same
    # identities, no duplicates.
    document = uploaded(client, env, LECTURE)
    first = client.get(f"/api/documents/{document['id']}/chunks").json()

    client.post(f"/api/documents/{document['id']}/reprocess")
    second = client.get(f"/api/documents/{document['id']}/chunks").json()

    assert [c["id"] for c in second] == [c["id"] for c in first]


# --- read and delete --------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("get", "/pages"),
        ("get", "/chunks"),
        ("post", "/reprocess"),
        ("delete", ""),
    ],
)
def test_an_unknown_document_is_a_404(client: TestClient, method: str, suffix: str):
    response = getattr(client, method)(f"/api/documents/{uuid.uuid4()}{suffix}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_delete_removes_the_document_pages_and_file(
    client: TestClient, env: str, session: Session, data_dir: Path
):
    document = uploaded(client, env, pdfs.pdf("a", "b"))
    path = data_dir / "uploads" / env / f"{document['id']}.pdf"
    assert path.exists()

    response = client.delete(f"/api/documents/{document['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/documents/{document['id']}").status_code == 404
    pages = select(func.count()).where(
        DocumentPage.document_id == uuid.UUID(document["id"])
    )
    assert session.scalar(pages) == 0
    assert not path.exists()


def test_deleting_an_environment_removes_only_its_documents_and_files(
    client: TestClient, session: Session, data_dir: Path
):
    # Acceptance criterion: deleting an environment removes only its data.
    doomed, kept = new_environment(client, "Doomed"), new_environment(client, "Kept")
    gone = uploaded(client, doomed, pdfs.pdf("a"))
    stays = uploaded(client, kept, pdfs.pdf("b"))

    client.delete(f"/api/environments/{doomed}")

    assert client.get(f"/api/documents/{gone['id']}").status_code == 404
    assert not (data_dir / "uploads" / doomed).exists()
    assert current(client, stays)["status"] == "ready"
    assert len(client.get(f"/api/documents/{stays['id']}/pages").json()) == 1
    assert (data_dir / "uploads" / kept / f"{stays['id']}.pdf").exists()

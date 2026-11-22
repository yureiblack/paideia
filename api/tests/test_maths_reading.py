"""Tests for reading a document's maths (decision record 26): the endpoints in
app/routers/documents.py, the job in app/services/maths_reading.py, and the
document read again with the pages read.

Purpose: prove the whole reading end to end with a scripted model. The offer
lists the pages with maths and an estimate; a reading that agrees with the
PDF's text puts the maths in the pages and passages as LaTeX; one that
disagrees, even read again in halves, leaves the page as it was and says
why; cancelling changes nothing; a reading carries on from the pages already
read; the model being unreachable is reported in its own words; and a new
version of the file is never read with another version's pages.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Document, Job, PageTranscription
from app.routers.deps import get_dispatcher, get_llm
from app.services import maths_reading
from tests import pdfs
from tests.fakes import FailingProvider
from tests.test_documents_api import new_environment, uploaded
from tests.test_jobs import Recording

PROSE = "The characteristic polynomial of the matrix is"
FORMULA = "l2 - 6l + 1 = 0"  # set in the Symbol font: the text layer reads it so
FAITHFUL = f"{PROSE}\n\n$$l^2 - 6l + 1 = 0$$"
WRONG = f"{PROSE}\n\n$$l^2 - 5l + 1 = 0$$"  # a digit misread


@pytest.fixture
def document(client: TestClient) -> dict:
    """A ready document whose first page holds maths and second does not."""
    environment = new_environment(client)
    return uploaded(
        client,
        environment,
        pdfs.maths_pdf((PROSE, FORMULA), "A second page, of prose only."),
    )


def read_maths(client: TestClient, document: dict, first=1, last=2):
    return client.post(
        f"/api/documents/{document['id']}/maths",
        json={"first_page": first, "last_page": last},
    )


def maths(client: TestClient, document: dict) -> dict:
    response = client.get(f"/api/documents/{document['id']}/maths")
    assert response.status_code == 200, response.text
    return response.json()


def page(client: TestClient, document: dict, number: int) -> str:
    return client.get(f"/api/documents/{document['id']}/pages").json()[number - 1][
        "content"
    ]


def last_update(client: TestClient, document: dict) -> dict:
    updates = client.get(
        f"/api/environments/{document['environment_id']}/updates"
    ).json()
    return updates[0]


# --- the offer -------------------------------------------------------------------


def test_the_offer_lists_the_maths_pages_and_how_long_a_page_takes(client, document):
    assert maths(client, document) == {
        "maths_pages": [1],
        "read": [],
        "waiting": [],
        "kept_text": [],
        "seconds_per_page": 65.0,
    }


def test_a_document_not_read_yet_has_no_maths_to_offer(client):
    environment = new_environment(client)
    broken = uploaded(client, environment, pdfs.encrypted_pdf())

    assert client.get(f"/api/documents/{broken['id']}/maths").status_code == 409
    assert read_maths(client, broken, 1, 1).status_code == 409


# --- reading ---------------------------------------------------------------------


def test_a_faithful_reading_puts_the_maths_in_the_page_and_its_passages(
    client, document, llm
):
    llm.transcription = FAITHFUL

    response = read_maths(client, document)

    assert response.status_code == 202, response.text
    assert response.json()["kind"] == "maths"
    assert len(llm.images) == 1  # page 1 only: page 2 holds no maths
    assert page(client, document, 1) == f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]"
    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()
    assert any("\\[l^2 - 6l + 1 = 0\\]" in chunk["content"] for chunk in chunks)
    assert maths(client, document)["read"] == [1]

    update = last_update(client, document)
    assert update["kind"] == "maths"
    assert update["status"] == "done"
    assert update["steps"][0] == {
        "name": "maths",
        "label": "Reading the maths",
        "state": "done",
        "detail": "1 of 1 page read.",
    }
    assert update["steps"][1]["name"] == "read"
    assert update["steps"][1]["state"] == "done"


def test_a_page_that_disagrees_twice_keeps_the_pdfs_text_and_says_why(
    client, document, llm
):
    llm.transcription = WRONG

    read_maths(client, document)

    assert len(llm.images) == 3  # the page whole, then its two halves
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    kept = maths(client, document)["kept_text"]
    assert [k["page"] for k in kept] == [1]
    assert kept[0]["reason"].startswith("Its digits differ from the PDF's text")
    assert last_update(client, document)["steps"][0]["detail"] == (
        "0 of 1 page read. Page 1 keeps the PDF's own text."
    )


def test_a_page_read_in_halves_is_kept_when_the_halves_agree(client, document, llm):
    answers = iter([WRONG, PROSE, "$$l^2 - 6l + 1 = 0$$"])
    llm.transcription = lambda prompt, image: next(answers)

    read_maths(client, document)

    assert maths(client, document)["read"] == [1]
    assert page(client, document, 1) == f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]"


def test_a_sentence_of_the_models_own_before_either_half_is_dropped(
    client, document, llm
):
    answers = iter(
        [
            WRONG,
            f"Here is the transcription of the page in Markdown:\n\n{PROSE}",
            (
                "The following is the transcription of the image in LaTeX:\n\n"
                "$$l^2 - 6l + 1 = 0$$"
            ),
        ]
    )
    llm.transcription = lambda prompt, image: next(answers)

    read_maths(client, document)

    assert maths(client, document)["read"] == [1]


def test_reading_the_document_again_keeps_its_maths(client, document, llm):
    llm.transcription = FAITHFUL
    read_maths(client, document)

    response = client.post(f"/api/documents/{document['id']}/reprocess")

    assert response.status_code == 202
    assert page(client, document, 1) == f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]"


def test_a_new_version_is_never_read_with_the_old_versions_pages(client, document, llm):
    llm.transcription = FAITHFUL
    read_maths(client, document)

    client.post(
        f"/api/documents/{document['id']}/versions",
        content=pdfs.maths_pdf((PROSE, FORMULA), "A second page, changed."),
        headers={"Content-Type": "application/pdf"},
    )

    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    assert maths(client, document)["read"] == []


# --- what is refused ---------------------------------------------------------------


def test_pages_already_read_are_not_read_again(client, document, llm):
    llm.transcription = FAITHFUL
    read_maths(client, document)

    response = read_maths(client, document)

    assert response.status_code == 409
    assert (
        response.json()["detail"] == "The maths of these pages has been read already."
    )


def test_pages_without_maths_are_refused(client, document):
    response = read_maths(client, document, 2, 2)

    assert response.status_code == 409
    assert response.json()["detail"] == "These pages hold no maths to read."


@pytest.mark.parametrize("first, last", [(1, 3), (2, 1), (0, 1)])
def test_pages_outside_the_document_are_refused(client, document, first, last):
    assert read_maths(client, document, first, last).status_code == 422


# --- stopping and carrying on -------------------------------------------------------


def test_cancelling_a_reading_changes_nothing(client, document, session: Session):
    app.dependency_overrides[get_dispatcher] = Recording  # nothing runs by itself
    job = read_maths(client, document).json()

    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()

    assert cancelled["status"] == "cancelled"
    update = last_update(client, document)
    assert update["status"] == "cancelled"
    chain = session.execute(
        select(Job.kind, Job.status).where(Job.update_id == update["id"])
    ).all()
    assert sorted(chain) == [
        ("derive", "cancelled"),
        ("maths", "cancelled"),
        ("read", "cancelled"),
    ]
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    assert session.get(Document, document["id"]).status == "ready"


def test_a_reading_carries_on_from_the_pages_already_read(
    client, document, llm, session: Session
):
    # A reading cancelled after its first page: the page was read and kept,
    # but never put in place.
    session.add(
        PageTranscription(
            document_id=document["id"],
            sha256=document["sha256"],
            page_number=1,
            status="accepted",
            content=f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]",
            blocks=[[0, len(PROSE), False], [len(PROSE) + 2, len(PROSE) + 27, False]],
            attempts=1,
            model=llm.model_name,
            prompt_version="page_transcription/v1",
            seconds=40.0,
        )
    )
    session.commit()
    # Not in place yet, so not yet read, as far as the learner can see; but
    # reading it again takes no time.
    offer = maths(client, document)
    assert (offer["read"], offer["waiting"]) == ([], [1])

    response = read_maths(client, document)

    assert response.status_code == 202, response.text
    assert llm.images == []  # nothing read again
    assert page(client, document, 1) == f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]"
    # The estimate is now this machine's own.
    assert maths(client, document)["seconds_per_page"] == 40.0


def test_a_page_already_read_is_not_read_again_when_a_job_runs_twice(
    client, document, llm, session_factory
):
    # A job that crashed after storing a page, and runs again from that page.
    llm.transcription = FAITHFUL
    for _ in range(2):
        status = maths_reading.transcribe_page(
            session_factory, uuid.UUID(document["id"]), 1, llm
        )

    assert status == "accepted"
    assert len(llm.images) == 1


def test_the_model_unreachable_is_reported_in_its_own_words(client, document):
    app.dependency_overrides[get_llm] = FailingProvider

    job = read_maths(client, document).json()

    jobs = client.get(f"/api/environments/{document['environment_id']}/jobs").json()
    reading = next(j for j in jobs if j["id"] == job["id"])
    assert reading["status"] == "queued"  # tried again later
    assert reading["error"] == "Could not reach Ollama. Is it running? Trying again."
    step = last_update(client, document)["steps"][0]
    assert step["state"] == "failed"
    assert step["detail"] == "Could not reach Ollama. Is it running?"
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"

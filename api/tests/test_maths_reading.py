"""Tests for reading a document's maths with the document (decision records
26 and 31): the chain queued in app/routers/documents.py, the job steps in
app/services/maths_reading.py, and the document read again with the pages
read.

Purpose: prove the whole reading end to end with a scripted model. A
document's text is read first; then each page that sets maths is read by the
model, and the document read again with it, before its summary; a page that
agrees with the PDF's text puts its maths in the page and passages as LaTeX;
one that disagrees, even read again in halves, keeps the page as it was and
the update says why; cancelling the maths skips it and the chain goes on,
and reading the document again later reads what was left; cancelling the
document's reading cancels it all; the model being unreachable is reported
in its own words; and a new version of the file is never read with another
version's pages.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Document, Job
from app.parsing import PyMuPDFParser
from app.routers.deps import get_dispatcher, get_llm
from app.services import jobs, maths_reading
from tests import pdfs
from tests.fakes import FailingProvider
from tests.test_documents_api import new_environment, uploaded
from tests.test_jobs import Recording

PROSE = "The characteristic polynomial of the matrix is"
FORMULA = "l2 - 6l + 1 = 0"  # set in the Symbol font: the text layer reads it so
FAITHFUL = f"{PROSE}\n\n$$l^2 - 6l + 1 = 0$$"
WRONG = f"{PROSE}\n\n$$l^2 - 5l + 1 = 0$$"  # a digit misread
READ = f"{PROSE}\n\n\\[l^2 - 6l + 1 = 0\\]"
MATHS_PDF = pdfs.maths_pdf((PROSE, FORMULA), "A second page, of prose only.")


def upload(client: TestClient) -> dict:
    """A document whose first page holds maths and second does not."""
    return uploaded(client, new_environment(client), MATHS_PDF)


def page(client: TestClient, document: dict, number: int) -> str:
    return client.get(f"/api/documents/{document['id']}/pages").json()[number - 1][
        "content"
    ]


def last_update(client: TestClient, document: dict) -> dict:
    updates = client.get(
        f"/api/environments/{document['environment_id']}/updates"
    ).json()
    return updates[0]


def maths_step(update: dict) -> dict:
    return next(s for s in update["steps"] if s["name"] == "maths")


def chain(session: Session, update: dict) -> list[tuple[str, str]]:
    return list(
        session.execute(
            select(Job.kind, Job.status)
            .where(Job.update_id == update["id"])
            .order_by(Job.created_at)
        ).all()
    )


def run_queued(session_factory, llm, embedder) -> None:
    """Run the queued jobs as the worker would, oldest first."""
    tools = jobs.Tools(session_factory, llm, embedder, PyMuPDFParser())
    with session_factory() as session:
        queued = session.scalars(
            select(Job.id).where(Job.status == "queued").order_by(Job.created_at)
        ).all()
    for job_id in queued:
        jobs.run_now(tools, job_id)


# --- read with the document ------------------------------------------------------


def test_a_documents_maths_is_read_with_it_before_its_summary(client, llm, session):
    llm.transcription = FAITHFUL

    document = upload(client)

    assert len(llm.images) == 1  # page 1 only: page 2 holds no maths
    assert page(client, document, 1) == READ
    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()
    assert any("\\[l^2 - 6l + 1 = 0\\]" in chunk["content"] for chunk in chunks)

    update = last_update(client, document)
    assert (update["kind"], update["status"]) == ("added", "done")
    assert [s["name"] for s in update["steps"]] == [
        "read",
        "maths",
        "document_summary",
        "environment_summary",
        "concepts",
        "knowledge_graph",
        "roadmap",
    ]
    assert maths_step(update) == {
        "name": "maths",
        "label": "Reading the maths",
        "state": "done",
        "detail": "1 of 1 page read.",
    }
    # The text first, readable at once; then the maths, the text again with
    # it, and what is made from it.
    assert chain(session, update) == [
        ("read", "succeeded"),
        ("vision", "succeeded"),
        ("read", "succeeded"),
        ("derive", "succeeded"),
    ]


def test_a_document_without_maths_or_figures_is_read_as_before(client, llm, session):
    document = uploaded(client, new_environment(client), pdfs.pdf("Processes"))

    update = last_update(client, document)
    assert "maths" not in [s["name"] for s in update["steps"]]
    assert chain(session, update) == [("read", "succeeded"), ("derive", "succeeded")]
    assert llm.images == []


def test_a_page_that_disagrees_twice_keeps_the_pdfs_text_and_says_why(client, llm):
    llm.transcription = WRONG

    document = upload(client)

    assert len(llm.images) == 3  # the page whole, then its two halves
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    assert maths_step(last_update(client, document))["detail"] == (
        "0 of 1 page read. Page 1 keeps the PDF's own text."
    )


def test_a_page_read_in_halves_is_kept_when_the_halves_agree(client, llm):
    answers = iter([WRONG, PROSE, "$$l^2 - 6l + 1 = 0$$"])
    llm.transcription = lambda prompt, image: next(answers)

    document = upload(client)

    assert page(client, document, 1) == READ


def test_a_sentence_of_the_models_own_before_either_half_is_dropped(client, llm):
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

    document = upload(client)

    assert page(client, document, 1) == READ


def test_reading_the_document_again_keeps_its_maths_and_reads_nothing_again(
    client, llm, session
):
    llm.transcription = FAITHFUL
    document = upload(client)

    response = client.post(f"/api/documents/{document['id']}/reprocess")

    assert response.status_code == 202
    assert page(client, document, 1) == READ
    assert len(llm.images) == 1
    update = last_update(client, document)
    assert update["kind"] == "reprocessed"
    assert "maths" not in [s["name"] for s in update["steps"]]
    assert chain(session, update) == [("read", "succeeded"), ("derive", "succeeded")]


def test_a_new_version_is_never_read_with_the_old_versions_pages(client, llm):
    llm.transcription = FAITHFUL
    document = upload(client)
    llm.transcription = WRONG  # the new version's page 1 is read afresh

    client.post(
        f"/api/documents/{document['id']}/versions",
        content=pdfs.maths_pdf((PROSE, FORMULA), "A second page, changed."),
        headers={"Content-Type": "application/pdf"},
    )

    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    assert len(llm.images) == 1 + 3


# --- stopping and carrying on -------------------------------------------------------


def test_cancelling_the_maths_skips_it_and_the_chain_goes_on(
    client, llm, embedder, session, session_factory
):
    app.dependency_overrides[get_dispatcher] = Recording  # nothing runs by itself
    llm.transcription = FAITHFUL
    document = upload(client)
    update = last_update(client, document)
    vision = session.scalars(
        select(Job).where(Job.update_id == update["id"], Job.kind == "vision")
    ).one()

    cancelled = client.post(f"/api/jobs/{vision.id}/cancel").json()
    run_queued(session_factory, llm, embedder)

    assert cancelled["status"] == "cancelled"
    assert llm.images == []
    update = last_update(client, document)
    assert update["status"] == "done"
    assert chain(session, update) == [
        ("read", "succeeded"),
        ("vision", "cancelled"),
        ("read", "succeeded"),
        ("derive", "succeeded"),
    ]
    assert maths_step(update)["detail"] == (
        "0 of 1 page read. 1 not read, as the reading stopped."
    )
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"

    # Reading it again reads what was left.
    app.dependency_overrides[get_dispatcher] = jobs.InlineDispatcher
    client.post(f"/api/documents/{document['id']}/reprocess")

    assert page(client, document, 1) == READ
    assert len(llm.images) == 1


def test_cancelling_the_documents_reading_cancels_it_all(
    client, llm, session, session_factory
):
    app.dependency_overrides[get_dispatcher] = Recording
    llm.transcription = FAITHFUL
    document = upload(client)
    update = last_update(client, document)
    first = session.scalars(
        select(Job)
        .where(Job.update_id == update["id"], Job.kind == "read")
        .order_by(Job.created_at)
    ).first()
    assert first is not None

    client.post(f"/api/jobs/{first.id}/cancel")

    assert last_update(client, document)["status"] == "cancelled"
    assert {status for _, status in chain(session, update)} == {"cancelled"}


def test_a_page_already_read_is_not_read_again_when_a_job_runs_twice(
    client, llm, session_factory
):
    # A job that crashed after storing a page, and runs again from that page.
    llm.transcription = FAITHFUL
    document = upload(client)
    for _ in range(2):
        status = maths_reading.transcribe_page(
            session_factory, uuid.UUID(document["id"]), 1, llm
        )

    assert status == "accepted"
    assert len(llm.images) == 1


def test_the_model_unreachable_is_reported_in_its_own_words(client, session):
    app.dependency_overrides[get_llm] = FailingProvider

    document = upload(client)

    update = last_update(client, document)
    [vision] = session.scalars(
        select(Job).where(Job.update_id == update["id"], Job.kind == "vision")
    ).all()
    assert vision.status == "queued"  # tried again later
    assert vision.error == "Could not reach Ollama. Is it running? Trying again."
    step = maths_step(update)
    assert step["state"] == "failed"
    assert step["detail"] == "Could not reach Ollama. Is it running?"
    # The text was read meanwhile, and can be read.
    assert page(client, document, 1) == f"{PROSE}\n\n{FORMULA}"
    assert session.get(Document, document["id"]).status == "ready"

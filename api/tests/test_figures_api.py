"""Tests for reading a document's figures with the document (decision
records 29 and 31): the chain queued in app/routers/documents.py, the job
steps in app/services/figures.py, and the document read again with the
figures read.

Purpose: prove the whole reading end to end with a scripted model. Every
figure is read once the text is; each, read or not, is a place in its page
where the reader shows its picture; a reading that agrees with the figure
takes the place of its caption and labels as a passage of its own, without
the model's description, found by search and read by the summary; one that
gives a number the figure does not show is asked again, and if it still
does the page keeps the PDF's text and the update says why; a table is read
as rows; the figure's picture is served for its version of the file only;
and a figure read already is not read again.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import parsing
from app.models import Document, Job
from app.services import summaries
from tests import pdfs
from tests.test_documents_api import new_environment, uploaded

CAPTION = "Figure 1. A drawn figure with two labels."
DESCRIPTION = (
    "A square crossed by a diagonal, p1 at its top left and p2 at its bottom right."
)
FIGURE_1 = f"KIND\ndiagram\n\nTEXT\np1\np2\n\nTABLE\nnone\n\nDESCRIPTION\n{DESCRIPTION}"
MADE_UP = FIGURE_1.replace("bottom right.", "bottom right, 7 units apart.")
FIGURE_2 = "KIND\ndiagram\n\nTEXT\n(a) Before.\n(b) After.\n\nDESCRIPTION\nTwo circles."
TABLE_1 = (
    "KIND\ntable\n\nTEXT\nnone\n\nTABLE\n| Name | Value |\n|---|---|\n"
    "| alpha | 12 |\n| beta | 34 |\n\nDESCRIPTION\nTwo names with their values."
)
FIGURE_4 = "KIND\nchart\n\nTEXT\n1\n2\n3\n4\n\nDESCRIPTION\nLines of four lengths."
UNUSABLE = "I cannot tell."
CAPTIONS = {
    CAPTION: FIGURE_1,
    "Figure 2. Two parts of one figure.": FIGURE_2,
    "Table 1. Some values.": TABLE_1,
    "Figure 4. Lines of four lengths.": FIGURE_4,
}
PASSAGE = f"{CAPTION} Diagram: p1; p2."


def by_figure(answers: dict[str, str]):
    """The model's answer for each figure of the PDF, told apart by its
    picture: as answers names it by caption, else one that is no reading."""
    path = Path(tempfile.mkdtemp()) / "figures.pdf"
    path.write_bytes(pdfs.figures_pdf())
    captions = {
        parsing.figure_image(path, f): f.caption or "" for f in parsing.figures(path)
    }

    def answer(prompt, image):
        return answers.get(captions.get(image, ""), UNUSABLE)

    return answer


def upload(client: TestClient, llm, answers: dict[str, str]) -> dict:
    """A document laid out as a textbook sets its figures, read with these
    answers."""
    llm.transcription = by_figure(answers)
    return uploaded(client, new_environment(client), pdfs.figures_pdf())


def pages(client: TestClient, document: dict) -> list[dict]:
    return client.get(f"/api/documents/{document['id']}/pages").json()


def last_update(client: TestClient, document: dict) -> dict:
    return client.get(f"/api/environments/{document['environment_id']}/updates").json()[
        0
    ]


def figures_step(update: dict) -> dict:
    return next(s for s in update["steps"] if s["name"] == "figures")


def picture(client: TestClient, document: dict, key: str, version=None):
    return client.get(
        f"/api/documents/{document['id']}/figures/{key}/image",
        params={"version": version or document["sha256"]},
    )


# --- read with the document ------------------------------------------------------


def test_every_figure_is_read_with_the_document(client, llm, session):
    document = upload(client, llm, CAPTIONS)

    assert len(llm.images) == 4
    update = last_update(client, document)
    assert (update["kind"], update["status"]) == ("added", "done")
    assert [s["name"] for s in update["steps"]][:3] == [
        "read",
        "figures",
        "document_summary",
    ]
    assert figures_step(update) == {
        "name": "figures",
        "label": "Reading the figures",
        "state": "done",
        "detail": "4 of 4 figures read.",
    }
    kinds = session.execute(
        select(Job.kind, Job.title)
        .where(Job.update_id == update["id"])
        .order_by(Job.created_at)
    ).all()
    assert kinds == [
        ("read", "Reading lecture.pdf"),
        ("vision", "Reading the figures of lecture.pdf"),
        ("read", "Reading lecture.pdf with its figures"),
        ("derive", "Updating from lecture.pdf"),
    ]


def test_a_faithful_reading_takes_the_place_of_the_figures_text(client, llm):
    document = upload(client, llm, {CAPTION: FIGURE_1})

    first = pages(client, document)[0]
    assert first["content"].split("\n\n") == [
        pdfs.PROSE,
        PASSAGE,  # in place of the labels and the caption
        pdfs.PROSE,
        "Figure 3 shows the next idea. " + pdfs.PROSE,
    ]
    [figure] = first["figures"]
    assert figure["key"].startswith("1:")
    assert figure["caption"] == CAPTION
    assert first["content"][figure["start"] : figure["end"]] == PASSAGE
    assert DESCRIPTION not in first["content"]


def test_every_figure_is_a_place_for_its_picture_read_or_not(client, llm):
    # None of page 2's figures is read: their text stays, gathered.
    document = upload(client, llm, {CAPTION: FIGURE_1})

    second = pages(client, document)[1]
    assert [f["caption"] for f in second["figures"]] == [
        "Figure 2. Two parts of one figure.",
        "Table 1. Some values.",
    ]
    table = second["figures"][1]
    shown = second["content"][table["start"] : table["end"]]
    assert shown.startswith("Table 1. Some values.")
    assert shown.split() == ["Table", "1.", "Some", "values.", "Name", "Value"] + [
        "alpha",
        "12",
        "beta",
        "34",
    ]
    for figure in second["figures"]:
        response = picture(client, document, figure["key"])
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")


def test_a_figures_passage_is_found_by_search_and_summarised(client, llm, session):
    document = upload(client, llm, {CAPTION: FIGURE_1})

    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()
    [figure] = [c for c in chunks if c["figure_id"]]
    assert figure["content"] == PASSAGE
    assert all(DESCRIPTION not in c["content"] for c in chunks)

    plan = summaries.plan(session, session.get(Document, document["id"]))
    assert str(figure["id"]) in {str(chunk.id) for chunk in plan.chunks}

    results = client.post(
        "/api/search",
        json={
            "environment_id": document["environment_id"],
            "query": "a drawn figure with two labels p1 p2",
        },
    ).json()["results"]
    cited = [r["citation"] for r in results if r["citation"]["figure_id"]]
    assert cited and cited[0]["figure_id"] == figure["figure_id"]
    # Search shows the picture of the figure read.
    response = client.get(f"/api/figures/{figure['figure_id']}/image")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_a_figures_picture_is_served_for_its_version_only(client, llm):
    document = upload(client, llm, {CAPTION: FIGURE_1})
    key = pages(client, document)[0]["figures"][0]["key"]

    response = picture(client, document, key)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert picture(client, document, key, version="0" * 64).status_code == 404
    assert picture(client, document, "1:0,0,1,1").status_code == 404
    assert picture(client, document, "page").status_code == 404
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/figures/{missing}/image").status_code == 404


def test_a_made_up_number_is_asked_again_then_the_page_keeps_its_text(client, llm):
    answers = {**CAPTIONS, CAPTION: MADE_UP}

    document = upload(client, llm, answers)

    assert llm.agains[:2] == [False, True]  # asked once more, differently
    first = pages(client, document)[0]
    assert "p1" in first["content"].split("\n\n")
    [figure] = first["figures"]
    assert first["content"][figure["start"] : figure["end"]].endswith(CAPTION)
    assert figures_step(last_update(client, document))["detail"] == (
        "3 of 4 figures read. One keeps the PDF's own text."
    )
    # Nor does reading the document again put the refused reading in.
    before = first["content"]
    client.post(f"/api/documents/{document['id']}/reprocess")
    assert pages(client, document)[0]["content"] == before


def test_a_figure_read_right_the_second_time_is_kept(client, llm):
    first_time = iter([MADE_UP, FIGURE_1])
    answer = by_figure(CAPTIONS)

    def answers(prompt, image):
        found = answer(prompt, image)
        return next(first_time) if found == FIGURE_1 else found

    llm.transcription = answers
    document = uploaded(client, new_environment(client), pdfs.figures_pdf())

    assert PASSAGE in pages(client, document)[0]["content"]


def test_a_table_is_read_as_rows(client, llm):
    document = upload(client, llm, CAPTIONS)

    second = pages(client, document)[1]
    assert (
        "Table 1. Some values. Table: Name | Value / alpha | 12 / beta | 34."
        in (second["content"])
    )


def test_figures_read_already_are_not_read_again(client, llm, session):
    document = upload(client, llm, CAPTIONS)

    client.post(f"/api/documents/{document['id']}/reprocess")

    assert len(llm.images) == 4
    assert PASSAGE in pages(client, document)[0]["content"]
    update = last_update(client, document)
    assert "figures" not in [s["name"] for s in update["steps"]]


def test_a_new_version_shows_no_figure_of_the_old_one(client, llm, session):
    document = upload(client, llm, CAPTIONS)
    [figure_id] = [
        c["figure_id"]
        for c in client.get(f"/api/documents/{document['id']}/chunks").json()
        if c["figure_id"] and c["content"].startswith(CAPTION)
    ]
    key = pages(client, document)[0]["figures"][0]["key"]

    client.post(
        f"/api/documents/{document['id']}/versions",
        content=pdfs.pdf("A new version, with no figures."),
        headers={"Content-Type": "application/pdf"},
    )

    current = client.get(f"/api/documents/{document['id']}").json()
    assert pages(client, document)[0]["figures"] == []
    assert client.get(f"/api/figures/{figure_id}/image").status_code == 404
    assert picture(client, document, key, current["sha256"]).status_code == 404


@pytest.mark.parametrize("caption", list(CAPTIONS))
def test_each_figure_is_read_from_its_own_picture(client, llm, caption):
    document = upload(client, llm, {caption: CAPTIONS[caption]})

    texts = [p["content"] for p in pages(client, document)]
    assert any(caption + " " in text for text in texts)

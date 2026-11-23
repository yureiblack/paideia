"""Tests for reading a document's figures (decision record 29): the endpoints
in app/routers/documents.py, the job in app/services/figures.py, and the
document read again with the figures read.

Purpose: prove the whole reading end to end with a scripted model. The offer
lists the figures found, with their captions, and an estimate; a reading
that agrees with the figure takes the place of the figure's text in its
page, caption and labels, as one passage of its own, found by search and
never summarised; one that gives a number the figure does not show is asked
again, and if it still does the page keeps the PDF's text and says why; a
table is read as rows; the figure's picture is served; and a figure read
already is not read again.
"""

import pytest
from fastapi.testclient import TestClient

from app.models import Document
from app.services import summaries
from tests import pdfs
from tests.test_documents_api import new_environment, uploaded

CAPTION = "Figure 1. A drawn figure with two labels."
DESCRIPTION = (
    "A square crossed by a diagonal, p1 at its top left and p2 at its bottom right."
)
FIGURE_1 = f"KIND\ndiagram\n\nTEXT\np1\np2\n\nTABLE\nnone\n\nDESCRIPTION\n{DESCRIPTION}"
MADE_UP = FIGURE_1.replace("bottom right.", "bottom right, 7 units apart.")
TABLE_1 = (
    "KIND\ntable\n\nTEXT\nnone\n\nTABLE\n| Name | Value |\n|---|---|\n"
    "| alpha | 12 |\n| beta | 34 |\n\nDESCRIPTION\nTwo names with their values."
)


@pytest.fixture
def document(client: TestClient) -> dict:
    """A ready document laid out as a textbook sets its figures."""
    return uploaded(client, new_environment(client), pdfs.figures_pdf())


def read_figures(client: TestClient, document: dict, first=1, last=1):
    return client.post(
        f"/api/documents/{document['id']}/figures",
        json={"first_page": first, "last_page": last},
    )


def figures(client: TestClient, document: dict) -> dict:
    response = client.get(f"/api/documents/{document['id']}/figures")
    assert response.status_code == 200, response.text
    return response.json()


def pages(client: TestClient, document: dict) -> list[dict]:
    return client.get(f"/api/documents/{document['id']}/pages").json()


def last_update(client: TestClient, document: dict) -> dict:
    return client.get(f"/api/environments/{document['environment_id']}/updates").json()[
        0
    ]


# --- the offer -------------------------------------------------------------------


def test_the_offer_lists_the_figures_with_their_captions(client, document):
    found = figures(client, document)

    assert [(f["page"], f["caption"]) for f in found["figures"]] == [
        (1, CAPTION),
        (2, "Figure 2. Two parts of one figure."),
        (2, "Table 1. Some values."),
        (3, "Figure 4. Lines of four lengths."),
    ]
    assert (found["read"], found["waiting"], found["kept"]) == ([], [], [])
    assert found["seconds_per_figure"] == 20.0


def test_a_document_not_read_yet_has_no_figures_to_offer(client):
    broken = uploaded(client, new_environment(client), pdfs.encrypted_pdf())

    assert client.get(f"/api/documents/{broken['id']}/figures").status_code == 409
    assert read_figures(client, broken).status_code == 409


def test_pages_outside_the_document_are_refused(client, document):
    assert read_figures(client, document, 2, 9).status_code == 422


# --- reading ---------------------------------------------------------------------


def test_a_faithful_reading_takes_the_place_of_the_figures_text(client, document, llm):
    llm.transcription = FIGURE_1

    response = read_figures(client, document)

    assert response.status_code == 202, response.text
    assert response.json()["kind"] == "figures"
    assert len(llm.images) == 1  # page 1 holds one figure
    first = pages(client, document)[0]
    passage = f"{CAPTION} Diagram: p1; p2. Described by the model: {DESCRIPTION}"
    assert first["content"].split("\n\n") == [
        pdfs.PROSE,
        passage,  # in place of the labels and the caption
        pdfs.PROSE,
        "Figure 3 shows the next idea. " + pdfs.PROSE,
    ]
    [figure] = first["figures"]
    assert first["content"][figure["start"] : figure["end"]] == passage
    assert (figure["caption"], figure["kind"], figure["text"]) == (
        CAPTION,
        "diagram",
        ["p1", "p2"],
    )
    assert figure["description"] == DESCRIPTION

    found = figures(client, document)
    assert len(found["read"]) == 1 and found["read"][0].startswith("1:")
    update = last_update(client, document)
    assert (update["kind"], update["status"]) == ("figures", "done")
    assert update["steps"][0] == {
        "name": "figures",
        "label": "Reading the figures",
        "state": "done",
        "detail": "1 of 1 figure read.",
    }


def test_a_figure_is_a_passage_of_its_own_found_by_search_never_summarised(
    client, document, llm, session
):
    llm.transcription = FIGURE_1
    read_figures(client, document)

    chunks = client.get(f"/api/documents/{document['id']}/chunks").json()
    [figure] = [c for c in chunks if c["figure_id"]]
    assert figure["content"].startswith(CAPTION)
    assert "Described by the model" in figure["content"]
    assert all(
        "Described by the model" not in c["content"] for c in chunks if c != figure
    )

    plan = summaries.plan(session, session.get(Document, document["id"]))
    assert all(chunk.figure_id is None for chunk in plan.chunks)

    results = client.post(
        "/api/search",
        json={"environment_id": document["environment_id"], "query": "square diagonal"},
    ).json()["results"]
    cited = [r["citation"] for r in results if r["citation"]["figure_id"]]
    assert cited and cited[0]["figure_id"] == figure["figure_id"]


def test_the_figures_picture_is_served(client, document, llm):
    llm.transcription = FIGURE_1
    read_figures(client, document)
    figure_id = pages(client, document)[0]["figures"][0]["id"]

    response = client.get(f"/api/figures/{figure_id}/image")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/figures/{missing}/image").status_code == 404


def test_a_made_up_number_is_asked_again_then_the_page_keeps_its_text(
    client, document, llm
):
    llm.transcription = MADE_UP
    before = pages(client, document)[0]["content"]

    read_figures(client, document)

    assert llm.agains == [False, True]  # asked once more, differently
    assert pages(client, document)[0]["content"] == before
    [kept] = figures(client, document)["kept"]
    assert (kept["page"], kept["caption"]) == (1, CAPTION)
    assert kept["reason"] == "It gives numbers the figure does not show: 7."
    assert last_update(client, document)["steps"][0]["detail"] == (
        "0 of 1 figure read. One keeps the PDF's own text."
    )
    # Nor does reading the document again put the refused reading in.
    client.post(f"/api/documents/{document['id']}/reprocess")
    assert pages(client, document)[0]["content"] == before
    assert pages(client, document)[0]["figures"] == []


def test_a_figure_read_right_the_second_time_is_kept(client, document, llm):
    answers = iter([MADE_UP, FIGURE_1])
    llm.transcription = lambda prompt, image: next(answers)

    read_figures(client, document)

    assert len(figures(client, document)["read"]) == 1


def test_a_table_is_read_as_rows(client, document, llm):
    answers = iter(
        [
            "KIND\ndiagram\n\nTEXT\n(a) Before.\n(b) After.\n\nDESCRIPTION\nTwo circles.",
            TABLE_1,
        ]
    )
    llm.transcription = lambda prompt, image: next(answers)

    read_figures(client, document, 2, 2)

    second = pages(client, document)[1]
    table = next(f for f in second["figures"] if f["kind"] == "table")
    assert table["tables"] == [
        {"title": None, "rows": [["Name", "Value"], ["alpha", "12"], ["beta", "34"]]}
    ]
    assert "Name | Value / alpha | 12 / beta | 34" in second["content"]


def test_figures_read_already_are_not_read_again(client, document, llm):
    llm.transcription = FIGURE_1
    read_figures(client, document)

    response = read_figures(client, document)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "The figures of these pages have been read already."
    )
    assert len(llm.images) == 1


def test_reading_the_document_again_keeps_its_figures(client, document, llm):
    llm.transcription = FIGURE_1
    read_figures(client, document)

    client.post(f"/api/documents/{document['id']}/reprocess")

    assert pages(client, document)[0]["figures"][0]["description"] == DESCRIPTION


def test_a_new_version_shows_no_figure_of_the_old_one(client, document, llm):
    llm.transcription = FIGURE_1
    read_figures(client, document)
    figure_id = pages(client, document)[0]["figures"][0]["id"]

    client.post(
        f"/api/documents/{document['id']}/versions",
        content=pdfs.pdf("A new version, with no figures."),
        headers={"Content-Type": "application/pdf"},
    )

    assert pages(client, document)[0]["figures"] == []
    assert figures(client, document)["read"] == []
    assert client.get(f"/api/figures/{figure_id}/image").status_code == 404

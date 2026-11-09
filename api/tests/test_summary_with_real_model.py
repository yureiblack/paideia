"""A summary from the real language model, where one is available.

Purpose: the whole path, from an uploaded PDF through Ollama to a stored,
cited summary, written by itself once the document is read, with the
configured model. It needs Ollama running with the model
downloaded, so it is skipped where they are not, which includes CI: there,
an 8B model on machines without a GPU would take minutes per summary. Run it
locally after changing prompts, the model or the summary service.

A real model's wording varies with the model, so the checks are about form
and grounding, not words: plain text, every point cited, and every point
supported by a passage it cites, as judged by the search reranker.
"""

import pytest
from fastapi.testclient import TestClient

from app.llm import default_provider
from app.main import app
from app.reranking import default_reranker
from app.routers.deps import get_llm
from tests import pdfs

PROBLEM = default_provider().check()

pytestmark = pytest.mark.skipif(
    PROBLEM is not None, reason=f"needs the local language model: {PROBLEM}"
)

LECTURE = pdfs.html_pdf(
    "<h2>CPU Scheduling</h2><p>When several tasks are ready, the dispatcher "
    "decides which runs next. Round robin gives each task a fixed time quantum "
    "and then preempts it, moving it to the back of the ready queue. Shortest "
    "job first runs the task with the smallest expected burst, which minimises "
    "average waiting time but can starve long jobs.</p>",
    "<h2>Paging</h2><p>Paging divides physical memory into fixed-size frames and "
    "each address space into pages of the same size. A page table maps every "
    "page to its frame, and a page fault occurs when a page is not resident, so "
    "the kernel loads it from disk.</p>",
    "<h2>Journaling</h2><p>A journaling file system writes a description of each "
    "change to a log before applying it, so after a crash it can replay "
    "committed changes instead of scanning the whole disk.</p>",
)


def test_the_real_model_summarizes_an_uploaded_document_by_itself(client: TestClient):
    # The real model from the start: the upload's background tasks read the
    # document, then write its summary.
    app.dependency_overrides[get_llm] = default_provider
    env = client.post("/api/environments", json={"name": "Operating Systems"}).json()
    document = client.post(
        f"/api/environments/{env['id']}/documents",
        params={"filename": "Lecture 4.pdf"},
        content=LECTURE,
        headers={"Content-Type": "application/pdf"},
    ).json()

    response = client.get(f"/api/documents/{document['id']}/summary")

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["status"] == "ready", summary["error"]
    assert summary["model"] == default_provider().model_name
    points = summary["key_points"]
    assert 3 <= len(points) <= 7
    texts = [summary["overview"], *(p["text"] for p in points)]
    assert not any(mark in text for text in texts for mark in ("**", "##", "\n- "))
    assert all(p["citations"] for p in points)
    assert {c["page_start"] for p in points for c in p["citations"]} == {1, 2, 3}
    reranker = default_reranker()
    for point in points:
        excerpts = [c["excerpt"] for c in point["citations"]]
        assert max(reranker.score(point["text"], excerpts)) >= 0.5, point

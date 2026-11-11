"""A summary from the real language model, where one is available.

Purpose: the whole path, from an uploaded PDF through Ollama to a stored,
cited summary, written by itself once the document is read, the
environment's summary built from it, the document's concepts, the
knowledge graph between them, the learning roadmap and practice items, with
the configured model. It needs Ollama running with the model downloaded, so
it is skipped where they are not, which includes CI: there, an 8B model on
machines without a GPU would take minutes per summary. Run it locally after
changing prompts, the model or the summary, concept, graph, roadmap or
practice services.

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

    # The environment's summary was built from it too, the same way.
    environment = client.get(f"/api/environments/{env['id']}/summary").json()
    assert environment["state"] == "up_to_date", environment
    master = environment["summary"]
    assert [d["filename"] for d in master["based_on"]] == ["Lecture 4.pdf"]
    assert master["key_points"] and all(p["citations"] for p in master["key_points"])
    texts = [master["overview"], *(p["text"] for p in master["key_points"])]
    assert not any(mark in text for text in texts for mark in ("**", "##", "\n- "))
    for point in master["key_points"]:
        excerpts = [c["excerpt"] for c in point["citations"]]
        assert max(reranker.score(point["text"], excerpts)) >= 0.5, point

    # And its concepts were extracted: validated, each with its evidence.
    concepts = client.get(f"/api/documents/{document['id']}/concepts").json()
    assert concepts["extraction"]["status"] == "ready", concepts["extraction"]
    found = concepts["concepts"]
    assert len(found) >= 3
    assert all(c["evidence"] and c["definition"] for c in found)
    assert len({c["normalized_name"] for c in found}) == len(found)

    # And the graph was built from them: every pair the backend found was
    # decided, and every relationship rests on passages it cites.
    graph = client.get(f"/api/environments/{env['id']}/graph").json()
    assert graph["state"] == "up_to_date", graph
    assert graph["pairs"] >= 1 and graph["asked"] == graph["pairs"]
    nodes = {n["id"] for n in graph["nodes"]}
    assert all({e["source"], e["target"]} <= nodes for e in graph["edges"])
    for edge in graph["edges"]:
        near = client.get(f"/api/concepts/{edge['source']}/neighbourhood").json()
        direct = [
            n
            for group in ("prerequisites", "dependents", "part_of", "parts", "related")
            for n in near[group]
            if n["id"] == edge["target"] and n["depth"] == 1
        ]
        assert direct and all(n["evidence"] for n in direct), (edge, near)

    # And the roadmap: every concept exactly once, prerequisites first unless
    # they loop, and stage titles in plain words.
    plan = client.get(f"/api/environments/{env['id']}/roadmap").json()
    assert plan["state"] == "up_to_date", plan
    placed = [c["id"] for stage in plan["stages"] for c in stage["concepts"]]
    assert sorted(placed) == sorted(nodes)
    at = {concept_id: n for n, concept_id in enumerate(placed)}
    for edge in graph["edges"]:
        if edge["relationship_type"] == "PREREQUISITE_OF" and not any(
            edge["source"] in {c["id"] for c in cycle["concepts"]}
            for cycle in plan["cycles"]
        ):
            assert at[edge["source"]] < at[edge["target"]], edge
    assert all(stage["written"] for stage in plan["stages"]), plan["stages"]
    for stage in plan["stages"]:
        assert len(stage["title"].split()) <= 8
        assert not any(mark in stage["title"] + stage["description"] for mark in "*#`")

    # And practice for the first concept: items in plain words, never
    # mentioning passages, each supported by the passage it cites.
    first = plan["stages"][0]["concepts"][0]
    client.post(f"/api/concepts/{first['id']}/practice")
    practice = client.get(f"/api/environments/{env['id']}/practice").json()
    state = next(c for c in practice["concepts"] if c["concept_id"] == first["id"])
    assert state["state"] == "ready" and state["items"] >= 2, state
    items = client.get(
        f"/api/environments/{env['id']}/practice/session",
        params={"concept_id": first["id"]},
    ).json()
    for item in items:
        assert "passage" not in item["prompt"].lower(), item
        assert not any(mark in item["prompt"] for mark in "*#`"), item

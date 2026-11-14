"""Tests for incremental updates and their records, through the API.

Purpose: every change to an environment's material records an update whose
steps say what each did, and whose report says what changed: new and
removed concepts and relationships, passages new, kept and removed, what
was updated and what was not. A new version keeps the document, its
unchanged passages and the practice of concepts whose passages did not
change; identical files are refused; a failed step marks the update failed.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parsing import ParseError
from app.routers.documents import get_parser
from tests import pdfs
from tests.test_concepts import concept
from tests.test_concepts_api import environment, upload
from tests.test_graph import RULES, SCHEDULING_CONCEPTS
from tests.test_graph_api import SCHEDULING, SYNCHRONIZATION
from tests.test_practice import Practising
from tests.test_practice_api import concept_ids

# Scheduling, its round robin passage rewritten.
SCHEDULING_V2 = pdfs.html_pdf(
    "<h2>Threads</h2><p>A thread is a sequence of execution within a process.</p>",
    "<h2>Round robin</h2><p>Round robin gives every thread a fixed time quantum, "
    "then moves it to the back of the queue.</p>",
)


@pytest.fixture
def llm():
    sync = [
        concept("Mutex", [1]),
        concept("Critical Section", [1]),
        concept("Semaphore", [2]),
    ]
    return Practising(RULES, [SCHEDULING_CONCEPTS, sync, SCHEDULING_CONCEPTS])


def updates(client: TestClient, env: str) -> list[dict]:
    return client.get(f"/api/environments/{env}/updates").json()


def steps(update: dict) -> dict[str, tuple[str, str]]:
    return {s["name"]: (s["state"], s["detail"]) for s in update["steps"]}


def names(notes: list[dict]) -> list[str]:
    return [n["name"] for n in notes]


def edges(notes: list[dict]) -> set[tuple[str, str, str]]:
    return {(n["source"], n["type"], n["target"]) for n in notes}


def test_an_added_document_records_each_step_and_what_changed(client: TestClient):
    env = environment(client)
    document = upload(client, env, "scheduling.pdf", SCHEDULING)

    [update] = updates(client, env)

    assert (update["kind"], update["status"], update["filename"]) == (
        "added",
        "done",
        "scheduling.pdf",
    )
    assert update["document_id"] == document["id"] and update["finished_at"]
    assert steps(update) == {
        "read": (
            "done",
            (
                "2 passages: 2 new, 0 kept, 0 removed. 2 embedded, 0 found already "
                "embedded by their text."
            ),
        ),
        "document_summary": ("done", "Written for this text."),
        "environment_summary": ("done", "Rebuilt from 1 document summaries."),
        "concepts": ("done", "3 concepts in this document, 3 new to the environment."),
        "knowledge_graph": (
            "done",
            "The model was asked about 3 new pairs; 0 were remembered.",
        ),
        "roadmap": ("done", "1 stages: 1 titled now, 0 kept."),
    }
    report = update["report"]
    assert report["new_concepts"] == ["Round Robin", "Thread", "Time Quantum"]
    assert edges(report["new_relationships"]) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }
    assert report["passages"]["new"] == 2
    assert names(report["updated"]) == [
        "Its summary",
        "Environment summary",
        "Knowledge map",
        "Roadmap stage titles",
    ]
    assert client.get(f"/api/updates/{update['id']}").json() == update


def test_a_second_document_reports_only_its_own_changes(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)

    latest, first = updates(client, env)

    report = latest["report"]
    assert report["new_concepts"] == ["Critical Section", "Mutex", "Semaphore"]
    assert report["removed_concepts"] == []
    assert ("Thread", "PREREQUISITE_OF", "Mutex") in edges(report["new_relationships"])
    assert ("Thread", "PREREQUISITE_OF", "Round Robin") not in edges(
        report["new_relationships"]
    )
    assert {"name": "Other documents' summaries", "detail": "1 kept."} in report[
        "unchanged"
    ]
    assert first["kind"] == "added" and first["filename"] == "scheduling.pdf"


def test_a_new_version_keeps_the_document_and_what_did_not_change(
    client: TestClient, llm
):
    env = environment(client)
    document = upload(client, env, "scheduling.pdf", SCHEDULING)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)
    ids = concept_ids(client, env)
    client.post(
        f"/api/environments/{env}/practice",
        json={"concept_ids": [ids["Thread"], ids["Round Robin"]]},
    )
    chunks = {
        c["heading"]: c["id"]
        for c in client.get(f"/api/documents/{document['id']}/chunks").json()
    }
    embeddings = len(llm.calls)

    response = client.post(
        f"/api/documents/{document['id']}/versions",
        content=SCHEDULING_V2,
        headers={"Content-Type": "application/pdf"},
    )

    assert response.status_code == 202, response.text
    assert response.json()["id"] == document["id"]
    listed = [d["id"] for d in client.get(f"/api/environments/{env}/documents").json()]
    assert len(listed) == 2 and document["id"] in listed  # the same document
    update = updates(client, env)[0]
    assert (update["kind"], update["status"], update["document_id"]) == (
        "new_version",
        "done",
        document["id"],
    )
    assert update["report"]["passages"] == {
        "passages": 2,
        "new": 1,
        "kept": 1,
        "removed": 1,
        "embedded": 1,
        "reused": 0,
    }
    after = {
        c["heading"]: c["id"]
        for c in client.get(f"/api/documents/{document['id']}/chunks").json()
    }
    assert after["Threads"] == chunks["Threads"]  # unchanged: same passage
    assert after["Round robin"] != chunks["Round robin"]
    # Thread's passage did not change, so its practice is kept; Round
    # Robin's did, so its items wait to be prepared again.
    assert update["report"]["practice_outdated"] == ["Round Robin"]
    assert {"name": "Practice items", "detail": "Those of 1 concepts kept."} in update[
        "report"
    ]["unchanged"]
    assert steps(update)["document_summary"] == ("done", "Written for this text.")
    assert len(llm.calls) > embeddings


def test_identical_versions_are_refused(client: TestClient):
    env = environment(client)
    document = upload(client, env, "scheduling.pdf", SCHEDULING)
    upload(client, env, "sync.pdf", SYNCHRONIZATION)

    same = client.post(
        f"/api/documents/{document['id']}/versions",
        content=SCHEDULING,
        headers={"Content-Type": "application/pdf"},
    )
    other = client.post(
        f"/api/documents/{document['id']}/versions",
        content=SYNCHRONIZATION,
        headers={"Content-Type": "application/pdf"},
    )

    assert (same.status_code, same.json()["detail"]) == (
        409,
        "This file is the document's current version already.",
    )
    assert other.status_code == 409
    assert "sync.pdf" in other.json()["detail"]
    assert len(updates(client, env)) == 2  # no update for refused versions


def test_a_deletion_records_what_went(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    sync = upload(client, env, "sync.pdf", SYNCHRONIZATION)

    client.delete(f"/api/documents/{sync['id']}")

    update = updates(client, env)[0]
    assert (update["kind"], update["status"], update["filename"]) == (
        "deleted",
        "done",
        "sync.pdf",
    )
    assert update["document_id"] is None  # the document is gone
    assert list(steps(update)) == ["environment_summary", "knowledge_graph", "roadmap"]
    # Without sync.pdf, the material is what it was before it came: the
    # results written then are current again, and the record says so.
    assert steps(update)["environment_summary"] == (
        "done",
        "Back to the summary written earlier for these documents.",
    )
    assert steps(update)["knowledge_graph"] == (
        "done",
        "Back to the map of these concepts built earlier; nothing new asked.",
    )
    assert {"Environment summary", "Knowledge map"} <= set(
        names(update["report"]["updated"])
    )
    report = update["report"]
    assert report["removed_concepts"] == ["Critical Section", "Mutex", "Semaphore"]
    assert ("Thread", "PREREQUISITE_OF", "Mutex") in edges(
        report["removed_relationships"]
    )
    assert report["new_concepts"] == [] and report["passages"] is None


class Unreadable:
    def parse(self, path):
        raise ParseError("This PDF is damaged and could not be opened.")


def test_a_failed_step_marks_the_update_failed(client: TestClient):
    app.dependency_overrides[get_parser] = Unreadable
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)

    [update] = updates(client, env)

    assert update["status"] == "failed"
    assert steps(update)["read"] == (
        "failed",
        "This PDF is damaged and could not be opened.",
    )
    assert steps(update)["document_summary"][0] == "skipped"
    assert steps(update)["concepts"][0] == "skipped"


def test_an_unknown_update_is_not_found(client: TestClient):
    assert client.get(f"/api/updates/{uuid.uuid4()}").status_code == 404

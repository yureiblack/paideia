"""Tests for the update report's rules in app/services/updates.py.

Purpose: the report compares two snapshots. The knowledge map counts as
updated when its relationships changed, even when the build behind it is
the same one (edges written again from remembered decisions).
"""

from types import SimpleNamespace

from app.services.updates import report

UPDATE = SimpleNamespace(document_id=None, kind="reprocessed", steps=[])


def snapshot(edges, graph="g1"):
    return {
        "concepts": {"a": "Thread", "b": "Mutex"},
        "relationships": edges,
        "document_summaries": {},
        "environment_summary": "s1",
        "knowledge_graph": graph,
        "roadmap": "r1",
        "practised": [],
    }


def test_new_relationships_update_the_map_even_from_the_same_build():
    before = snapshot([["a", "RELATED_TO", "b"]])
    after = snapshot([["a", "PREREQUISITE_OF", "b"]])

    changed = report(before, after, UPDATE)

    assert {"name": "Knowledge map", "detail": None} in changed["updated"]
    assert changed["relationships"]["new"] == [
        {"source": "Thread", "type": "PREREQUISITE_OF", "target": "Mutex"}
    ]
    assert changed["relationships"]["removed"] == [
        {"source": "Thread", "type": "RELATED_TO", "target": "Mutex"}
    ]
    assert {"name": "Roadmap stage titles", "detail": None} in changed["unchanged"]


def test_nothing_changed_reports_everything_unchanged():
    same = snapshot([["a", "RELATED_TO", "b"]])

    changed = report(same, same, UPDATE)

    assert changed["updated"] == []
    assert [n["name"] for n in changed["unchanged"]] == [
        "Environment summary",
        "Knowledge map",
        "Roadmap stage titles",
    ]

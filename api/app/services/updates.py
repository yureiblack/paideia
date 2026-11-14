"""Update records: every change to an environment's material, step by step.

Purpose
-------
Adding a document, a new version, a reprocess or a deletion each sets off a
chain of background steps: reading, the document's summary, the
environment's summary, concepts, the knowledge graph, the roadmap. Each of
them already redoes only what changed (decision record 17). An update
record makes that visible: it is created when the change is asked for, each
step records itself as it runs and what it did, and when the chain ends the
record says what changed, by comparing the environment before and after.

The steps' own work is unchanged: run_step wraps the same functions the
chains always called.
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionFactory
from app.llm import LLMProvider
from app.models import (
    Concept,
    ConceptRelationship,
    Document,
    Environment,
    GeneratedArtifact,
    MaterialUpdate,
)
from app.schemas import MaterialUpdateRead, UpdateReport, UpdateStep
from app.services import concepts as concept_service
from app.services import environment_summaries as environment_summary_service
from app.services import graph as graph_service
from app.services import practice as practice_service
from app.services import roadmap as roadmap_service
from app.services import summaries as summary_service

logger = logging.getLogger(__name__)

LABELS = {
    "read": "Reading the document",
    "document_summary": "Its summary",
    "environment_summary": "Environment summary",
    "concepts": "Concepts",
    "knowledge_graph": "Knowledge map",
    "roadmap": "Roadmap",
}
DOCUMENT_STEPS = (
    "read",
    "document_summary",
    "environment_summary",
    "concepts",
    "knowledge_graph",
    "roadmap",
)
DELETION_STEPS = ("environment_summary", "knowledge_graph", "roadmap")


# --- snapshots ------------------------------------------------------------------


KINDS = {
    "environment_summary": "environment_summary",
    "knowledge_graph": "knowledge_graph",
    "roadmap": "learning_roadmap",
}


def _current(session: Session, environment_id: uuid.UUID, llm: LLMProvider) -> dict:
    """The result each shared step stands for now, by id: the environment's
    summary of its current documents, the graph of its current pairs, the
    titles of its current stages. Not the newest written: going back to
    earlier material goes back to the results written for it."""
    environment = session.get(Environment, environment_id)
    shown = environment_summary_service.state(session, environment, llm).summary
    pairs = graph_service._pairs(session, environment_id)
    graph = (
        graph_service._find(
            session, environment_id, graph_service._version(pairs), llm.model_name
        )
        if pairs
        else None
    )
    found = roadmap_service.material(session, environment_id)
    titles = (
        roadmap_service._find(session, environment_id, found.version, llm.model_name)
        if found.nodes
        else None
    )
    return {
        "environment_summary": str(shown.id) if shown and shown.current else None,
        "knowledge_graph": str(graph.id) if graph and graph.status == "ready" else None,
        "roadmap": str(titles.id) if titles and titles.status == "ready" else None,
    }


def _seen(session: Session, environment_id: uuid.UUID) -> dict[str, list[str]]:
    """Every result of each shared kind already written, to tell going back
    to one from writing a new one."""
    return {
        key: [
            str(i)
            for i in session.scalars(
                select(GeneratedArtifact.id).where(
                    GeneratedArtifact.environment_id == environment_id,
                    GeneratedArtifact.artifact_type == kind,
                )
            )
        ]
        for key, kind in KINDS.items()
    }


def snapshot(session: Session, environment_id: uuid.UUID, llm: LLMProvider) -> dict:
    """What an update's report compares: concepts, relationships, each
    document's current summary, the newest environment summary, graph and
    roadmap titles, and which concepts have practice items practised now."""
    concepts = {
        str(c.id): c.name
        for c in session.scalars(
            select(Concept).where(Concept.environment_id == environment_id)
        )
    }
    relationships = sorted(
        [str(r.source_concept_id), r.relationship_type, str(r.target_concept_id)]
        for r in session.scalars(
            select(ConceptRelationship).where(
                ConceptRelationship.environment_id == environment_id
            )
        )
    )
    document_summaries = {}
    for document in session.scalars(
        select(Document).where(Document.environment_id == environment_id)
    ):
        summary = summary_service.current_summary(session, document, llm)
        ready = summary is not None and summary.status == "ready"
        document_summaries[str(document.id)] = str(summary.id) if ready else None
    _, _, practised, _ = practice_service._practised(session, environment_id)
    return {
        "concepts": concepts,
        "relationships": relationships,
        "document_summaries": document_summaries,
        **_current(session, environment_id, llm),
        "seen": _seen(session, environment_id),
        "practised": sorted({str(item.concept_id) for item, _ in practised}),
    }


def begin(
    session: Session,
    environment_id: uuid.UUID,
    kind: str,
    document: Document,
    llm: LLMProvider,
    steps: Iterable[str],
) -> MaterialUpdate:
    """Record a change about to be made, with the environment as it is
    before it. Commits."""
    update = MaterialUpdate(
        environment_id=environment_id,
        document_id=document.id,
        filename=document.filename,
        kind=kind,
        status="running",
        steps=[
            {"name": name, "label": LABELS[name], "state": "waiting", "detail": None}
            for name in steps
        ],
        before=snapshot(session, environment_id, llm),
        started_at=datetime.now(UTC),
    )
    session.add(update)
    session.commit()
    return update


# --- steps ---------------------------------------------------------------------


def _set_step(
    session: Session, update: MaterialUpdate, name: str, state: str, detail, result=None
) -> None:
    steps = []
    for step in update.steps:
        if step["name"] == name:
            step = {**step, "state": state, "detail": detail}
            if result is not None:
                step["result"] = result
        steps.append(step)
    update.steps = steps


def _document(session: Session, update: MaterialUpdate) -> Document | None:
    return session.get(Document, update.document_id) if update.document_id else None


def _describe_read(session, update, result, llm):
    document = _document(session, update)
    if document is None:
        return "skipped", "The document was deleted meanwhile."
    if document.status == "failed":
        return "failed", document.error
    if result is None:
        return "done", "Already read."
    return "done", (
        f"{result['passages']} passages: {result['new']} new, {result['kept']} kept, "
        f"{result['removed']} removed. {result['embedded']} embedded, "
        f"{result['reused']} found already embedded by their text."
    )


def _describe_document_summary(session, update, result, llm):
    document = _document(session, update)
    if document is None or document.status != "ready":
        return "skipped", "The document could not be read."
    summary = summary_service.current_summary(session, document, llm)
    if summary is None:
        return "skipped", "No summary was asked for."
    if summary.status == "failed":
        return "failed", summary.error
    if summary.status != "ready":
        return "done", "Being written."
    before = update.before.get("document_summaries", {}).get(str(document.id))
    if before == str(summary.id):
        return "done", "Kept: its text is unchanged."
    return "done", "Written for this text."


def _changed(session, update, key, llm) -> tuple[GeneratedArtifact | None, str]:
    """The step's current result, and whether it is unchanged, a new one, or
    one written earlier and current again."""
    now = _current(session, update.environment_id, llm)[key]
    if now == update.before.get(key):
        return None, "unchanged"
    artifact = session.get(GeneratedArtifact, uuid.UUID(now)) if now else None
    written = (artifact.metadata_json or {}).get("written_at") if artifact else None
    rewritten = written is not None and written >= update.started_at.isoformat()
    earlier = now in update.before.get("seen", {}).get(key, []) and not rewritten
    return artifact, "earlier" if earlier else "new"


def _describe_environment_summary(session, update, result, llm):
    environment = session.get(Environment, update.environment_id)
    state = environment_summary_service.state(session, environment, llm)
    if state.state == "failed":
        return "failed", state.error
    if state.state == "waiting":
        return "done", "Waiting for other documents still on their way."
    if state.state == "none":
        return "done", "Nothing to summarize."
    artifact, how = _changed(session, update, "environment_summary", llm)
    if how == "earlier":
        return "done", "Back to the summary written earlier for these documents."
    if how == "new" and artifact is not None:
        documents = len((artifact.metadata_json or {}).get("based_on", []))
        return "done", f"Rebuilt from {documents} document summaries."
    return "done", "Unchanged."


def _describe_concepts(session, update, result, llm):
    document = _document(session, update)
    if document is None or document.status != "ready":
        return "skipped", "The document could not be read."
    extraction = concept_service.current_extraction(session, document, llm)
    if extraction is None:
        return "skipped", "No extraction was asked for."
    if extraction.status == "failed":
        return "failed", extraction.error
    kept = (extraction.metadata_json or {}).get("kept", 0)
    known = set(update.before.get("concepts", {}))
    new = session.scalars(
        select(Concept.id).where(Concept.environment_id == update.environment_id)
    ).all()
    added = sum(str(i) not in known for i in new)
    return "done", f"{kept} concepts in this document, {added} new to the environment."


def _describe_graph(session, update, result, llm):
    environment = session.get(Environment, update.environment_id)
    state = graph_service.state(session, environment, llm)
    if state.state == "failed":
        return "failed", state.error
    if state.state == "waiting":
        return "done", "Waiting for other documents still on their way."
    artifact, how = _changed(session, update, "knowledge_graph", llm)
    if how == "earlier":
        return (
            "done",
            "Back to the map of these concepts built earlier; nothing new asked.",
        )
    if how == "new" and artifact is not None:
        meta = artifact.metadata_json or {}
        return "done", (
            f"The model was asked about {meta.get('asked', 0)} new pairs; "
            f"{meta.get('remembered', 0)} were remembered."
        )
    return "done", "Unchanged: no new pairs of concepts."


def _describe_roadmap(session, update, result, llm):
    environment = session.get(Environment, update.environment_id)
    state = roadmap_service.state(session, environment, llm)
    if state.state == "failed":
        return "failed", state.error
    if state.state == "waiting":
        return "done", "Waiting for the knowledge map."
    artifact, how = _changed(session, update, "roadmap", llm)
    if how == "earlier":
        return (
            "done",
            f"Back to the stage titles written earlier: {len(state.stages)} stages.",
        )
    if how == "new" and artifact is not None:
        meta = artifact.metadata_json or {}
        return "done", (
            f"{meta.get('stages', len(state.stages))} stages: "
            f"{meta.get('asked', 0)} titled now, {meta.get('remembered', 0)} kept."
        )
    return "done", f"Unchanged: {len(state.stages)} stages."


DESCRIBE = {
    "read": _describe_read,
    "document_summary": _describe_document_summary,
    "environment_summary": _describe_environment_summary,
    "concepts": _describe_concepts,
    "knowledge_graph": _describe_graph,
    "roadmap": _describe_roadmap,
}


def run_step(
    session_factory: SessionFactory,
    update_id: uuid.UUID,
    name: str,
    llm: LLMProvider,
    work: Callable,
    *args,
) -> None:
    """Run one step of an update's chain, recording it as running, then what
    it did. A background task, in place of work(*args) itself."""
    with session_factory() as session:
        update = session.get(MaterialUpdate, update_id, with_for_update=True)
        if update is not None:
            _set_step(session, update, name, "running", None)
            session.commit()
    result, problem = None, None
    try:
        result = work(*args)
    except Exception:
        logger.exception("Step %s of update %s failed", name, update_id)
        problem = "An unexpected error occurred."
    with session_factory() as session:
        update = session.get(MaterialUpdate, update_id, with_for_update=True)
        if update is None:
            return
        if problem is not None:
            state, detail = "failed", problem
        else:
            state, detail = DESCRIBE[name](session, update, result, llm)
        _set_step(
            session,
            update,
            name,
            state,
            detail,
            result if isinstance(result, dict) else None,
        )
        session.commit()


# --- the report ----------------------------------------------------------------


def report(before: dict, after: dict, update: MaterialUpdate) -> dict:
    """What an update changed, from the environment before and after it."""
    names = {**before.get("concepts", {}), **after.get("concepts", {})}
    was, now = set(before.get("concepts", {})), set(after.get("concepts", {}))
    edges_before = {tuple(r) for r in before.get("relationships", [])}
    edges_after = {tuple(r) for r in after.get("relationships", [])}

    def named(edges):
        found = [
            {"source": names.get(s, "?"), "type": t, "target": names.get(d, "?")}
            for s, t, d in edges
        ]
        return sorted(found, key=lambda e: (e["source"], e["type"], e["target"]))

    updated, unchanged = [], []
    document = str(update.document_id) if update.document_id else None
    summaries_before = before.get("document_summaries", {})
    summaries_after = after.get("document_summaries", {})
    if document and update.kind != "deleted":
        if summaries_after.get(document) and summaries_after.get(
            document
        ) != summaries_before.get(document):
            updated.append({"name": "Its summary", "detail": "Written for this text."})
        elif summaries_after.get(document):
            unchanged.append(
                {"name": "Its summary", "detail": "Its text is unchanged."}
            )
    others = [
        d
        for d, s in summaries_after.items()
        if d != document and s and summaries_before.get(d) == s
    ]
    if others:
        unchanged.append(
            {"name": "Other documents' summaries", "detail": f"{len(others)} kept."}
        )
    for key, label in (
        ("environment_summary", "Environment summary"),
        ("knowledge_graph", "Knowledge map"),
        ("roadmap", "Roadmap stage titles"),
    ):
        moved = after.get(key) != before.get(key)
        if key == "knowledge_graph":
            moved = moved or edges_before != edges_after
        (updated if moved else unchanged).append({"name": label, "detail": None})
    practised_before = set(before.get("practised", []))
    practised_after = set(after.get("practised", []))
    outdated = sorted(names[i] for i in practised_before - practised_after if i in now)
    kept = practised_before & practised_after
    if kept:
        unchanged.append(
            {"name": "Practice items", "detail": f"Those of {len(kept)} concepts kept."}
        )
    if outdated:
        updated.append(
            {
                "name": "Practice items",
                "detail": "To prepare again, as their passages changed: "
                + ", ".join(outdated)
                + ".",
            }
        )
    read = next((s for s in update.steps if s["name"] == "read"), None)
    return {
        "concepts": {
            "new": sorted(names[i] for i in now - was),
            "removed": sorted(names[i] for i in was - now),
        },
        "relationships": {
            "new": named(edges_after - edges_before),
            "removed": named(edges_before - edges_after),
        },
        "passages": read.get("result") if read else None,
        "updated": updated,
        "unchanged": unchanged,
        "practice_outdated": outdated,
    }


def finish(
    session_factory: SessionFactory, update_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Close an update with what it changed. A background task, the chain's
    last."""
    with session_factory() as session:
        update = session.get(MaterialUpdate, update_id, with_for_update=True)
        if update is None:
            return
        after = snapshot(session, update.environment_id, llm)
        update.report = report(update.before, after, update)
        failed = any(step["state"] == "failed" for step in update.steps)
        update.steps = [
            {**s, "state": "skipped"} if s["state"] in ("waiting", "running") else s
            for s in update.steps
        ]
        update.status = "failed" if failed else "done"
        update.finished_at = datetime.now(UTC)
        session.commit()


def to_read(update: MaterialUpdate) -> MaterialUpdateRead:
    report = update.report
    return MaterialUpdateRead(
        id=update.id,
        kind=update.kind,
        document_id=update.document_id,
        filename=update.filename,
        status=update.status,
        steps=[
            UpdateStep(**{k: s[k] for k in ("name", "label", "state", "detail")})
            for s in update.steps
        ],
        report=UpdateReport(
            new_concepts=report["concepts"]["new"],
            removed_concepts=report["concepts"]["removed"],
            new_relationships=report["relationships"]["new"],
            removed_relationships=report["relationships"]["removed"],
            passages=report["passages"],
            updated=report["updated"],
            unchanged=report["unchanged"],
            practice_outdated=report["practice_outdated"],
        )
        if report
        else None,
        started_at=update.started_at,
        finished_at=update.finished_at,
    )


def recent(
    session: Session, environment_id: uuid.UUID, limit: int = 20
) -> list[MaterialUpdate]:
    """An environment's updates, newest first."""
    return list(
        session.scalars(
            select(MaterialUpdate)
            .where(MaterialUpdate.environment_id == environment_id)
            .order_by(MaterialUpdate.started_at.desc(), MaterialUpdate.id)
            .limit(limit)
        )
    )

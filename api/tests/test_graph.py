"""Tests for the knowledge graph in app/services/graph.py, with mocked model
decisions.

Purpose: the backend finds the pairs and the model only classifies them;
every decision is remembered, so a rebuild asks only about pairs not seen
before (a new lecture's) and a deletion asks nothing; the graph's edges are
exactly what the current pairs' decisions stand for, each with its passages
as evidence; the tables refuse a second relationship for a pair, self-edges
and confidences out of range; traversal is transitive and survives cycles.
"""

import re

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Concept,
    ConceptRelationship,
    Document,
    GeneratedArtifact,
    RelationshipDecision,
)
from app.services import concepts, graph
from app.services import documents as document_service
from tests.fakes import FailingProvider, MockProvider, simple_answer
from tests.parsed import H, P, document
from tests.test_concepts import add, chunks_of, concept, environment, extract

SCHEDULING = document(
    [H("Threads"), P("A thread is a sequence of execution within a process.")],
    [H("Round robin"), P("Round robin gives every thread a time quantum in turn.")],
)
SYNCHRONIZATION = document(
    [H("Mutex"), P("A mutex lets one of the threads into the critical section.")],
    [H("Semaphores"), P("A semaphore counts the resources available.")],
)
REVIEW = document(
    [H("Threads again"), P("Each thread waits for its turn in round robin.")],
)
SCHEDULING_CONCEPTS = [
    concept("Thread", [1]),
    concept("Round Robin", [2]),
    concept("Time Quantum", [2]),
]
SYNCHRONIZATION_CONCEPTS = [
    concept("Mutex", [1]),
    concept("Critical Section", [1]),
    concept("Semaphore", [2]),
]

_PAIR = re.compile(
    r"^Pair (\d+) \(passages [\d, ]+\): (.+?): .*? \| (.+?): ", re.MULTILINE
)
CHOICES = {"before": (1, 2), "part of": (3, 4), "related": (5, 5)}


def asked_pairs(prompt) -> list[tuple[str, str]]:
    """The pairs a relationship prompt asks about, as (a, b) names."""
    return [(a, b) for _, a, b in _PAIR.findall(prompt.user)]


class Deciding(MockProvider):
    """A model whose concept extractions are scripted, one list per
    document, and whose relationship decisions follow rules: (x, y): "before"
    means x must be understood before y, "part of" that x is a part of y,
    "related" just related; any other pair has no relationship."""

    def __init__(self, rules, extractions=(), confidence=0.9, **kwargs):
        super().__init__(answer=self._answer, **kwargs)
        self.rules, self.confidence = rules, confidence
        self.extractions = iter(extractions)

    def _answer(self, prompt, schema):
        if prompt.name == "concept_extraction":
            return {"concepts": next(self.extractions)}
        if prompt.name != "relationship":
            return simple_answer(prompt, schema)
        decisions = []
        for number, (a, b) in enumerate(asked_pairs(prompt), start=1):
            choice = 6
            if (a, b) in self.rules:
                choice = CHOICES[self.rules[(a, b)]][0]
            elif (b, a) in self.rules:
                choice = CHOICES[self.rules[(b, a)]][1]
            decisions.append(
                {"pair": number, "choice": choice, "confidence": self.confidence}
            )
        return {"decisions": decisions}

    def relationship_calls(self):
        return [p for p, _ in self.calls if p.name == "relationship"]


RULES = {
    ("Thread", "Round Robin"): "before",
    ("Time Quantum", "Round Robin"): "part of",
    ("Critical Section", "Mutex"): "related",
    ("Thread", "Mutex"): "before",
}


def build(session, session_factory, env, llm) -> GeneratedArtifact | None:
    graph.refresh_graph(session_factory, env.id, llm)
    session.expire_all()
    return graph._find(
        session,
        env.id,
        graph._version(graph._pairs(session, env.id)),
        llm.model_name,
    )


def written(meta: dict) -> dict:
    """A build's details without the time it was written."""
    return {k: v for k, v in meta.items() if k != "written_at"}


def edges(session, env) -> set[tuple[str, str, str]]:
    """(source, type, target) by concept name."""
    names = {
        c.id: c.name
        for c in session.scalars(
            select(Concept).where(Concept.environment_id == env.id)
        )
    }
    return {
        (names[r.source_concept_id], r.relationship_type, names[r.target_concept_id])
        for r in session.scalars(
            select(ConceptRelationship).where(
                ConceptRelationship.environment_id == env.id
            )
        )
    }


def scheduling_graph(session, session_factory, llm):
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)
    return env, doc, build(session, session_factory, env, llm)


def test_the_model_classifies_the_pairs_the_backend_found(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS])

    env, doc, artifact = scheduling_graph(session, session_factory, llm)

    [prompt] = llm.relationship_calls()
    assert sorted(asked_pairs(prompt)) == [
        ("Round Robin", "Thread"),
        ("Round Robin", "Time Quantum"),
        ("Thread", "Time Quantum"),
    ]
    # Statements with the real names, both directions offered.
    assert "  1. Round Robin must be understood before Thread." in prompt.user
    assert "  2. Thread must be understood before Round Robin." in prompt.user
    assert artifact.status == "ready"
    assert written(artifact.metadata_json) == {"pairs": 3, "asked": 3, "remembered": 0}
    assert artifact.content == {"edges": {"PART_OF": 1, "PREREQUISITE_OF": 1}}
    assert edges(session, env) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }
    # Each edge's evidence is the passage that connected its pair.
    rr = session.scalar(select(Concept).where(Concept.name == "Round Robin"))
    near = graph.neighbourhood(session, rr)
    [thread] = near.prerequisites
    [evidence] = thread.evidence
    assert evidence.chunk_id == chunks_of(session, doc)[1].id
    assert [p.name for p in near.parts] == ["Time Quantum"]


def test_building_again_with_the_same_pairs_asks_nothing(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS])
    env, _, first = scheduling_graph(session, session_factory, llm)
    calls = len(llm.calls)

    again = build(session, session_factory, env, llm)
    artifact, write_now = graph.request_graph(session, env, llm)

    assert len(llm.calls) == calls
    assert again.id == first.id == artifact.id
    assert not write_now
    assert graph.state(session, env, llm).state == "up_to_date"


def test_a_new_lecture_asks_only_about_its_new_pairs(session: Session, session_factory):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])
    env, _, _ = scheduling_graph(session, session_factory, llm)

    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)
    artifact = build(session, session_factory, env, llm)

    _, second = llm.relationship_calls()
    # The mutex passage names threads: Thread, from the scheduling lecture,
    # is paired with the synchronization lecture's concepts.
    assert sorted(asked_pairs(second)) == [
        ("Critical Section", "Mutex"),
        ("Critical Section", "Thread"),
        ("Mutex", "Thread"),
    ]
    assert written(artifact.metadata_json) == {"pairs": 6, "asked": 3, "remembered": 3}
    assert edges(session, env) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
        ("Critical Section", "RELATED_TO", "Mutex"),
        ("Thread", "PREREQUISITE_OF", "Mutex"),
    }


def test_deleting_a_lecture_removes_its_relationships_and_asks_nothing(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])
    env, _, first = scheduling_graph(session, session_factory, llm)
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)
    build(session, session_factory, env, llm)
    calls = len(llm.calls)

    document_service.delete_document(session, sync)
    concepts.refresh_concepts(session, env.id)
    session.commit()
    artifact = build(session, session_factory, env, llm)

    assert len(llm.calls) == calls
    assert artifact.id == first.id  # the same pairs as the first build
    assert edges(session, env) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }


def test_going_back_to_earlier_pairs_brings_back_their_edges(
    session: Session, session_factory
):
    # A second lecture's passage about threads in round robin gives the pair
    # Round Robin and Thread a second passage: a new question, decided
    # differently. Deleting the lecture brings back the first question, and
    # its remembered answer.
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, Deciding(RULES, [SCHEDULING_CONCEPTS]))
    build(session, session_factory, env, Deciding(RULES))
    review = add(session, session_factory, env, "review.pdf", REVIEW)
    extract(session, session_factory, review, Deciding({}, [[concept("Thread", [1])]]))
    build(
        session, session_factory, env, Deciding({("Thread", "Round Robin"): "related"})
    )
    assert ("Round Robin", "RELATED_TO", "Thread") in edges(session, env)

    document_service.delete_document(session, review)
    concepts.refresh_concepts(session, env.id)
    session.commit()
    llm = Deciding({})
    # The first build is found again, but its edges are not back yet.
    assert graph.state(session, env, llm).state == "stale"
    build(session, session_factory, env, llm)
    assert graph.state(session, env, llm).state == "up_to_date"

    assert llm.calls == []
    assert edges(session, env) == {
        ("Thread", "PREREQUISITE_OF", "Round Robin"),
        ("Time Quantum", "PART_OF", "Round Robin"),
    }


class DeletingWhileDeciding(Deciding):
    """Deletes a document while it decides, as a user may while the model
    works."""

    def __init__(self, session_factory, document_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_factory, self.document_id = session_factory, document_id

    def generate_structured(self, prompt, schema):
        if prompt.name == "relationship":
            with self.session_factory() as other:
                doomed = other.get(Document, self.document_id)
                if doomed is None:  # deleted at the first request already
                    return super().generate_structured(prompt, schema)
                document_service.delete_document(other, doomed)
                concepts.refresh_concepts(other, doomed.environment_id)
                other.commit()
        return super().generate_structured(prompt, schema)


def test_a_document_deleted_while_the_model_decides_fails_the_build_quietly(
    session: Session, session_factory
):
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extracting = Deciding(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])
    extract(session, session_factory, doc, extracting)
    extract(session, session_factory, sync, extracting)

    artifact = build(
        session,
        session_factory,
        env,
        DeletingWhileDeciding(session_factory, sync.id, RULES),
    )
    session.expire_all()
    stale = session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.artifact_type == "knowledge_graph"
        )
    )

    assert artifact is None  # nothing built for the pairs as they are now
    assert stale.status == "failed"
    assert stale.error == "The concepts changed before the graph was built."
    assert session.scalar(select(func.count()).select_from(RelationshipDecision)) == 0
    assert graph.state(session, env, Deciding(RULES)).state == "stale"
    assert build(session, session_factory, env, Deciding(RULES)).status == "ready"


def test_decisions_without_a_relationship_are_remembered_but_draw_no_edge(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS], confidence=0.3)

    env, _, artifact = scheduling_graph(session, session_factory, llm)

    assert artifact.status == "ready"
    assert edges(session, env) == set()
    assert session.scalar(select(func.count()).select_from(RelationshipDecision)) == 3
    assert graph.state(session, env, llm).state == "up_to_date"


def test_a_model_that_fails_fails_the_build_and_asking_again_retries(
    session: Session, session_factory
):
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, Deciding(RULES, [SCHEDULING_CONCEPTS]))

    failed = build(session, session_factory, env, FailingProvider())
    state = graph.state(session, env, FailingProvider())

    assert failed.status == "failed"
    assert (state.state, state.error) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )
    assert state.edges == []

    llm = Deciding(RULES)
    retried = build(session, session_factory, env, llm)
    assert retried.id == failed.id
    assert retried.status == "ready"
    assert len(edges(session, env)) == 2


def test_the_graph_waits_while_documents_are_on_their_way(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS])
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    concepts.request_extraction(session, sync, llm)  # asked for, not written

    artifact, write_now = graph.request_graph(session, env, llm)
    state = graph.state(session, env, llm)

    assert (artifact, write_now) == (None, False)
    assert (state.state, state.waiting_for) == ("waiting", 1)
    assert llm.relationship_calls() == []
    sync.status = "processing"
    session.commit()
    assert graph.request_graph(session, env, llm) == (None, False)


def test_a_graph_whose_concepts_changed_before_it_was_built_is_not_stored(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)
    artifact, _ = graph.request_graph(session, env, llm)
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)

    graph.write_graph(session_factory, artifact.id, llm)

    session.expire_all()
    stale = session.get(GeneratedArtifact, artifact.id)
    assert stale.status == "failed"
    assert llm.relationship_calls() == []
    assert edges(session, env) == set()
    assert graph.state(session, env, llm).state == "stale"


def test_an_environment_without_pairs_has_no_graph(session: Session, session_factory):
    llm = Deciding(RULES, [[concept("Thread", [1])]])
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)

    assert graph.request_graph(session, env, llm) == (None, False)
    state = graph.state(session, env, llm)
    assert (state.state, [n.name for n in state.nodes]) == ("none", ["Thread"])


# --- the tables -----------------------------------------------------------------


def concepts_named(session, env, *names) -> list[Concept]:
    made = [
        Concept(
            environment_id=env.id,
            name=name,
            normalized_name=name.lower(),
            definition=f"About {name}.",
        )
        for name in names
    ]
    session.add_all(made)
    session.flush()
    return made


def relate(session, env, source, target, kind="PREREQUISITE_OF", confidence=0.9):
    session.add(
        ConceptRelationship(
            environment_id=env.id,
            source_concept_id=source.id,
            target_concept_id=target.id,
            relationship_type=kind,
            confidence=confidence,
        )
    )
    session.flush()


@pytest.mark.parametrize(
    "second",
    [
        lambda a, b: (b, a, "PREREQUISITE_OF", 0.9),  # the contradiction
        lambda a, b: (a, b, "RELATED_TO", 0.9),  # a second kind
        lambda a, b: (a, a, "RELATED_TO", 0.9),  # a self-edge
        lambda a, b: (b, b, "PREREQUISITE_OF", 0.9),
        lambda a, b: (b, a, "PART_OF", 1.5),  # out of range (and a second)
    ],
)
def test_the_tables_refuse_a_second_relationship_for_a_pair_and_self_edges(
    session: Session, second
):
    env = environment(session)
    a, b = concepts_named(session, env, "Deadlock", "Deadlock Avoidance")
    relate(session, env, a, b)
    source, target, kind, confidence = second(a, b)

    with pytest.raises(IntegrityError), session.begin_nested():
        relate(session, env, source, target, kind, confidence)


def test_confidence_must_be_between_zero_and_one(session: Session):
    env = environment(session)
    a, b = concepts_named(session, env, "Deadlock", "Deadlock Avoidance")

    with pytest.raises(IntegrityError), session.begin_nested():
        relate(session, env, a, b, confidence=1.01)


# --- traversal ------------------------------------------------------------------


def names_of(session, found: dict) -> dict[str, int]:
    return {session.get(Concept, i).name: depth for i, depth in found.items()}


def test_prerequisites_and_dependents_are_found_transitively_with_depth(
    session: Session,
):
    env = environment(session)
    process, thread, mutex, deadlock, banker = concepts_named(
        session, env, "Process", "Thread", "Mutex", "Deadlock", "Banker"
    )
    relate(session, env, process, thread)
    relate(session, env, thread, mutex)
    relate(session, env, mutex, deadlock)
    relate(session, env, process, deadlock)  # a shorter way round
    relate(session, env, deadlock, banker, "RELATED_TO")  # not a prerequisite

    assert names_of(session, graph.walk(session, deadlock.id, "prerequisites")) == {
        "Mutex": 1,
        "Process": 1,
        "Thread": 2,
    }
    assert names_of(session, graph.walk(session, process.id, "dependents")) == {
        "Thread": 1,
        "Deadlock": 1,
        "Mutex": 2,
    }
    assert graph.walk(session, banker.id, "prerequisites") == {}


def test_a_cycle_ends_the_walk(session: Session, monkeypatch):
    env = environment(session)
    a, b, c = concepts_named(session, env, "A", "B", "C")
    relate(session, env, a, b)
    relate(session, env, b, c)
    relate(session, env, c, a)
    # Without the depth cap, only the path walked so far stops the walk: a
    # walk round and round the cycle would run until cancelled.
    monkeypatch.setattr(graph, "MAX_DEPTH", 10_000_000)
    session.execute(text("SET LOCAL statement_timeout = '3s'"))

    assert names_of(session, graph.walk(session, a.id, "prerequisites")) == {
        "C": 1,
        "B": 2,
    }
    assert names_of(session, graph.walk(session, a.id, "dependents")) == {
        "B": 1,
        "C": 2,
    }


def test_a_neighbourhood_sorts_neighbours_by_relationship(session: Session):
    env = environment(session)
    thread, rr, quantum, mlfq, fcfs, aging = concepts_named(
        session, env, "Thread", "Round Robin", "Time Quantum", "MLFQ", "FCFS", "Aging"
    )
    relate(session, env, thread, rr)
    relate(session, env, rr, mlfq)
    relate(session, env, quantum, rr, "PART_OF")
    relate(session, env, rr, fcfs, "PART_OF")
    relate(session, env, aging, rr, "RELATED_TO")

    near = graph.neighbourhood(session, rr)

    assert [(n.name, n.depth) for n in near.prerequisites] == [("Thread", 1)]
    assert [(n.name, n.depth) for n in near.dependents] == [("MLFQ", 1)]
    assert [n.name for n in near.parts] == ["Time Quantum"]
    assert [n.name for n in near.part_of] == ["FCFS"]
    assert [n.name for n in near.related] == ["Aging"]
    assert near.prerequisites[0].confidence == 0.9
    deeper = graph.neighbourhood(session, mlfq)
    assert [(n.name, n.depth, n.confidence) for n in deeper.prerequisites] == [
        ("Round Robin", 1, 0.9),
        ("Thread", 2, None),  # not a direct relationship: no evidence of its own
    ]


def test_a_document_deleted_and_added_again_finds_every_decision(
    session: Session, session_factory
):
    llm = Deciding(
        RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS, SYNCHRONIZATION_CONCEPTS]
    )
    env, _, _ = scheduling_graph(session, session_factory, llm)
    sync = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, sync, llm)
    build(session, session_factory, env, llm)
    full = edges(session, env)
    document_service.delete_document(session, sync)
    concepts.refresh_concepts(session, env.id)
    session.commit()
    build(session, session_factory, env, llm)
    asked = len(llm.relationship_calls())

    # Its concepts were deleted with it; the decisions about its pairs were
    # not, so adding it again asks the model nothing and the map is whole.
    again = add(session, session_factory, env, "sync.pdf", SYNCHRONIZATION)
    extract(session, session_factory, again, llm)
    build(session, session_factory, env, llm)

    assert len(llm.relationship_calls()) == asked
    assert edges(session, env) == full
    assert ("Thread", "PREREQUISITE_OF", "Mutex") in full


def test_a_ready_build_missing_decisions_asks_only_for_those(
    session: Session, session_factory
):
    llm = Deciding(RULES, [SCHEDULING_CONCEPTS])
    env, _, first = scheduling_graph(session, session_factory, llm)
    lost = session.scalars(select(RelationshipDecision)).first()
    session.delete(lost)
    session.commit()

    again = build(session, session_factory, env, llm)

    _, second = llm.relationship_calls()
    assert len(asked_pairs(second)) == 1
    assert again.id == first.id
    assert again.metadata_json["asked"] == 1
    assert len(edges(session, env)) == 2

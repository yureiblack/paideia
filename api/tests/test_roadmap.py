"""Tests for the learning roadmap in app/services/roadmap.py, with mocked
model answers.

Purpose: the roadmap's stages and order come from the concepts and the
graph by fixed rules; the model only titles the stages, and whatever it
answers cannot change the order. Titles are remembered by stage, so a new
lecture asks only about its new stages; stages without a usable title show
a plain one, and a failure never hides the roadmap. The roadmap waits for
the graph, and loops of prerequisites are shown.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConceptRelationship, GeneratedArtifact
from app.services import graph, roadmap
from tests.fakes import FailingProvider
from tests.parsed import H, P, document
from tests.test_concepts import add, chunks_of, concept, environment, extract
from tests.test_graph import (
    RULES,
    SCHEDULING,
    SCHEDULING_CONCEPTS,
    SYNCHRONIZATION,
    SYNCHRONIZATION_CONCEPTS,
    Deciding,
    concepts_named,
    relate,
)

MEMORY = document(
    [H("Paging"), P("Paging maps pages to frames.")],
    [H("TLB"), P("The TLB caches translations.")],
)
MEMORY_CONCEPTS = [concept("Paging", [1]), concept("TLB", [2])]


class Titling(Deciding):
    """Deciding, whose roadmap answers come from titles(number of stages):
    by default "Topic 1" and so on, answered last stage first."""

    def __init__(self, *args, titles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.titles = titles or (
            lambda n: [
                {"stage": k, "title": f"Topic {k}", "description": f"Learn topic {k}."}
                for k in range(n, 0, -1)
            ]
        )

    def _answer(self, prompt, schema):
        if prompt.name == "roadmap_stages":
            count = schema.model_json_schema()["properties"]["stages"]["maxItems"]
            return {"stages": self.titles(count)}
        return super()._answer(prompt, schema)

    def roadmap_calls(self):
        return [p for p, _ in self.calls if p.name == "roadmap_stages"]


def lectures(session, session_factory, llm, *which):
    env = environment(session)
    docs = []
    for name, parsed in which:
        doc = add(session, session_factory, env, name, parsed)
        extract(session, session_factory, doc, llm)
        docs.append(doc)
    graph.refresh_graph(session_factory, env.id, llm)
    roadmap.refresh_roadmap(session_factory, env.id, llm)
    session.expire_all()
    return env, docs


def outline(state) -> list[tuple[str, list[str]]]:
    return [(s.title, [c.name for c in s.concepts]) for s in state.stages]


def test_the_rules_order_the_roadmap_and_the_model_only_titles_it(
    session: Session, session_factory
):
    llm = Titling(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS])

    env, (scheduling, _) = lectures(
        session,
        session_factory,
        llm,
        ("scheduling.pdf", SCHEDULING),
        ("sync.pdf", SYNCHRONIZATION),
    )
    state = roadmap.state(session, env, llm)

    # Prerequisites first, a whole before its part; Semaphore, related to
    # nothing, stays with the stage taught just before it. The model answered
    # the last stage first: titles go by number, the order stays.
    assert state.state == "up_to_date"
    assert outline(state) == [
        ("Topic 1", ["Thread", "Round Robin", "Time Quantum"]),
        ("Topic 2", ["Critical Section", "Mutex", "Semaphore"]),
    ]
    assert [s.description for s in state.stages] == ["Learn topic 1.", "Learn topic 2."]
    assert all(s.written for s in state.stages)
    [prompt] = llm.roadmap_calls()
    assert "Stage 1:\n- Thread: The meaning of Thread.\n- Round Robin:" in prompt.user
    assert "Stage 2:\n- Critical Section:" in prompt.user
    # What each concept builds on, across stages too, and its sources.
    rr = state.stages[0].concepts[1]
    mutex = state.stages[1].concepts[1]
    assert [c.name for c in rr.builds_on] == ["Thread"]
    assert [c.name for c in mutex.builds_on] == ["Thread"]
    assert [d.filename for d in state.stages[1].documents] == ["sync.pdf"]
    assert [e.chunk_id for e in rr.evidence] == [chunks_of(session, scheduling)[1].id]
    assert state.cycles == []


def test_a_new_lecture_asks_only_for_the_titles_of_its_new_stages(
    session: Session, session_factory
):
    llm = Titling(
        RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS, MEMORY_CONCEPTS]
    )
    env, _ = lectures(
        session,
        session_factory,
        llm,
        ("scheduling.pdf", SCHEDULING),
        ("sync.pdf", SYNCHRONIZATION),
    )

    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    extract(session, session_factory, memory, llm)
    graph.refresh_graph(session_factory, env.id, llm)
    roadmap.refresh_roadmap(session_factory, env.id, llm)
    session.expire_all()
    state = roadmap.state(session, env, llm)

    _, second = llm.roadmap_calls()
    assert "Stage 1:\n- Paging:" in second.user
    assert "Thread" not in second.user
    assert outline(state) == [
        ("Topic 1", ["Thread", "Round Robin", "Time Quantum"]),
        ("Topic 2", ["Critical Section", "Mutex", "Semaphore"]),
        ("Topic 1", ["Paging", "TLB"]),  # its own answer, numbered on its own
    ]
    latest = session.scalars(
        select(GeneratedArtifact)
        .where(GeneratedArtifact.artifact_type == "learning_roadmap")
        .order_by(GeneratedArtifact.created_at.desc(), GeneratedArtifact.id)
    ).all()
    assert {a.metadata_json["asked"] for a in latest} == {2, 1}


def test_asking_again_asks_nothing(session: Session, session_factory):
    llm = Titling(RULES, [SCHEDULING_CONCEPTS])
    env, _ = lectures(session, session_factory, llm, ("scheduling.pdf", SCHEDULING))
    calls = len(llm.calls)

    artifact, write_now = roadmap.request_roadmap(session, env, llm)

    assert artifact.status == "ready"
    assert not write_now
    assert len(llm.calls) == calls


def test_a_failure_shows_plain_titles_and_asking_again_retries(
    session: Session, session_factory
):
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, Titling(RULES, [SCHEDULING_CONCEPTS]))
    graph.refresh_graph(session_factory, env.id, Titling(RULES))

    roadmap.refresh_roadmap(session_factory, env.id, FailingProvider())
    session.expire_all()
    failed = roadmap.state(session, env, FailingProvider())

    assert (failed.state, failed.error) == (
        "failed",
        "Could not reach Ollama. Is it running?",
    )
    assert outline(failed) == [
        ("Thread and 2 more", ["Thread", "Round Robin", "Time Quantum"])
    ]
    assert failed.stages[0].description is None and not failed.stages[0].written

    llm = Titling(RULES)
    roadmap.refresh_roadmap(session_factory, env.id, llm)
    session.expire_all()
    assert outline(roadmap.state(session, env, llm))[0][0] == "Topic 1"


def test_unusable_titles_are_left_plain(session: Session, session_factory):
    def titles(n):
        return [
            {"stage": 1, "title": "**Scheduling**", "description": "Learn it."},
            {"stage": 2, "title": "Synchronization", "description": "Learn locks."},
        ]

    llm = Titling(RULES, [SCHEDULING_CONCEPTS, SYNCHRONIZATION_CONCEPTS], titles=titles)

    env, _ = lectures(
        session,
        session_factory,
        llm,
        ("scheduling.pdf", SCHEDULING),
        ("sync.pdf", SYNCHRONIZATION),
    )
    state = roadmap.state(session, env, llm)
    artifact = session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.artifact_type == "learning_roadmap"
        )
    )

    assert [(s.title, s.written) for s in state.stages] == [
        ("Thread and 2 more", False),
        ("Synchronization", True),
    ]
    assert artifact.metadata_json["plain"] == 1


def test_the_roadmap_waits_for_the_graph(session: Session, session_factory):
    llm = Titling(RULES, [SCHEDULING_CONCEPTS])
    env = environment(session)
    doc = add(session, session_factory, env, "scheduling.pdf", SCHEDULING)
    extract(session, session_factory, doc, llm)  # the graph is not built yet

    assert roadmap.request_roadmap(session, env, llm) == (None, False)
    state = roadmap.state(session, env, llm)
    assert state.state == "waiting"
    assert outline(state) == [
        ("Thread and 2 more", ["Thread", "Round Robin", "Time Quantum"])
    ]
    assert llm.roadmap_calls() == []


def test_material_changing_before_the_titles_are_written_stores_nothing(
    session: Session, session_factory
):
    llm = Titling(RULES, [SCHEDULING_CONCEPTS, MEMORY_CONCEPTS])
    env, _ = lectures(session, session_factory, llm, ("scheduling.pdf", SCHEDULING))
    memory = add(session, session_factory, env, "memory.pdf", MEMORY)
    extract(session, session_factory, memory, llm)
    graph.refresh_graph(session_factory, env.id, llm)
    artifact, _ = roadmap.request_roadmap(session, env, llm)
    relate(  # a relationship drawn by hand changes the stages
        session, env, *concepts_named(session, env, "Spooling", "Buffering")
    )
    session.commit()

    roadmap.write_roadmap(session_factory, artifact.id, llm)

    session.expire_all()
    stale = session.get(GeneratedArtifact, artifact.id)
    assert stale.status == "failed"
    assert stale.error == "The material changed before the roadmap was written."
    assert len(llm.roadmap_calls()) == 1  # only the first roadmap's


def test_a_loop_of_prerequisites_is_shown_and_learned_together(session: Session):
    env = environment(session)
    a, b, c = concepts_named(session, env, "Process", "Thread", "Scheduler")
    relate(session, env, a, b)
    relate(session, env, b, c)
    relate(session, env, c, a)
    session.commit()

    state = roadmap.state(session, env, Titling({}))

    [cycle] = state.cycles
    assert [x.name for x in cycle.concepts] == ["Process", "Scheduler", "Thread"]
    [stage] = state.stages
    assert [x.name for x in stage.concepts] == ["Process", "Scheduler", "Thread"]
    assert all(x.in_cycle for x in stage.concepts)


def test_an_environment_without_concepts_has_no_roadmap(session: Session):
    env = environment(session)

    assert roadmap.request_roadmap(session, env, Titling({})) == (None, False)
    state = roadmap.state(session, env, Titling({}))
    assert (state.state, state.stages, state.cycles) == ("none", [], [])
    assert session.scalar(select(func.count()).select_from(ConceptRelationship)) == 0

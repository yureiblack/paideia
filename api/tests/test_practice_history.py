"""Tests for practice session history in app/services/practice.py.

Purpose: nothing records a practice session, so the history works sessions
out from the answers (decision record 19). Answers less than 30 minutes
apart are one session, 30 minutes or more start another; the newest come
first and only the last 20 are shown; each counts its answers, the ones
recalled and the concepts in the order first answered. Only the
environment's own answers count, retired items' answers stay, and a
concept's answers go with it. Also the overview's strong flag, which a
roadmap stage's progress reads.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Concept
from app.schemas import AttemptCreate
from app.services import practice
from tests.test_concepts import environment
from tests.test_graph import RULES, SCHEDULING_CONCEPTS
from tests.test_practice import Practising, items_of, named, prepare, scheduling

START = datetime(2026, 11, 14, 9, tzinfo=UTC)


def ready(session, session_factory, names=("Thread", "Round Robin")):
    llm = Practising(RULES, [SCHEDULING_CONCEPTS])
    env, _ = scheduling(session, session_factory, llm)
    prepare(session, session_factory, env, list(names), llm)
    cards = {n: items_of(session, named(session, env, n))["flashcard"] for n in names}
    return env, cards, llm


def knew(session, card, at, right=True):
    practice.answer(session, card, AttemptCreate(knew=right), at)


def test_answers_under_thirty_minutes_apart_are_one_session(
    session: Session, session_factory
):
    names = ("Thread", "Round Robin", "Time Quantum")
    env, cards, _ = ready(session, session_factory, names=names)
    thread, robin, quantum = (cards[n] for n in names)
    # First answered in an order that is neither alphabetical nor reversed.
    knew(session, thread, START)
    knew(session, robin, START + timedelta(minutes=10), right=False)
    knew(session, quantum, START + timedelta(minutes=15))
    # 29 minutes 59 seconds after the last answer: still the same session.
    knew(session, thread, START + timedelta(minutes=44, seconds=59))
    # Exactly 30 minutes later: a new one.
    knew(session, robin, START + timedelta(minutes=74, seconds=59))

    history = practice.history(session, env.id)

    assert [
        (s.started_at, s.ended_at, s.answers, s.recalled, [c.name for c in s.concepts])
        for s in history
    ] == [
        (
            START + timedelta(minutes=74, seconds=59),
            START + timedelta(minutes=74, seconds=59),
            1,
            1,
            ["Round Robin"],
        ),
        (
            START,
            START + timedelta(minutes=44, seconds=59),
            4,
            3,
            ["Thread", "Round Robin", "Time Quantum"],
        ),
    ]


def test_only_the_last_sessions_are_shown(session: Session, session_factory):
    env, cards, _ = ready(session, session_factory, names=("Thread",))
    for day in range(practice.HISTORY + 3):
        knew(session, cards["Thread"], START + timedelta(days=day))

    history = practice.history(session, env.id)

    assert len(history) == practice.HISTORY
    assert history[0].started_at == START + timedelta(days=practice.HISTORY + 2)
    assert history[-1].started_at == START + timedelta(days=3)


def test_only_the_environments_own_answers_count(session: Session, session_factory):
    env, cards, _ = ready(session, session_factory, names=("Thread",))
    other, other_cards, _ = ready(session, session_factory, names=("Thread",))
    knew(session, cards["Thread"], START)
    knew(session, other_cards["Thread"], START + timedelta(minutes=1))
    knew(session, other_cards["Thread"], START + timedelta(minutes=2))

    assert [s.answers for s in practice.history(session, env.id)] == [1]
    assert [s.answers for s in practice.history(session, other.id)] == [2]
    assert practice.history(session, environment(session).id) == []


def test_retired_items_answers_stay_and_a_removed_concepts_go(
    session: Session, session_factory
):
    env, cards, _ = ready(session, session_factory)
    knew(session, cards["Thread"], START)
    knew(session, cards["Round Robin"], START + timedelta(minutes=1))
    cards["Thread"].retired_at = START + timedelta(hours=1)
    session.commit()

    assert [s.answers for s in practice.history(session, env.id)] == [2]

    session.execute(
        delete(Concept).where(Concept.id == cards["Round Robin"].concept_id)
    )
    session.commit()

    (only,) = practice.history(session, env.id)
    assert (only.answers, [c.name for c in only.concepts]) == (1, ["Thread"])


def test_the_overview_marks_concepts_recalled_after_a_long_gap_strong(
    session: Session, session_factory
):
    env, cards, llm = ready(session, session_factory)
    start = datetime.now(UTC) + timedelta(minutes=1)
    for days in (0, 1, 3):
        knew(session, cards["Thread"], start + timedelta(days=days))
    knew(session, cards["Round Robin"], start)

    view = practice.overview(session, env, llm, now=start + timedelta(days=3))

    strong = {c.name: c.strong for c in view.concepts if c.items}
    assert strong == {"Thread": True, "Round Robin": False}
    assert [n.name for n in view.recently_strong] == ["Thread"]


def test_the_history_endpoint(client: TestClient):
    env = client.post("/api/environments", json={"name": "History"}).json()

    response = client.get(f"/api/environments/{env['id']}/practice/history")

    assert (response.status_code, response.json()) == (200, [])
    missing = client.get(
        "/api/environments/00000000-0000-0000-0000-000000000000/practice/history"
    )
    assert missing.status_code == 404

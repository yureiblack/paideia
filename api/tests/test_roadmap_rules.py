"""Tests for the roadmap's structure in app/roadmap.py.

Purpose: the fixed rules that put concepts in stages and in order.
Prerequisites always come first; ties follow the material's own reading
order; loops are found, kept together and reported; stages are groups within
one document, never glued together by a link across documents; isolated
concepts stay where they were taught; big stages are split. The model never
orders anything; these rules do.
"""

import random
import uuid
from itertools import pairwise

from app.roadmap import (
    MAX_STAGE,
    Link,
    Node,
    build,
    plain_title,
    stage_key,
)

LECTURES = [uuid.uuid4() for _ in range(3)]


def node(name, lecture=0, at=1, evidence=1, definition=None):
    return Node(
        id=uuid.uuid4(),
        name=name,
        normalized_name=name.lower(),
        definition=definition or f"About {name}.",
        position=(lecture, at),
        home=LECTURES[lecture],
        evidence=evidence,
    )


def before(a, b):
    return Link(a.id, b.id, "PREREQUISITE_OF")


def part_of(part, whole):
    return Link(part.id, whole.id, "PART_OF")


def related(a, b):
    return Link(a.id, b.id, "RELATED_TO")


def names(nodes, roadmap) -> list[list[str]]:
    by_id = {n.id: n.name for n in nodes}
    return [[by_id[i] for i in stage] for stage in roadmap.stages]


def test_a_prerequisite_comes_first_even_when_taught_later():
    avoidance, deadlock = node("Deadlock avoidance", at=1), node("Deadlock", at=2)
    nodes = [avoidance, deadlock]

    roadmap = build(nodes, [before(deadlock, avoidance)])

    assert names(nodes, roadmap) == [["Deadlock", "Deadlock avoidance"]]


def test_otherwise_more_evidence_comes_first_then_reading_order():
    mutex = node("Mutex", at=1)
    race = node("Race condition", at=2, evidence=3)
    semaphore = node("Semaphore", at=3)
    nodes = [mutex, race, semaphore]

    roadmap = build(nodes, [related(mutex, race), related(race, semaphore)])

    assert names(nodes, roadmap) == [["Race condition", "Mutex", "Semaphore"]]


def test_a_whole_comes_before_its_parts_unless_a_prerequisite_says_otherwise():
    fifo, policy = node("FIFO", at=1, evidence=3), node("Replacement policy", at=2)
    quantum, rr = (
        node("Time quantum", lecture=1, at=1),
        node("Round robin", lecture=1, at=2),
    )
    nodes = [fifo, policy, quantum, rr]

    roadmap = build(
        nodes,
        [part_of(fifo, policy), part_of(quantum, rr), before(quantum, rr)],
    )

    assert names(nodes, roadmap) == [
        ["Replacement policy", "FIFO"],
        ["Time quantum", "Round robin"],
    ]


def test_a_link_across_documents_never_merges_their_stages():
    thread, switch = node("Thread", 0, 1), node("Context switch", 0, 2)
    tlb, paging = node("TLB", 1, 1), node("Paging", 1, 2)
    nodes = [thread, switch, tlb, paging]

    roadmap = build(
        nodes, [related(thread, switch), related(tlb, paging), related(switch, tlb)]
    )

    assert names(nodes, roadmap) == [["Thread", "Context switch"], ["TLB", "Paging"]]


def test_stages_follow_prerequisites_across_documents_then_reading_order():
    avoidance, banker = node("Deadlock avoidance", 0, 1), node("Banker", 0, 2)
    paging, tlb = node("Paging", 1, 1), node("TLB", 1, 2)
    deadlock, wait = node("Deadlock", 2, 1), node("Circular wait", 2, 2)
    nodes = [avoidance, banker, paging, tlb, deadlock, wait]

    roadmap = build(
        nodes,
        [
            related(avoidance, banker),
            related(paging, tlb),
            related(deadlock, wait),
            before(deadlock, avoidance),  # the third lecture's comes first
        ],
    )

    assert names(nodes, roadmap) == [
        ["Paging", "TLB"],
        ["Deadlock", "Circular wait"],
        ["Deadlock avoidance", "Banker"],
    ]


def test_a_concept_without_relationships_stays_where_it_was_taught():
    aging = node("Aging", 0, 1)  # first, alone: joins the stage after it
    sjf, srtf = node("SJF", 0, 2), node("SRTF", 0, 3)
    average = node("Exponential average", 0, 4)  # alone: joins the stage before
    paging, frames = node("Paging", 1, 1), node("Frames", 1, 2)  # nothing related
    nodes = [aging, sjf, srtf, average, paging, frames]

    roadmap = build(nodes, [before(sjf, srtf)])

    assert names(nodes, roadmap) == [
        ["Aging", "SJF", "SRTF", "Exponential average"],
        ["Paging", "Frames"],
    ]


def test_a_loop_of_prerequisites_is_reported_and_learned_together():
    a, b = node("Process", at=1), node("Thread", at=2)
    c = node("Scheduler", at=3, evidence=3)  # more evidence, but in a loop
    d = node("Dispatcher", at=4)
    nodes = [a, b, c, d]

    roadmap = build(nodes, [before(b, c), before(c, a), before(a, b), before(c, d)])

    assert names(nodes, roadmap) == [["Process", "Thread", "Scheduler", "Dispatcher"]]
    [cycle] = roadmap.cycles
    assert cycle.concepts == (a.id, b.id, c.id)
    assert set(cycle.links) == {(b.id, c.id), (c.id, a.id), (a.id, b.id)}


def test_a_concept_between_two_stages_joins_the_one_before_it():
    a, b = node("Paging", at=1), node("Page table", at=2)
    alone = node("Frames", at=3)
    c, d = node("TLB", at=4), node("TLB miss", at=5)
    nodes = [a, b, alone, c, d]

    roadmap = build(nodes, [related(a, b), related(c, d)])

    assert names(nodes, roadmap) == [
        ["Paging", "Page table", "Frames"],
        ["TLB", "TLB miss"],
    ]


def test_a_stage_comes_where_its_first_concept_is_taught():
    a, b = node("Paging", at=1), node("Frames", at=2)
    c, d = node("TLB", at=3), node("Page table", at=4)
    nodes = [a, b, c, d]

    roadmap = build(nodes, [related(a, d), related(b, c)])

    assert names(nodes, roadmap) == [["Paging", "Page table"], ["Frames", "TLB"]]


def test_a_loop_across_documents_keeps_unrelated_neighbours_apart():
    # Without the loop kept together first, Semaphore and Mutex would each
    # join their lecture's other stage, and the loop would merge both.
    sem, wait = node("Semaphore", 0, 1), node("Wait", 0, 2)
    signal = node("Signal", 0, 3)
    mutex, lock = node("Mutex", 1, 1), node("Lock", 1, 2)
    unlock = node("Unlock", 1, 3)
    nodes = [sem, wait, signal, mutex, lock, unlock]

    roadmap = build(
        nodes,
        [
            related(wait, signal),
            related(lock, unlock),
            before(sem, mutex),
            before(mutex, sem),
        ],
    )

    assert names(nodes, roadmap) == [
        ["Semaphore", "Mutex"],
        ["Wait", "Signal"],
        ["Lock", "Unlock"],
    ]


def test_a_loop_across_documents_is_one_stage():
    a, b = node("Semaphore", 0, 1), node("Mutex", 1, 1)
    nodes = [a, b]

    roadmap = build(nodes, [before(a, b), before(b, a)])

    assert names(nodes, roadmap) == [["Semaphore", "Mutex"]]
    assert len(roadmap.cycles) == 1


def test_stages_whose_prerequisites_loop_are_merged():
    a1, a2 = node("Critical section", 0, 1), node("Priority inversion", 0, 2)
    b1, b2 = node("Mutex", 1, 1), node("Race condition", 1, 2)
    nodes = [a1, a2, b1, b2]

    roadmap = build(
        nodes,
        [related(a1, a2), related(b1, b2), before(a1, b1), before(b2, a2)],
    )

    [stage] = names(nodes, roadmap)
    assert stage.index("Critical section") < stage.index("Mutex")
    assert stage.index("Race condition") < stage.index("Priority inversion")
    assert roadmap.cycles == ()  # no concept loops; only the stages did


def test_a_big_stage_is_split_evenly_in_order():
    nodes = [node(f"Concept {n:02}", at=n) for n in range(MAX_STAGE + 2)]
    links = [related(x, y) for x, y in pairwise(nodes)]

    roadmap = build(nodes, links)

    assert [len(s) for s in roadmap.stages] == [5, 5]
    assert [i for s in roadmap.stages for i in s] == [n.id for n in nodes]


def test_the_same_material_always_gives_the_same_roadmap():
    nodes = [node(f"C{n}", lecture=n % 3, at=n, evidence=n % 2 + 1) for n in range(12)]
    links = [related(nodes[n], nodes[n + 3]) for n in range(9)] + [
        before(nodes[7], nodes[1]),
        part_of(nodes[4], nodes[10]),
    ]
    first = build(nodes, links)

    for seed in range(5):
        shuffled_nodes, shuffled_links = nodes[:], links[:]
        random.Random(seed).shuffle(shuffled_nodes)
        random.Random(seed).shuffle(shuffled_links)
        assert build(shuffled_nodes, shuffled_links) == first


def test_links_to_unknown_concepts_and_to_themselves_are_ignored():
    a, b = node("Paging", at=1), node("TLB", at=2)
    nodes = [a, b]

    roadmap = build(
        nodes,
        [
            Link(a.id, a.id, "PREREQUISITE_OF"),
            Link(uuid.uuid4(), b.id, "PREREQUISITE_OF"),
        ],
    )

    assert names(nodes, roadmap) == [["Paging", "TLB"]]
    assert roadmap.cycles == ()


def test_a_stages_key_follows_what_the_model_would_see():
    a, b = node("Paging"), node("TLB", at=2)
    by_id = {a.id: a, b.id: b}
    renamed = node("Paging", definition="Something else.")
    by_id[renamed.id] = renamed

    assert stage_key([a.id, b.id], by_id) == stage_key([a.id, b.id], by_id)
    assert stage_key([a.id, b.id], by_id) != stage_key([b.id, a.id], by_id)
    assert stage_key([a.id], by_id) != stage_key([renamed.id], by_id)


def test_plain_titles():
    assert plain_title(["Deadlock"]) == "Deadlock"
    assert plain_title(["Paging", "TLB"]) == "Paging and TLB"
    assert plain_title(["Deadlock", "Safe state", "Banker"]) == "Deadlock and 2 more"

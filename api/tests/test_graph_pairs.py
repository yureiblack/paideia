"""Tests for candidate pairs and decisions in app/graph.py.

Purpose: the fixed rules that decide which pairs of concepts the model is
asked about, how a pair is fingerprinted, and what each decision means for
the graph. The model never chooses a pair; these rules do.
"""

import uuid

import pytest

from app.graph import (
    MIN_CONFIDENCE,
    ConceptInfo,
    Passage,
    edge_for,
    find_pairs,
    name_forms,
    words,
)

DOC_A, DOC_B = uuid.uuid4(), uuid.uuid4()


def concept(name, aliases=()):
    from app.concepts import normalize

    return ConceptInfo(
        uuid.uuid4(), name, normalize(name), f"About {name}.", tuple(aliases)
    )


def passage(text, doc=DOC_A, ordinal=1):
    return Passage(uuid.uuid4(), doc, ordinal, text, f"hash of {text}")


def test_words_are_simplified_for_matching_whole_names():
    assert words("Threads share an address space.") == " thread share an address space "
    assert " thread " in words("Each thread has its own stack.")
    assert " mutex " not in words("A mutexes-free design")  # whole words only


def test_name_forms_include_aliases_and_drop_bracketed_parts():
    tlb = concept("Translation Lookaside Buffer (TLB)", aliases=["TLB"])
    assert name_forms(tlb) == {" translation lookaside buffer ", " tlb "}


def test_concepts_sharing_an_evidence_passage_are_a_pair():
    p = passage("Round robin gives every task a time quantum.")
    rr, quantum = concept("Round Robin"), concept("Time Quantum")

    [pair] = find_pairs([rr, quantum], {rr.id: {p.id}, quantum.id: {p.id}}, {p.id: p})

    assert {pair.a.name, pair.b.name} == {"Round Robin", "Time Quantum"}
    assert pair.passages == (p,)


def test_a_passage_naming_another_concept_pairs_them_across_documents():
    # The mutex passage, in the synchronization lecture, names threads; Thread
    # comes from the scheduling lecture.
    mutex_passage = passage("A mutex lets only one of the threads in at a time.", DOC_B)
    thread_passage = passage("A thread is a sequence of execution.", DOC_A)
    mutex, thread = concept("Mutex"), concept("Thread")

    [pair] = find_pairs(
        [mutex, thread],
        {mutex.id: {mutex_passage.id}, thread.id: {thread_passage.id}},
        {mutex_passage.id: mutex_passage, thread_passage.id: thread_passage},
    )

    assert (pair.a.name, pair.b.name) == ("Mutex", "Thread")  # normalized order
    assert pair.passages == (mutex_passage,)
    assert pair.document_id == DOC_B


def test_unconnected_concepts_are_not_a_pair():
    p1, p2 = passage("Paging maps pages to frames."), passage("A semaphore counts.")
    paging, semaphore = concept("Paging"), concept("Semaphore")

    assert (
        find_pairs(
            [paging, semaphore],
            {paging.id: {p1.id}, semaphore.id: {p2.id}},
            {p1.id: p1, p2.id: p2},
        )
        == []
    )


def test_pairs_come_best_supported_first_and_are_bounded(monkeypatch):
    from app import graph

    p1, p2 = (
        passage("Deadlock and circular wait."),
        passage("Circular wait in deadlock.", ordinal=2),
    )
    p3 = passage("Safe states avoid deadlock.", ordinal=3)
    deadlock, wait, safe = (
        concept("Deadlock"),
        concept("Circular Wait"),
        concept("Safe State"),
    )
    evidence = {
        deadlock.id: {p1.id, p2.id, p3.id},
        wait.id: {p1.id, p2.id},
        safe.id: {p3.id},
    }
    passages = {p.id: p for p in (p1, p2, p3)}

    pairs = find_pairs([deadlock, wait, safe], evidence, passages)
    assert [len(p.passages) for p in pairs] == [2, 1]

    monkeypatch.setattr(graph, "MAX_PAIRS", 1)
    assert len(find_pairs([deadlock, wait, safe], evidence, passages)) == 1


def test_a_pairs_key_changes_with_its_passages_text_only():
    p = passage("Round robin gives every task a time quantum.")
    rr, quantum = concept("Round Robin"), concept("Time Quantum")
    [pair] = find_pairs([rr, quantum], {rr.id: {p.id}, quantum.id: {p.id}}, {p.id: p})
    same = Passage(uuid.uuid4(), DOC_B, 9, p.text, p.content_hash)
    edited = Passage(p.id, DOC_A, 1, p.text + " Edited.", "another hash")

    [again] = find_pairs(
        [rr, quantum], {rr.id: {same.id}, quantum.id: {same.id}}, {same.id: same}
    )
    [changed] = find_pairs(
        [rr, quantum],
        {rr.id: {edited.id}, quantum.id: {edited.id}},
        {edited.id: edited},
    )

    assert again.key == pair.key
    assert changed.key != pair.key


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("a_before_b", ("a", "b", "PREREQUISITE_OF")),
        ("b_before_a", ("b", "a", "PREREQUISITE_OF")),
        ("a_part_of_b", ("a", "b", "PART_OF")),
        ("b_part_of_a", ("b", "a", "PART_OF")),
        ("related", ("a", "b", "RELATED_TO")),
    ],
)
def test_each_decision_means_one_edge(decision, expected):
    p = passage("Deadlock avoidance prevents deadlock.")
    deadlock, avoidance = concept("Deadlock"), concept("Deadlock Avoidance")
    [pair] = find_pairs(
        [deadlock, avoidance], {deadlock.id: {p.id}, avoidance.id: {p.id}}, {p.id: p}
    )
    ids = {"a": pair.a.id, "b": pair.b.id}

    edge = edge_for(pair, decision, 0.9)

    assert (edge.source, edge.target, edge.relationship_type) == (
        ids[expected[0]],
        ids[expected[1]],
        expected[2],
    )


def test_none_and_low_confidence_mean_no_edge_and_unknown_decisions_are_refused():
    p = passage("Deadlock avoidance prevents deadlock.")
    deadlock, avoidance = concept("Deadlock"), concept("Deadlock Avoidance")
    [pair] = find_pairs(
        [deadlock, avoidance], {deadlock.id: {p.id}, avoidance.id: {p.id}}, {p.id: p}
    )

    assert edge_for(pair, "none", 1.0) is None
    assert edge_for(pair, "a_before_b", MIN_CONFIDENCE - 0.01) is None
    assert edge_for(pair, "a_before_b", MIN_CONFIDENCE) is not None
    with pytest.raises(ValueError):
        edge_for(pair, "a_causes_b", 0.9)

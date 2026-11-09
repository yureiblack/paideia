"""Tests for concept names and validation in app/concepts.py.

Purpose: the deterministic rules that decide what the model's proposals are
called and whether they are kept. The names come from a real extraction of
three lectures, made while planning this phase.
"""

from types import SimpleNamespace

import pytest

from app.concepts import (
    MAX_ALIASES,
    clean_aliases,
    normalize,
    singular,
    split_name,
    validate,
)


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("Shortest Job First (SJF)", "shortest job first"),
        ("Mutex (Mutual Exclusion)", "mutex"),
        ("FIFO (First-In-First-Out) Page Replacement", "fifo page replacement"),
        ("Translation Lookaside Buffer (TLB)", "translation lookaside buffer"),
        ("Belady’s Anomaly", "belady's anomaly"),
        ("Belady's anomaly", "belady's anomaly"),
        ("Banker's Algorithm", "banker's algorithm"),
        ("Working-Set Model", "working set model"),
        (
            "Bounded-Buffer Producer-Consumer Problem",
            "bounded buffer producer consumer problem",
        ),
        ("Threads", "thread"),
        ("Thread", "thread"),
        ("The Semaphores", "semaphore"),
        ("Processes", "process"),
        ("Page Replacement Policies", "page replacement policy"),
        ("CPU caches", "cpu cache"),
        ("  Round   Robin  ", "round robin"),
        ("I/O Scheduling", "i o scheduling"),
        ("ﬁle systems", "file system"),  # the ligature folds to "fi"
        ("(SJF)", ""),
        ("!!!", ""),
    ],
)
def test_names_normalize_deterministically(name, normalized):
    assert normalize(name) == normalized


@pytest.mark.parametrize(
    ("word", "single"),
    [
        ("processes", "process"),
        ("addresses", "address"),
        ("policies", "policy"),
        ("threads", "thread"),
        ("caches", "cache"),
        ("address", "address"),
        ("status", "status"),
        ("analysis", "analysis"),
        ("bus", "bus"),
        ("tlb", "tlb"),
        ("os", "os"),
    ],
)
def test_singular_is_conservative(word, single):
    assert singular(word) == single


def test_bracketed_parts_are_split_off_as_aliases():
    assert split_name("Shortest Job First (SJF)") == ("Shortest Job First", ["SJF"])
    assert split_name("FIFO (First-In-First-Out) Page Replacement") == (
        "FIFO Page Replacement",
        ["First-In-First-Out"],
    )
    assert split_name("Paging") == ("Paging", [])


def test_aliases_keep_names_and_drop_descriptions_repeats_and_blanks():
    kept = clean_aliases(
        [
            "",
            "TLB",
            "tlb",  # the same alias again
            "Translation Lookaside Buffers",  # the concept's own name
            "associative cache of recent page-to-frame translations",  # description
            "evicting a victim page",  # a description, though only four words
            "TLB hit/miss",  # not really an alias, but nothing marks it as such
        ],
        normalize("Translation Lookaside Buffer"),
    )
    assert kept == ["TLB", "TLB hit/miss"]
    assert len(clean_aliases([f"name {n}" for n in "abcdefgh"])) == MAX_ALIASES


def proposal(name, definition="A definition.", aliases=(), sources=(1,)):
    return SimpleNamespace(
        name=name, definition=definition, aliases=list(aliases), sources=list(sources)
    )


def test_validation_drops_what_cannot_be_trusted_and_counts_it():
    kept, dropped = validate(
        [
            proposal("Paging", sources=[1]),
            proposal("(TLB)"),  # nothing left once brackets go
            proposal("1234"),  # no letters
            proposal("Deadlock", definition="   "),  # no definition
            proposal("Thrashing", sources=[9]),  # a passage it was not given
            proposal("x" * 81),  # too long
        ],
        allowed={1, 2, 3},
    )

    assert [c.normalized_name for c in kept] == ["paging"]
    assert dropped == 5


def test_proposals_with_the_same_name_are_merged():
    kept, dropped = validate(
        [
            proposal("Thread", "First definition.", ["lightweight process"], [1]),
            proposal(
                "Threads", "Second definition.", ["LWP", "lightweight process"], [2, 1]
            ),
        ],
        allowed={1, 2},
    )

    [thread] = kept
    assert dropped == 0
    assert (thread.name, thread.definition) == ("Thread", "First definition.")
    assert thread.passages == [1, 2]
    assert thread.aliases == ["lightweight process", "LWP"]


@pytest.mark.parametrize(
    "description",
    [
        "disk busy all the time",
        "dividing physical memory into frames",
        "processor idle waiting for disk",
        "loading a page only when touched",
    ],
)
def test_descriptions_from_the_prototype_are_not_kept_as_aliases(description):
    assert clean_aliases([description]) == []


def test_real_alternative_names_are_kept():
    names = [
        "SJF",
        "LRU",
        "First-In-First-Out",
        "mutual exclusion",
        "Least Recently Used",
    ]
    assert clean_aliases(names) == names


def test_bracketed_abbreviations_become_aliases():
    [sjf], _ = validate([proposal("Shortest Job First (SJF)", aliases=[""])], {1})

    assert (sjf.name, sjf.normalized_name, sjf.aliases) == (
        "Shortest Job First",
        "shortest job first",
        ["SJF"],
    )


def test_aliases_never_merge_concepts():
    kept, _ = validate(
        [
            proposal("Mutex", aliases=["lock"]),
            proposal("Lock", aliases=["mutex"]),
        ],
        allowed={1},
    )

    assert sorted(c.normalized_name for c in kept) == ["lock", "mutex"]

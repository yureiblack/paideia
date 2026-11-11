"""Tests for prompt templates in app/prompting.py and app/prompts/.

Purpose: a prompt renders with its version, every placeholder must be filled,
a file must have its two parts, and a released prompt never changes: editing
one fails here, because answers already generated record that version. A
change belongs in a new file, v2, added to RELEASED below.
"""

import hashlib

import pytest

from app import prompting

# Every released prompt and the SHA-256 of its file.
RELEASED = {
    "concept_extraction/v1": "3a23ef95c5aca4f19d73c111e47566c7d869e762213a88420b43ea98ec89b913",
    "combine_summaries/v1": "0107b851c11f171d2b2ad22e1023012a5cfaea64944b7f8f426aeb81fc1b026a",
    "document_summary/v1": "d5bffc7d775b7ec4a5f0b661003f63c4b134eaf5aa30564b6806f7387de30dd9",
    "environment_summary/v1": "965c483c92c14c612e891f854bb8fed1d3ecb87019c9587ed6a65cd137610069",
    "practice_items/v1": "548781c5f829fc7171162eb425fca9f15e1059860be7cc540735a43374eacad8",
    "relationship/v1": "1990b4c79f86eed0f846939af9a0aafcd61e3b3b220b7a7251bd5510d3fd4925",
    "roadmap_stages/v1": "28d49ca8cffcb2a49b6102a51353291ebe1b867b5814e15f2b48e7508e583b33",
}


def test_released_prompts_are_never_edited():
    found = {
        f"{path.parent.name}/{path.stem}": hashlib.sha256(path.read_bytes()).hexdigest()
        for path in prompting.PROMPTS_DIR.glob("*/*.txt")
    }

    assert found == RELEASED, (
        "A prompt file was added or changed. Released prompts are never edited: "
        "write the change as a new version and add it to RELEASED."
    )


def test_a_prompt_renders_with_its_version():
    prompt = prompting.render(
        "document_summary",
        "v1",
        filename="Lecture 4.pdf",
        passages="[1] Paging maps pages to frames.",
        min_points=3,
        max_points=7,
    )

    assert prompt.id == "document_summary/v1"
    assert "Use only the numbered passages" in prompt.system
    assert "Document: Lecture 4.pdf" in prompt.user
    assert "[1] Paging maps pages to frames." in prompt.user
    assert "between 3 and 7 key points" in prompt.user
    assert "$" not in prompt.system + prompt.user


def test_a_prompt_can_hold_named_parts_besides_system_and_user():
    pair = prompting.part("relationship", "v1", "pair").substitute(
        number=1,
        passages="2",
        a="Deadlock",
        a_definition="A state.",
        b="Deadlock Avoidance",
        b_definition="A strategy.",
    )
    prompt = prompting.render("relationship", "v1", passages="[2] ...", pairs=pair)

    assert pair.startswith("Pair 1 (passages 2): Deadlock: A state. |")
    assert "1. Deadlock must be understood before Deadlock Avoidance." in pair
    assert "6. The passages do not show a relationship." in pair
    assert prompt.user.endswith(pair)
    assert "=== pair" not in prompt.user


def test_every_placeholder_must_be_given():
    with pytest.raises(KeyError):
        prompting.render("document_summary", "v1", filename="Lecture 4.pdf")


def test_a_prompt_file_needs_a_system_and_a_user_part(tmp_path, monkeypatch):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "v1.txt").write_text("=== system\nOnly a system part.\n")
    monkeypatch.setattr(prompting, "PROMPTS_DIR", tmp_path)

    with pytest.raises(ValueError, match="needs one"):
        prompting.render("broken", "v1")

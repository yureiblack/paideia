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
    "combine_summaries/v1": "0107b851c11f171d2b2ad22e1023012a5cfaea64944b7f8f426aeb81fc1b026a",
    "document_summary/v1": "d5bffc7d775b7ec4a5f0b661003f63c4b134eaf5aa30564b6806f7387de30dd9",
    "environment_summary/v1": "965c483c92c14c612e891f854bb8fed1d3ecb87019c9587ed6a65cd137610069",
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


def test_every_placeholder_must_be_given():
    with pytest.raises(KeyError):
        prompting.render("document_summary", "v1", filename="Lecture 4.pdf")


def test_a_prompt_file_needs_a_system_and_a_user_part(tmp_path, monkeypatch):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "v1.txt").write_text("=== system\nOnly a system part.\n")
    monkeypatch.setattr(prompting, "PROMPTS_DIR", tmp_path)

    with pytest.raises(ValueError, match="needs one"):
        prompting.render("broken", "v1")

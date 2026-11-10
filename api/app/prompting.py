"""Prompt templates, stored as versioned files.

Purpose
-------
What the model is asked is as much a part of its answer as the model itself,
so prompts live in files, one per version, under app/prompts/<name>/:
app/prompts/document_summary/v1.txt is version v1 of the document summary
prompt. Every answer records the version it came from (Prompt.id, such as
"document_summary/v1"). A released version is never edited: a change is a new
file, v2, and tests/test_prompting.py fails if a released file changes.

A file has a system part and a user part, introduced by lines reading
"=== system" and "=== user", and may have further named parts, such as the
"=== pair" template the relationship prompt repeats once per pair; part()
returns one. Placeholders are written $name, the syntax of Python's
string.Template, so the braces of any JSON in a prompt never clash with them.
Every placeholder must be given a value.
"""

import re
from pathlib import Path
from string import Template

from app.llm import Prompt

PROMPTS_DIR = Path(__file__).parent / "prompts"

_PART = re.compile(r"^=== (\w+)$", re.MULTILINE)


def _parts(name: str, version: str) -> dict[str, str]:
    path = PROMPTS_DIR / name / f"{version}.txt"
    pieces = _PART.split(path.read_text(encoding="utf-8"))
    # split() yields the text before the first marker, then marker, part, ...
    parts = dict(
        zip(pieces[1::2], (piece.strip() for piece in pieces[2::2]), strict=True)
    )
    if not {"system", "user"} <= set(parts):
        raise ValueError(f"{path} needs one '=== system' and one '=== user' part.")
    return parts


def part(name: str, version: str, part_name: str) -> Template:
    """One further part of a prompt version, as a template to fill."""
    return Template(_parts(name, version)[part_name])


def render(name: str, version: str, **values: object) -> Prompt:
    """The named prompt version with its placeholders filled in."""
    parts = _parts(name, version)
    text = {str(key): str(value) for key, value in values.items()}
    return Prompt(
        name=name,
        version=version,
        system=Template(parts["system"]).substitute(text),
        user=Template(parts["user"]).substitute(text),
    )

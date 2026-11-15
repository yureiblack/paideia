"""The name an uploaded file is shown by.

Purpose
-------
Files on disk are named by document id (app/storage.py), so the name a client
sends is only ever displayed: in the document list, in citations, in job
titles. It can still mislead or break a page, so it is cleaned before it is
stored (decision record 21):

- only the last part of a path is kept, whichever slash it uses, so
  "../../etc/notes.pdf" is shown as "notes.pdf";
- Unicode is normalised (NFC), so the same name typed two ways is stored
  the same way;
- control and formatting characters are removed. Among them are the
  invisible right-to-left override (U+202E), which reverses the text after
  it, so a name ending "fdp.exe" can be displayed as one ending "exe.pdf";
- runs of whitespace, line breaks included, become one space;
- a name longer than MAX_LENGTH is cut, keeping its extension.

A name with nothing left, or only dots, is refused.
"""

import re
import unicodedata
from pathlib import PurePosixPath

MAX_LENGTH = 200
MAX_EXTENSION = 10  # longer "extensions" are part of the name, not a type

# Cc: control characters. Cf: formatting characters, such as the zero-width
# space and the bidirectional overrides. Zl and Zp: line and paragraph
# separators, which become spaces like other whitespace.
_REMOVED = {"Cc", "Cf", "Cs", "Co", "Cn"}
_SPACES = {"Zl", "Zp", "Zs"}


class BadFilename(ValueError):
    """A name with nothing displayable left."""


def display_name(raw: str) -> str:
    name = PurePosixPath(raw.replace("\\", "/")).name
    name = unicodedata.normalize("NFC", name)
    kept = []
    for char in name:
        category = unicodedata.category(char)
        if category in _SPACES or char.isspace():
            kept.append(" ")
        elif category not in _REMOVED:
            kept.append(char)
    name = re.sub(r" +", " ", "".join(kept)).strip()
    if not name or set(name) == {"."}:
        raise BadFilename("filename must name a file")
    if len(name) > MAX_LENGTH:
        suffix = PurePosixPath(name).suffix
        if len(suffix) > MAX_EXTENSION:
            suffix = ""
        name = name[: MAX_LENGTH - len(suffix)].rstrip() + suffix
    return name

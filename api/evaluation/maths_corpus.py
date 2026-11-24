"""The maths benchmark's lectures: from their source to typeset PDFs, and
what each page of those PDFs says.

Purpose
-------
To measure how well the model reads maths, the true LaTeX of every formula on
a page must be known. So the lectures are written for the benchmark in the
very form the model is asked to write a page in (app/prompts/
page_transcription): Markdown, with maths in LaTeX between dollar signs. Each
is typeset with TeX, as most textbooks are, and the PDF is read by the app
exactly as an upload would be. What the source says on a page is then the
perfect reading of that page.

The source format is a small subset of Markdown, which keeps the conversion
exact:

- "# " starts the title, the first line; "## " a section heading;
- a paragraph is one or more lines of prose, with inline maths between
  single dollar signs and bold words between double asterisks;
- displayed maths is a block of its own between double dollar signs, and may
  run over several lines;
- a list is a block whose every line starts with "- ", or with a number and
  a full stop.

Each block is converted to LaTeX with a label after it, and TeX writes in its
auxiliary file the page each label landed on. A paragraph is never split
across two pages (\\interlinepenalty), so every block is on exactly one page
and each page's truth is the blocks on it. Displayed maths is attached to the
paragraph before it, as LaTeX authors write it, and TeX never breaks a page
just before a display.

Typesetting needs Tectonic (https://tectonic-typesetting.github.io), a
self-contained TeX engine. It is needed only to run the benchmark, never by
the app. Its first run downloads the TeX packages it uses, about 40 MB.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "docs" / "evaluation" / "maths" / "corpus"

# Every build is dated the same day, so the same source always makes the
# same PDF, byte for byte.
SOURCE_DATE_EPOCH = "1767225600"  # 2026-01-01

# Body text at 11 points on A4, one-inch margins, as article-class lecture
# notes are; each page is headed by the lecture's title and its number.
PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage{amsmath,amssymb}
\usepackage[margin=1in]{geometry}
\interlinepenalty=10000
\pagestyle{myheadings}
\markright{%s}
\begin{document}
"""

# Characters that mean something to TeX, as prose writes them.
_TEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "—": "---",
    "–": "--",
}
_INLINE = re.compile(r"\$([^$]+)\$")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_NUMBERED = re.compile(r"^\d+\.\s")
_LABEL = re.compile(r"\\newlabel\{b(\d+)\}\{\{[^{}]*\}\{(\d+)\}")


class TypesettingError(Exception):
    """Tectonic is missing, or could not typeset a lecture."""


@dataclass(frozen=True)
class Block:
    kind: str  # title, heading, text, display, item or numbered
    markdown: str  # as written in the source


@dataclass(frozen=True)
class Lecture:
    filename: str  # as uploaded, such as 04-calculus.pdf
    title: str
    source: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Typeset:
    pdf: bytes
    pages: tuple[int, ...]  # the page each block landed on, numbered from 1

    @property
    def page_count(self) -> int:
        return max(self.pages)


def blocks(source: str) -> tuple[Block, ...]:
    """The source's blocks, in order. A list is one block per item."""
    found: list[Block] = []
    for chunk in re.split(r"\n\s*\n", source.strip()):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        first = lines[0]
        if first.startswith("# "):
            found.append(Block("title", first))
        elif first.startswith("## "):
            found.append(Block("heading", first))
        elif first.startswith("$$"):
            if not lines[-1].endswith("$$") or len("\n".join(lines)) < 5:
                raise ValueError(
                    f"A displayed formula must end its block with $$: {first[:40]}"
                )
            found.append(Block("display", "\n".join(lines)))
        elif all(line.startswith("- ") for line in lines):
            found.extend(Block("item", line) for line in lines)
        elif all(_NUMBERED.match(line) for line in lines):
            found.extend(Block("numbered", line) for line in lines)
        else:
            found.append(Block("text", " ".join(lines)))
    return tuple(found)


def lectures(directory: Path = CORPUS_DIR) -> list[Lecture]:
    """Every lecture of the corpus, in file order."""
    found = []
    for path in sorted(directory.glob("*.md")):
        source = path.read_text(encoding="utf-8")
        title = source.splitlines()[0].removeprefix("# ").strip()
        found.append(Lecture(f"{path.stem}.pdf", title, source, blocks(source)))
    return found


def _prose(text: str) -> str:
    return "".join(_TEX_SPECIAL.get(c, c) for c in text)


def _inline(text: str) -> str:
    """A line of prose as LaTeX: its maths as written, the rest escaped."""
    out, i = [], 0
    for m in _INLINE.finditer(text):
        out.append(
            _BOLD.sub(
                lambda b: r"\textbf{" + b.group(1) + "}", _prose(text[i : m.start()])
            )
        )
        out.append(f"${m.group(1)}$")
        i = m.end()
    out.append(_BOLD.sub(lambda b: r"\textbf{" + b.group(1) + "}", _prose(text[i:])))
    return "".join(out)


def to_latex(lecture: Lecture) -> str:
    """The lecture as a LaTeX document, with a label for every block."""
    out = [PREAMBLE % _prose(lecture.title)]
    previous = None
    for n, block in enumerate(lecture.blocks):
        label = rf"\label{{b{n}}}"
        text = block.markdown
        if previous in ("item", "numbered") and block.kind != previous:
            out.append(
                "\n\\end{%s}" % ("itemize" if previous == "item" else "enumerate")
            )
        if block.kind == "title":
            out.append("\n\n\\section*{" + _inline(text[2:]) + "}" + label)
        elif block.kind == "heading":
            out.append("\n\n\\subsection*{" + _inline(text[3:]) + "}" + label)
        elif block.kind == "display":
            body = text[2:-2].strip()
            # After prose the display belongs to its paragraph; otherwise it
            # starts one of its own.
            lead = "\n" if previous in ("text", "display") else "\n\n\\noindent"
            out.append(f"{lead}{label}\\[{body}\\]")
        elif block.kind in ("item", "numbered"):
            if previous != block.kind:
                out.append(
                    "\n\n\\begin{%s}"
                    % ("itemize" if block.kind == "item" else "enumerate")
                )
            body = text[2:] if block.kind == "item" else _NUMBERED.sub("", text)
            out.append(f"\n\\item {label}" + _inline(body))
        else:
            if previous == "display":
                out.append(f"\n{label}" + _inline(text))  # the paragraph goes on
            else:
                out.append(f"\n\n\\leavevmode{label}" + _inline(text))
        previous = block.kind
    if previous in ("item", "numbered"):
        out.append("\n\\end{%s}" % ("itemize" if previous == "item" else "enumerate"))
    out.append("\n\n\\end{document}\n")
    return "".join(out)


def tectonic() -> str:
    """Tectonic's path, or TypesettingError saying how to install it."""
    found = shutil.which("tectonic")
    if found is None:
        raise TypesettingError(
            "The maths benchmark typesets its lectures with Tectonic, which is "
            "not installed. Install it with: brew install tectonic"
        )
    return found


def tectonic_version() -> str:
    run = subprocess.run(
        [tectonic(), "--version"], capture_output=True, text=True, check=False
    )
    return run.stdout.strip()


def typeset(lecture: Lecture) -> Typeset:
    """The lecture as a PDF, and the page each of its blocks landed on."""
    with tempfile.TemporaryDirectory() as work:
        tex = Path(work) / "lecture.tex"
        tex.write_text(to_latex(lecture), encoding="utf-8")
        run = subprocess.run(
            [
                tectonic(),
                "-X",
                "compile",
                "--untrusted",
                "-Z",
                "deterministic-mode",
                "--keep-intermediates",
                str(tex),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH},
            check=False,
        )
        if run.returncode != 0:
            raise TypesettingError(
                f"{lecture.filename} did not typeset:\n{run.stderr[-2000:]}"
            )
        aux = (Path(work) / "lecture.aux").read_text(encoding="utf-8")
        pdf = (Path(work) / "lecture.pdf").read_bytes()
    landed = {int(m.group(1)): int(m.group(2)) for m in _LABEL.finditer(aux)}
    missing = [n for n in range(len(lecture.blocks)) if n not in landed]
    if missing:
        raise TypesettingError(f"{lecture.filename}: blocks {missing} have no page.")
    return Typeset(pdf, tuple(landed[n] for n in range(len(lecture.blocks))))


def page_truth(lecture: Lecture, typeset_: Typeset, page_number: int) -> str:
    """What the page says, in the form the model is asked to write it."""
    parts: list[str] = []
    previous = None
    for block, page in zip(lecture.blocks, typeset_.pages, strict=True):
        if page != page_number:
            continue
        same_list = block.kind in ("item", "numbered") and previous == block.kind
        if parts:
            parts.append("\n" if same_list else "\n\n")
        parts.append(block.markdown)
        previous = block.kind
    return "".join(parts)

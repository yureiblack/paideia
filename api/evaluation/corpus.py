"""The benchmark's documents, from their source text to PDFs.

Purpose
-------
The corpus is written as plain text in docs/evaluation/corpus/, one file per
lecture, so it can be read and reviewed on GitHub and no binary files live in
the repository. The benchmark turns each into a PDF the way a word processor
would, with real headings and paragraphs flowing across A4 pages, and then
reads it with the app's own parser, as if it had been uploaded.

The source format is a small subset of Markdown: "# " for the title, "## "
for a section heading, "- " for a list item, and blank lines between
paragraphs. Nothing else is recognised, which keeps the conversion exact.
"""

import html
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "docs" / "evaluation" / "corpus"

# Body text at 11 points and headings well above the parser's 1.15 ratio, so
# every heading is recognised as one (app/parsing.py).
CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 20pt; font-weight: bold; margin: 0 0 12pt 0; }
h2 { font-size: 14pt; font-weight: bold; margin: 14pt 0 6pt 0; }
p { margin: 0 0 8pt 0; }
ul { margin: 0 0 8pt 0; }
li { margin: 0 0 3pt 0; }
"""
PAGE = pymupdf.paper_rect("a4")
MARGIN = 72  # one inch on every side


@dataclass(frozen=True)
class SourceDocument:
    filename: str  # as uploaded, such as 03-synchronization.pdf
    title: str
    text: str  # the source, as written


def documents(directory: Path = CORPUS_DIR) -> list[SourceDocument]:
    """Every document of the corpus, in file order."""
    found = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix("# ").strip()
        found.append(SourceDocument(f"{path.stem}.pdf", title, text))
    return found


def to_html(text: str) -> str:
    """The source as HTML: headings, paragraphs and lists, every word
    escaped."""
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines[0].startswith("# "):
            parts.append(f"<h1>{html.escape(lines[0][2:])}</h1>")
        elif lines[0].startswith("## "):
            parts.append(f"<h2>{html.escape(lines[0][3:])}</h2>")
        elif all(line.startswith("- ") for line in lines):
            items = "".join(f"<li>{html.escape(line[2:])}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
        else:
            parts.append(f"<p>{html.escape(' '.join(lines))}</p>")
    return "<body>" + "\n".join(parts) + "</body>"


def to_pdf(text: str) -> bytes:
    """The source laid out on as many A4 pages as it needs."""
    story = pymupdf.Story(html=to_html(text), user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    area = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


def plain(text: str) -> str:
    """Text with its whitespace collapsed, for finding a quote in a passage
    whatever line breaks the PDF put in it."""
    return " ".join(text.split())

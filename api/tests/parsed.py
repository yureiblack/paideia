"""Hand-built parsed documents, for tests that need exact control of the text.

document() takes pages of (text, is_heading) paragraphs and lays them out the
way the parser does: paragraphs joined by a blank line, each block knowing
where its text sits.
"""

from app.parsing import PARAGRAPH_BREAK, ParsedBlock, ParsedDocument, ParsedPage


def H(text: str) -> tuple[str, bool]:
    """A heading."""
    return (text, True)


def P(text: str) -> tuple[str, bool]:
    """A paragraph."""
    return (text, False)


def words(n: int, word: str = "word") -> str:
    """A sentence of roughly n characters."""
    return (f"{word} " * (n // (len(word) + 1))).strip() + "."


def document(*pages: list[tuple[str, bool]]) -> ParsedDocument:
    built = []
    for number, paragraphs in enumerate(pages, start=1):
        text, blocks = "", []
        for paragraph, is_heading in paragraphs:
            if text:
                text += PARAGRAPH_BREAK
            blocks.append(
                ParsedBlock(len(text), len(text) + len(paragraph), is_heading)
            )
            text += paragraph
        built.append(ParsedPage(number=number, text=text, blocks=tuple(blocks)))
    return ParsedDocument(pages=built, repaired=False)


class Returns:
    """A Parser that returns a prepared result, whatever the file."""

    def __init__(self, parsed: ParsedDocument):
        self.parsed = parsed

    def parse(self, path):
        return self.parsed

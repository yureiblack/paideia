# 07. Citations and the evidence model

Date: 2026-11-08
Status: accepted

## Context

Later phases generate summaries, concept maps, roadmaps and practice
questions, and every one of them must be traceable to the material it came
from. The roadmap asks for provenance to become a first-class object before
any of that exists: every future artifact must be able to point back to its
environment, document, document version, page and chunk, through reusable
citation objects. Search results should show document, page and excerpt, and
a source preview should show a passage in its place. Clicking a search result
should reveal something like "Lecture 4.pdf · Page 17" and the passage.

Two facts from earlier phases shape the design. A document's file never
changes: its SHA-256 is stored, and the same file cannot be uploaded twice to
one environment. And a chunk stores exactly where it starts and ends in the
stored page text (record 04), so its passage can always be found again.
Before deciding, that was checked on a real six-page PDF through the real
parser and chunker: chunks ran across as many as four short pages, one page
held the end of one chunk and the start of the next, and every chunk was
rebuilt exactly from its stored positions.

## Decisions

### One Citation, built in one place

A citation names the environment, the document, the document's version, its
filename, the chunk, the pages, the heading and the passage itself. It is one
schema, `Citation`, and one module, `services/sources.py`, builds it. Search
results carry it now; summaries will carry the same object, so every part of
the app cites the same way.

### A document's version is its file's SHA-256

The file behind a document never changes. Its extracted text can, when the
document is reprocessed with a newer parser, but then every chunk whose text
changed gets a new id, because a chunk's id is derived from its text (record
04). The document version and the chunk id together therefore pin one exact
passage, without any new table or column.

Linking an old file and its replacement, a corrected version of the same
lecture, belongs to the phases that replace documents (10 and 17), which can
add that link when there is something to link.

Alternative considered: a `document_versions` table now. Nothing creates
versions yet, so its design would be guesswork.

### Search results are a citation and a score

`results` used to be flat: chunk id, document id, filename, pages, heading,
text and score. Each result is now `{citation, score}`, the citation being the
same object a preview and, later, a summary return. Only the app's own
frontend read the old shape.

### The title is the filename, the excerpt is the chunk

The roadmap's own example, "Lecture 4.pdf", is a filename. A PDF's metadata
title is often missing or meaningless ("Microsoft Word - lec4.docx").

The excerpt is the chunk's text, at most 1200 characters: the passage the
reranker judged. Picking a single "best sentence" at search time would cost
more model work and rest on a weaker judgement than the reranker's.

### The source preview

`GET /api/chunks/{chunk_id}/preview` returns the citation and every page the
passage touches, each with its text and the range the passage covers. A
passage can start part-way through one page and end part-way through a later
one, so the first page is highlighted from the chunk's start, the last up to
its end, and any page in between entirely. A page with no text is left out,
as it is when the chunk's text is assembled. Joined with the blank line that
separates pages, the highlighted parts are exactly the excerpt, which the
tests check for every chunk of generated multi-page documents.

A passage that no longer exists, because its document was deleted or
reprocessed into different text since the search, is a 404 with that reason.

### "Show in page" in the Search tab

Each result has a "Show in page" button that opens the citation inline:
"Lecture 4.pdf · Page 3", then each page with the passage marked, the panel
scrolled to where the passage starts. It works like the Materials tab's "Read
text", and keeps the reader on their results.

Alternatives considered: a dialog, which must manage focus and the keyboard
carefully, and a separate page, which leaves the results behind.

### No evidence table yet

Nothing generates content yet, so nothing would write to a table of
citations. Phase 09 introduces generated artifacts and stores their citations
in this same shape.

## Testing

- A citation from a processed document names its environment, document,
  filename, pages, heading and excerpt, and its version is the SHA-256 of the
  exact uploaded bytes.
- Citing several chunks keeps their order, across documents, with one query
  for the documents.
- For every chunk of five generated multi-page documents, each with an empty
  page in the middle: the preview lists exactly the pages with text in the
  chunk's range, highlights the first from the chunk's start, the last to its
  end and every middle page whole, and the highlighted parts rebuild the
  excerpt exactly.
- A passage that starts part-way down a page shares that page with the
  passage before it, and each highlights only its own part.
- Through the API: a search result's citation opens to its page, and the
  preview cites it with an identical object; a deleted document's passage is
  a 404 with the reason; a malformed id is a 422.
- Seven deliberate breaks of the citation code are each caught by a test. Two
  were caught only after the tests gained an interleaved order and a passage
  starting mid-page.
- In the browser: one-page and multi-page passages highlighted exactly,
  scrolled into view, a deleted passage explained, and phone width in dark
  mode.

## Consequences

- Anything generated from now on can store citations in this shape and
  check, through the chunk id, whether the passage it cites still exists.
- Search results changed shape; the API's own frontend is the only client.
- A citation's excerpt can be up to 1200 characters. Summaries that quote
  many sources may want a shorter display, which they can derive from the
  excerpt.

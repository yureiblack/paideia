# 04. Chunking and the content index

Date: 2026-11-02
Status: accepted

## Context

Search, citations and later the language model all work on passages, not whole
documents. Phase 04 cuts every document into chunks without any model involved,
so the source representation is deterministic, reproducible and easy to debug.
The roadmap's acceptance test is strict: process the same PDF twice and get the
same chunk identities, with no duplicates.

A prototype on the text stored by Phase 03 showed that paragraph boundaries were
already lost: headings, new paragraphs and line wraps were all a single line
break. The parser had to change first.

## Decisions

### Paragraphs and headings come from PyMuPDF's detailed text mode

PyMuPDF's `dict` mode reports each block of text with its lines, font sizes and
styles. Each block becomes a paragraph, its wrapped lines joined into one. A
block is a heading when it is short and either clearly larger than the body
text or bold at body size. Body size is the font size used by the most
characters in the document. The prototype showed this recovers headings and
paragraphs, including two-column pages in the right order, so PyMuPDF 2.x and
its machine-learning layout engine are still not needed.

Each page's text is now stored as paragraphs separated by a blank line, and the
parser reports where each paragraph sits and whether it is a heading.

### The text is cleaned for search

- Ligatures such as the single character "ﬁ" are expanded to "fi". Without
  this, a search for "files" would never match text that used one.
- Words broken across lines are rejoined by the parser. PyMuPDF's own
  dehyphenation option had no effect in any of five extraction modes. A line
  ending in a hyphen followed by a lowercase word is joined without the hyphen
  if the joined word appears elsewhere in the document, so "pro-" and "cess"
  become "process"; otherwise the hyphen is kept, so "well-defined" survives.
  The rule never invents a word.
- Running headers, footers and page numbers are dropped. A block counts as one
  when it is short, sits in the outer 7% of the page at top or bottom, and
  repeats, with digits treated alike, in that margin on at least half the pages
  of a document of three pages or more. Body text matching a header is kept. A
  band of an eighth of the page was tried first and removed real first lines,
  since body text conventionally starts an inch from the edge.

### Chunks follow paragraphs and headings

Whole paragraphs are packed into a chunk until it reaches about 800 characters,
and a chunk never exceeds 1200. Every heading starts a new chunk and opens it;
consecutive headings stay with the paragraph after them. A longer paragraph is
split at sentence ends, and a single over-long sentence at a space. Chunks do
not overlap. 1200 characters is roughly 250 to 300 tokens, within the input
limit of common local embedding models; the limits are constants that can be
tuned when the embedding model is chosen.

Each chunk records the nearest heading above it, which is used for ranking now
and will give context to results later.

### Chunk identity is derived from content

A chunk's id is a version-5 UUID of its document id, a SHA-256 hash of its
whitespace-normalised text, and which occurrence of that text it is within the
document. The same text in the same document always gets the same id, so
identity survives reprocessing by construction, and a paragraph that repeats on
several pages still gets distinct ids.

When a document is processed again, its stored chunks are synced rather than
replaced: unchanged chunks keep their rows, moved chunks have their position
updated, vanished chunks are deleted and new ones inserted. Embeddings will be
stored on these rows, so reprocessing an unchanged document will not trigger
re-embedding, and editing one section re-embeds only that section's chunks.

Alternatives considered:

- Random ids, deleting and reinserting every chunk: fails the acceptance test.
- Ids from a chunk's position: one paragraph inserted near the start would
  renumber every chunk after it.

### Every chunk knows exactly where it came from

A chunk stores its start as (page, character offset) and its end the same way,
into the stored page text. Its text can always be rebuilt from those offsets, a
property the tests check on generated documents with headings, page breaks and
empty pages. Citations will use this to highlight the exact passage.

### Full-text search runs inside Postgres

Each chunk has a generated `tsvector` column that Postgres computes from the
heading and the text. The English dictionary reduces words to stems, so
"processes" matches "process", and the heading is weighted above the body so a
match in a heading ranks higher. A GIN index serves the queries. Queries are
parsed with `websearch_to_tsquery`, which accepts quoted phrases, `OR` and
`-excluded` words, and results are ranked with `ts_rank_cd` and always limited
to one environment.

Computing the vector in Postgres rather than in application code means it can
never drift from the text it describes.

### No search endpoint yet

The search service exists and is tested, but no endpoint or search box is added
in this phase. Semantic search defines the search API next, and hybrid search
combines it with this keyword search after that, so the endpoint and its
interface are built once. A read-only endpoint lists a document's chunks, for
inspecting chunking quality.

## Consequences

- Documents processed before this phase need a reprocess to gain paragraph
  breaks and chunks.
- Parsing a page now costs about twice as long as plain text extraction, still
  under three seconds for 300 pages, which background processing absorbs.
- Changing the chunk size limits changes chunk identities, and would trigger
  re-embedding once embeddings exist.

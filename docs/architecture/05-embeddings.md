# 05. Local embeddings and vector search

Date: 2026-11-07
Status: accepted

## Context

Keyword search (record 04) finds only the words typed. Phase 05 adds search by
meaning. Every chunk gets an embedding: a list of 384 numbers from a language
model, placed so that passages about the same thing sit close together. A query
is embedded the same way, and the nearest chunks are the results. The roadmap's
acceptance test: answer "Find material related to process scheduling" without
an exact keyword match. No external embedding service is used; the model runs
on the same machine as the API.

## Decisions

### fastembed instead of Sentence Transformers

The roadmap's stack table names Sentence Transformers, for "open, local
embedding models; no API cost". Sentence Transformers runs on PyTorch, whose
package is 132 MB on the development Mac and 514 MB on Linux, where it also
pulls in about 1 GB of NVIDIA GPU libraries that CI would never use. A CPU-only PyTorch
exists, but it is served from a separate package index, which would split the
single pinned requirements file by platform.

fastembed runs the same open models through ONNX Runtime: about 183 MB
installed in total, the same packages on Mac and Linux. The roadmap's reason
holds unchanged. The application talks to an `Embedder` interface (a model
name, a dimension count, one method for passages and one for queries), so a
Sentence Transformers version would be one more class. fastembed also ships the
cross-encoder rerankers Phase 06 needs.

Alternatives considered:

- Sentence Transformers with PyTorch: the install size, and GPU libraries on CI.
- CPU-only PyTorch: a second package index and platform-specific pins.

### The model is BAAI/bge-small-en-v1.5

MIT licence, 384 dimensions, and a 512-token input window, so a full
1200-character chunk is never cut short; all-MiniLM-L6-v2's 256 tokens could
cut off its end. On first use fastembed downloads an ONNX conversion of the
model, published by Qdrant as `Qdrant/bge-small-en-v1.5-onnx-Q`, about 64 MB,
and keeps it in `MODEL_DIR` (`data/models/` by default) for every later run.

In the planning prototype, the acceptance query's top result was a round-robin
passage that shares no word with "process scheduling". BGE's optional
instruction prefix for queries did not improve the ranking, so queries are
embedded plainly. bge-base-en-v1.5 was three times slower, 210 MB, and no
better on the same test.

Measured on the development Mac: 256 chunks of about 1000 characters embed in
about 10 seconds, roughly 40 ms each, and a query in about 3 ms. Embedding runs
in the background, so a long document takes longer to become ready but nothing
waits on it.

The database column is `vector(384)`. `EMBEDDING_DIMENSIONS` is checked against
the model when it loads, so a model of another size fails at once with a clear
message rather than at the first insert. Switching to one needs a migration.

### Embeddings live on the chunk rows

Two columns on `document_chunks`: `embedding vector(384)` and
`embedding_model`, both empty until computed. Record 04's sync keeps unchanged
chunk rows when a document is processed again, so their embeddings survive and
only new or changed chunks are embedded. A chunk whose `embedding_model`
differs from the configured model counts as missing: changing the model
re-embeds each document on its next reprocess, and a search never mixes
vectors from two models, which would not be comparable.

Alternative considered: a separate embeddings table, which costs a join on
every search for flexibility nothing needs yet.

### Embedding happens during processing

The background job embeds the chunks that need it after chunking and before
its final write, in batches of 64, outside the row lock like parsing (record
03). A document is ready only when it can be found both by keywords and by
meaning.

If embedding fails, most likely because the first download had no internet
connection, the document is marked failed with that reason, and Try again
retries it. Marking it ready with embeddings silently missing was rejected:
search would skip it without anyone knowing why.

Chunks without an embedding, for example from documents processed before this
phase, are left out of semantic search until the document is reprocessed.

### An HNSW index with iterative scans

pgvector's HNSW index serves the search, with cosine distance, the measure the
BGE models are trained for. The migration also enables the `vector` extension,
which record 01 left to a migration.

The index is approximate, and it filters afterwards: it gathers a fixed number
of nearest candidates, `hnsw.ef_search`, 40 by default, and only then does
Postgres apply the environment filter. When another environment holds most of
the chunks, few or none of those candidates survive, and a search in a small
environment comes back short or empty. pgvector 0.8's iterative index scan
keeps searching until enough rows pass the filter. Every search turns it on
with `strict_order`, so results stay exactly in order of distance.

Every search also raises `hnsw.ef_search` to 100. `top_k` goes up to 50, above
the default of 40, and a wider search finds the true nearest chunks more
reliably at a small cost at this size. Both settings use `SET LOCAL` and last
only for the search's own transaction.

The query orders by distance alone, with no tie-breaker, because the index can
only serve an `ORDER BY` on the distance itself; a second sort key would turn
every search into a full scan.

### One search endpoint

`POST /api/search` takes `{environment_id, query, top_k}` as the roadmap
specifies, with `top_k` from 1 to 50, default 10. Each result carries the
roadmap's fields (`chunk_id`, `document_id`, `page_start`, `page_end`, `text`,
`score`) plus `filename` and `heading`, which any display of a result needs.
`score` is cosine similarity, higher meaning closer. It ranks results; it is
not a percentage or a probability. An unknown environment is a 404; a model
that cannot be loaded is a 503 with the reason. Phase 06 changes what sits
behind this endpoint, not its shape.

Keyword search moved next to semantic search in `services/search.py`, so
Phase 06 can combine the two in one place.

### A Search tab in every environment

A query box and a list of results, each showing its document, pages, heading,
text and score. The roadmap lists no interface for this phase, but the endpoint
exists now and Phase 06 keeps its shape, so the tab is built once. A search
runs when the form is submitted, not on every keystroke, and each query's
results are cached, so returning to an earlier query is instant.

## Testing

- Most tests use a stand-in embedder that hashes each word into one of 384
  positions: instant, offline and deterministic, and texts that share words
  land close together.
- Real-model tests check the vectors' size and length, the dimension check,
  and the acceptance query. That test embeds chunk-length passages on five
  operating-system topics, none containing "process" or "schedul", and expects
  the scheduling passage first, for the roadmap's wording and two others. A
  second test asks the roadmap's wording through the API, uploaded documents
  and all. With one-sentence passages the wrong passage won by 0.002; with
  chunk-length passages the scheduling one leads by 0.04 to 0.07.
- The environment filter is tested under the conditions where an index on its
  own fails, and building that test taught three things about HNSW:
  - With only a few hundred rows, Postgres skips the vector index for an exact
    path, so a plain test passes even with iterative scans off. The test forces
    the plan a large table gets, inside its rolled-back transaction.
  - HNSW stores identical vectors as one node in its graph, so 300 copies of
    one vector crowd out nothing. The crowd must be distinct.
  - The stand-in embedder's vectors made the test fail in about half of all
    runs. Hundreds of exact ties and hash collisions left the three chunks
    being searched for as outliers next to a tight cluster, and HNSW, which
    builds its layers at random, sometimes left an outlier with no links
    leading to it. The test now places its vectors by hand on a quarter circle
    around the query, 300 chunks of another environment at 1 to 60 degrees and
    this environment's three at 65, 70 and 75. It passed 30 full runs in a row,
    and fails every time with iterative scans turned off.
- CI caches the model between runs, keyed on `app/config.py`, which names it.

## Consequences

- Documents processed before this phase need a reprocess to be found by
  meaning.
- The first processed document downloads the model. Without an internet
  connection at that moment it fails with that reason, and Try again works
  once the connection is back.
- A model with another dimension count needs a migration and a reprocess of
  every document.
- A small embedding model puts related passages close together but does not
  always order them well: in the prototype a deadlock passage outranked a
  scheduling one for a scheduling query, and "how a journal repairs the disk
  after a crash" ranks a paging passage above a file-system one. Phase 06 adds
  keyword matching and a reranker for precision.
- The index is approximate by design. At this project's size, iterative scans
  and the wider search keep misses rare, and Phase 06's keyword half catches
  passages that share the query's words.

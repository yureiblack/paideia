# 06. Hybrid retrieval and reranking

Date: 2026-11-07
Status: accepted

## Context

Keyword search (record 04) finds exact terms and misses paraphrases. Semantic
search (record 05) finds paraphrases and can miss a rare term, a name or a
number. Phase 06 combines them into one pipeline, as the roadmap lays out:
keyword search and vector search, merged with Reciprocal Rank Fusion, then
reranked by a cross-encoder, with the four sizes involved configurable, every
stage's score visible in a debug mode, and retrieval evaluation fixtures and
tests. No answers are generated yet.

Every choice below was measured first, on a fixture written for the purpose
and now committed with the tests (`tests/retrieval_fixture.py`): 28 original
passages on operating systems and 32 questions labelled with the passages that
answer them. The passages include deliberate near-misses: disk scheduling
beside CPU scheduling, journaling beside write-ahead logging and
log-structured file systems, mutexes beside spinlocks and monitors, and a
passage on process creation full of the word "process". The questions come in
three kinds: 14 name something exactly ("TLB", "Belady's anomaly", "zombie"),
12 describe it in other words, and 6 put a rare term inside an everyday
question ("what is a zombie process and why does it stick around").

The main score is mean reciprocal rank over the top five results (MRR): 1
when the right passage is always first, 0.5 when it is always second, 0 when
it is missing.

## Decisions

### Keyword search lets any word match

Keyword search required every word of the query to appear, which is what
`websearch_to_tsquery` does. That finds nothing for 16 of the 32 questions:
every paraphrase and every mixed question, because a question always contains
some word the passage does not. In a hybrid search, a keyword half that stays
silent for most real questions adds little.

Now any of the query's words may match, and chunks are ranked with Postgres's
`ts_rank`, by how many of the words they contain, how often, and whether in a
heading. On the fixture this ranks 0.885 on its own, against 0.835 for
`ts_rank_cd`, the cover-density rank used before, which suits queries whose
words must all appear together. A query written with search syntax, a "quoted
phrase", `OR` or a `-word`, is still read exactly as in Phase 04.

Alternatives considered:

- Every word must match: silent for half the questions.
- Any word, ranked with `ts_rank_cd`: measurably noisier.

### Reciprocal Rank Fusion merges the two lists

Each search contributes its best 30 chunks. A chunk earns 1 / (60 + rank) from
each list it appears in, and the sums decide the merged order. Only positions
count, so a keyword rank and a cosine similarity, which are on unrelated
scales, never need to be made comparable. 60 is the constant from the paper
that introduced the method (Cormack, Clarke and Büttcher, 2009) and the usual
choice since. Ties are broken by chunk id, so the order is always the same.

A chunk found by only one search still counts. One consequence: a chunk
without an embedding, from a document processed before Phase 05, is now found
by its words.

### A cross-encoder reranks the best 30

The keyword and semantic searches never read the query and a passage together:
one compares words, the other vectors computed in advance. A cross-encoder
reads the query and one passage as a single input and judges how well the
passage answers it. That is far more precise and far too slow to run on every
chunk, so it reads only the best 30 of the merged list, or as many as the
request asks for if that is more, and the final order is its order.

The model is `Xenova/ms-marco-MiniLM-L-6-v2`, run through fastembed like the
embedding model. It is an ONNX conversion of
`cross-encoder/ms-marco-MiniLM-L-6-v2`, the standard Sentence Transformers
CrossEncoder, so this is the roadmap's choice through the library record 05
already chose. Apache-2.0, 87 MB, downloaded on the first search.

Measured on the fixture, reranking the merged list:

| Reranker | MRR | Time for 28 passages | Size |
|---|---|---|---|
| ms-marco-MiniLM-L-6-v2 | 0.969 | 0.28 s | 87 MB |
| ms-marco-MiniLM-L-12-v2 | 0.962 | 0.56 s | 120 MB |
| jina-reranker-v1-turbo-en | 0.936 | 0.36 s | 150 MB |
| bge-reranker-base | 0.981 | 2.3 s | 1 GB |

bge-reranker-base is better by one question in 32, for twelve times the size
and eight times the time. jina-reranker-v2 was not considered: its licence
forbids commercial use. On the development Mac, MiniLM-L-6 reranks 30
chunk-length passages in about 0.6 s and 50 in about 0.9 s.

The model's raw output has no fixed range, about -11 to +9 on the fixture,
and only its order matters.
A sigmoid turns it into 0 to 1, in the same order, and that is the `score` a
result carries. It is easier to read, but it is not a probability. Each chunk
is given to the reranker with its section heading in front, unless its text
already starts with it, so a passage from the middle of a section keeps its
context.

### Every stage is configurable and visible

Four settings: `RETRIEVAL_TOP_K_LEXICAL` and `RETRIEVAL_TOP_K_DENSE` (30
each), `RETRIEVAL_CANDIDATE_POOL` (30), and `RETRIEVAL_FINAL_K` (10, the
default for a request's `top_k`, which stays between 1 and 50).
`RERANK_MODEL` names the reranker.

`POST /api/search` keeps its shape. With `debug: true` the response also
carries the sizes used and every candidate in merged order, each with its
keyword rank and score, semantic rank and score, fusion score, rerank score
and final place, any of them empty when that stage never saw the chunk. The
Search tab's "Show scoring" switch turns this on and shows each result's four
scores and a table of every candidate.

`score` now means the reranker's judgement where it meant cosine similarity
before; the field and its 0-to-1 range are unchanged.

### A reranker that cannot load is a 503

As with the embedding model, the reason is shown, most likely a first
download without an internet connection. Quietly returning the merged order
was rejected: results would get worse with no one knowing why. A search that
finds no candidates never loads the reranker at all.

### Semantic search widens its search with the request

`hnsw.ef_search` was fixed at 100 because the largest request was 50. The
semantic half's size is now a setting, so the search keeps twice the number
asked for in view, at least 100 and at most pgvector's limit of 1000.

## Evaluation

`python -m tests.retrieval_eval` prints this table; `test_retrieval_quality.py`
asserts on it. The fixture has only 28 passages, so the evaluation uses
smaller sizes (10 from each search, a pool of 5) to keep the reranker reading
only a small share of them, as it does in a real environment.

| Method | MRR | Right passage first | Term | Meaning | Mixed | Answer reached the reranker |
|---|---|---|---|---|---|---|
| Keyword search alone | 0.885 | 84% | 1.000 | 0.694 | 1.000 | |
| Semantic search alone | 0.872 | 81% | 0.893 | 0.840 | 0.889 | |
| Both, fused | 0.928 | 88% | 1.000 | 0.808 | 1.000 | |
| Keyword search, reranked | 0.953 | 94% | 1.000 | 0.875 | 1.000 | 97% |
| Semantic search, reranked | 0.938 | 91% | 0.929 | 0.917 | 1.000 | 97% |
| **Both, fused, reranked (the app)** | **0.969** | **94%** | **1.000** | **0.917** | **1.000** | **100%** |

The two searches fail on different questions, which is why fusion beats
either alone, and why only the fused list got every question's answer in front
of the reranker. The reranker then does most of the ordering.

The test requires the full pipeline to reach 0.95, to reach the reranker with
every answer, and to beat every other row; and the stages before the reranker
to stay above floors just under their measured scores, so a weaker stage
cannot hide behind the reranker. Ranking keyword matches with `ts_rank_cd`, for
instance, leaves the final score unchanged but drops keyword search alone to
0.835 and fusion to 0.876, and fails the test.

Two questions still put the right passage second. "Find material related to
process scheduling" ranks disk scheduling first: both are scheduling, and the
reranker, trained on questions, scores every passage low for a request phrased
as a command, so even the right one shows a score near 0. "The computer slows
to a crawl because memory is overcommitted" ranks CPU caches above thrashing.

In the browser, "how a journal repairs the disk after a crash", which semantic
search alone answered with a paging passage in Phase 05, now finds the file
system passage first, at 0.99.

## Testing

- Reciprocal Rank Fusion's arithmetic, tie-breaking and constant, on plain
  ids.
- The pipeline with stand-ins for both models: each stage's size, the pool
  growing to `top_k`, the reranker deciding the order, every stage's scores,
  chunks without embeddings found by their words, environment isolation, no
  model needed for a blank query or an empty environment, and headings given
  to the reranker.
- Keyword search: any word of a question can match, more matched words rank
  higher, and search syntax still works.
- The API: the debug block, its agreement with the results, the 503 for each
  model, and the roadmap's Phase 05 acceptance query through both real models.
- The retrieval evaluation above, with the real models.
- Twelve deliberate breaks of the new code, each caught by a test: from
  requiring every word, or ignoring search syntax, to dropping the heading
  given to the reranker or returning the merged order unreranked.

## Consequences

- A search now runs two queries and the reranker, about 0.6 s on the
  development Mac at the default sizes, most of it the reranker.
- The first search downloads the reranker, so it is slow once and needs an
  internet connection.
- The small reranker does not expand abbreviations it has not seen: a passage
  about the "translation lookaside buffer" scores near 0 for "what is a TLB"
  unless it also says "TLB". Keyword search catches the abbreviation when the
  passage uses it.
- `score` is a 0-to-1 judgement from the reranker, not a similarity; clients
  that compared scores across searches should not.
- The fixture is small and written by one person. It is a regression test and
  a sanity check, not a benchmark; Phase 20 evaluates retrieval more broadly.

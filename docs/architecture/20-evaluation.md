# 20. Evaluation and benchmarking

Date: 2026-11-15
Status: accepted

## Context

Every claim so far about how well Paideia finds and cites passages rested on
a few checks in the browser and on the small fixture of record 06: 32
questions over 28 short passages, scored by MRR alone, inside a test.

The roadmap asks for more, with nothing fabricated or typed in by hand:

- an offline dataset for one sample environment, with 50 to 100 questions
  whose evidence has been verified;
- Recall@5, Recall@10, MRR, citation correctness, answer groundedness,
  answer completeness and latency;
- a comparison of semantic, lexical, hybrid, and hybrid with reranking;
- results under `docs/evaluation/`, and a script that reproduces them.

The results are in
[`docs/evaluation/retrieval-benchmark.md`](../evaluation/retrieval-benchmark.md).
This record explains how they are produced. It quotes none of them, so it
can never disagree with them.

## Decisions

### A corpus written for the benchmark, read by the real pipeline

Ten lecture notes on operating systems (`docs/evaluation/corpus/`), about
10,600 words, written so they can be published with the benchmark. A
published textbook could not be committed, and Wikipedia's share-alike
licence would bind the repository. The notes deliberately contain
near-misses, such as CPU scheduling beside disk scheduling, journaling beside
log-structured file systems, and starvation in three settings.

They are committed as text, in a small subset of Markdown, and turned into
PDFs at run time with PyMuPDF's Story layout, which flows them over A4 pages
with real headings and paragraphs. The app then reads each PDF as it reads
any upload: parser, chunker and embedding model. The result is 29 pages and
92 passages.

### Questions labelled by quoting their evidence

There are 80 questions in four kinds:

- 25 name the term;
- 30 describe it in other words, each listing words it must avoid;
- 10 put a rare term in an everyday question;
- 15 need two passages.

Each question quotes its evidence rather than naming chunk ids. At run time
each quote is found in whichever passage the chunker put it in, so the labels
survive a change to the chunker. A part of an answer can also name
alternative quotes, when another passage answers that part just as well.

Before anything is measured, every label is checked:

- a quote appears exactly once in the corpus, and inside exactly one passage
  of the document it names;
- a question needing two passages names two different passages;
- a term question contains its term, as does its evidence;
- a question in other words avoids its listed words.

The same checks run in CI.

### Checked in a second pass, not by an independent person

The plan was for the project's owner to review every label before anything
was published. At the owner's request, the labels were instead rechecked in
a second pass, separate from writing them. An independent read of the
review sheet was made blind, without the judge's verdicts or the reasoning
behind the labels, and every point it raised was then checked against the
text before anything changed. As a result:

- one passage was added as an alternative answer;
- two questions were reworded to ask exactly what their evidence answers;
- nineteen key facts were tightened;
- one of the reviewer's claims was rejected: the file systems document does
  cover free space.

The report and `questions.json` say this was not an independent human
review, and the report counts it among the limits of the results.

### Four methods, at the app's own settings

- **Semantic:** vector search alone.
- **Lexical:** keyword search alone.
- **Hybrid:** both searches, fused by Reciprocal Rank Fusion.
- **Hybrid + reranker:** the app's search as it runs.

Each returns 10 passages. Hybrid and the app's search consider 30 from each
search and rerank 30, the app's settings, so the figures describe the app as
it is, not a configuration tuned to the benchmark.

The scores:

- **Recall@k:** the share of a question's parts answered in the first k.
- **MRR@10.**
- **How often the first result is evidence.**
- **Latency:** each question is asked three times per method after a
  warm-up; the median of the three is that question's time.

### Three fresh builds per run

Two runs first gave different scores for hybrid. Passage ids derive from the
document's id, which is new for every upload, and both keyword search and
fusion break ties between passages by id. A tie can therefore fall either way
in a fresh build, in the app as in the benchmark.

Fixing the documents' ids would have hidden that, so instead every run reads
the corpus into a fresh database three times. The report gives the mean, with
the lowest and highest build beside the main score; each question records its
reciprocal rank in every build.

### Generation, judged on what the app writes

The app does not answer questions, and its roadmap says chat is not its
point, so a question-answering feature was not built for the benchmark.
Generation is judged on what the app does write: the ten documents'
summaries, written by the local model exactly as the app writes them.

- **Citation correctness:** the share of citations whose passage supports
  the point citing it.
- **Groundedness:** the share of points with at least one supporting
  citation.
- **Completeness:** each document has five key facts
  (`docs/evaluation/key-facts.json`), and a summary covers one when a word of
  it begins with a word from each of the fact's word groups.

The judge of support is the app's reranker at 0.5, the check practice items
already pass (record 14). Having the local model grade its own work was
rejected.

A reranker judges relevance, not truth. So 30 pairs were set aside, weighted
towards those it rejected, and decided again by the strict rule that a
passage must state everything the point claims. The report gives the judge's
agreement and a corrected citation figure: within each of the judge's two
verdicts, the share the review called supported, weighted by how many of all
citations got that verdict.

### No number typed by hand

`scripts/evaluate_retrieval.py` runs everything. It writes every number,
question by question, with the run's date, commit, machine and models, to
`docs/evaluation/results.json`. It then rewrites only the tables and the
findings between markers in the report; the prose around them names no
figures.

Results are always written before they are committed, so each run also
records a fingerprint of its inputs: the corpus, labels, app and benchmark
code, and pinned dependencies. Retrieval runs keep the last summaries, and
rescore them against the current key facts and review.

## What it found

The figures are in the report; these are the patterns behind them.

- **Retrieval:** keyword and semantic search fail on different questions, so
  fusion helps. The reranker gives the largest gain in ordering, and it costs
  the most time by far. Semantic search alone is weakest on questions in
  other words: they avoid the term but keep everyday words, and the small
  embedding model places near-identical topics close together.
- **Generation:** the summaries cover their documents' key facts well, but
  they are weaker on attribution. Many rejected citations point to a
  neighbouring passage rather than the one that says it, and the judge is
  lenient: it accepted citations the review rejected, never the reverse.
- **The chunker:** it splits a paragraph that crosses a page break into two
  passages. One passage of the corpus is just the end of a sentence, and a
  summary cited it. That is a weakness of the app, not of the benchmark.
  Fixing it changes passage ids, so it is left for a change of its own, to be
  judged by this benchmark's numbers before and after.

## Testing

- **Dataset and metrics:** `api/tests/test_evaluation.py` (9 tests, in CI)
  checks that every label resolves to the passages the app cuts, with the
  right count of each kind. It also checks that broken labels are reported,
  that every key fact can be found in its document, and that each metric is
  computed as defined on rankings made by hand, including alternative
  passages and word-start matching.
- **Deliberate breaks.** Thirteen deliberate breaks of the metrics and the
  checks were all caught. One was first missed: no test had two quotes in
  the same passage for a question needing two. That test was added.
- **The benchmark itself** runs locally, since it needs the models; its
  results are the report.

## Consequences

- Retrieval or chunking changes can now be judged by numbers: rerun the
  script before and after.
- A run takes about twenty minutes, and about five more with the summaries. Each run rebuilds the `_eval` database and leaves it in place.
- The corpus is small, so the reranker reads a third of it on every search.
  Recall would be lower among thousands of passages.
- The labels and the judge's sample have not been checked by an independent
  person.

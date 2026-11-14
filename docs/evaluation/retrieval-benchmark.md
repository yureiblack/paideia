# Retrieval and generation benchmark

This measures how well Paideia finds the passages that answer a question, and
how well the summaries it writes are supported by the passages they cite. It
runs offline, on a corpus written for it, and every number below is written by
the benchmark itself, `scripts/evaluate_retrieval.py`. None is typed by hand.
The design is explained in decision record 20.

## Reproducing it

From the repository root, with the services running (`docker compose up -d`)
and the virtual environment active:

```
python scripts/evaluate_retrieval.py                # retrieval, about twenty minutes
python scripts/evaluate_retrieval.py --generation   # also the summaries
```

`--generation` needs the local language model (Ollama) and adds about five
minutes. Each run rebuilds its own database, the development
database's name with `_eval` appended, so development and test data are never
touched. It writes every number, question by question, to
[`results.json`](results.json), and rewrites the tables below.

Latency depends on the machine, and the summaries on the model, so a rerun
elsewhere will not match these figures exactly. Retrieval scores vary a
little too, for a reason that applies to the app as well: when two passages
tie, keyword search and the fusion step order them by their ids, and ids are
new for every upload. Each run therefore reads the corpus into a fresh
database three times and reports the mean, with the lowest and highest build
beside the main score.

## The run

<!-- results:run -->
| | |
|---|---|
| Retrieval run | 2026-11-14T19:44:13+00:00, commit 21422c6 with uncommitted changes |
| Inputs fingerprint | 0997b798e31b: the corpus, labels, app and benchmark code and pinned dependencies; a rerun on the same files prints the same |
| Machine | Apple M3 Pro, 18 GB, macOS-26.5.2-arm64-arm-64bit-Mach-O |
| Corpus | 10 documents, 29 pages, 10589 words, 92 passages |
| Questions | 80, each asked 3 times per method, in each of 3 fresh builds of the database |
| Models | embedding BAAI/bge-small-en-v1.5, reranker Xenova/ms-marco-MiniLM-L-6-v2 |
| Search sizes | 30 from keyword search, 30 from semantic search, 30 reranked, 10 returned |
| Labels checked | 2026-11-15, in a second pass separate from writing them: every question and its evidence, and every passage a method ranked first without a label, rechecked against the text; one passage added as evidence and two questions reworded. Not an independent human review. |
| Generation run | 2026-11-14T18:23:16+00:00, commit 21422c6, model ministral-3:8b |
<!-- /results:run -->

## Findings

<!-- results:findings -->
- Highest MRR@10: D. Hybrid + reranker (the app), 0.925.
- Reranking the fused list raised MRR@10 from 0.848 to 0.925 and put the right passage first for 90% of questions instead of 77%, at a median 619 ms per search instead of 12 ms.
- Questions in other words: semantic search alone reached MRR@10 0.605, keyword search alone 0.704, the app 0.823.
- Questions naming the term: semantic 1.000, keyword 0.933, the app 1.000.
- The app put a labelled passage first for 72 of 80 questions; it missed some evidence in its top 10 for 1 (p01).
- Summaries: 10 of 10 written; 89% of 83 citations supported their point, 100% of 70 key points were grounded, and they covered 98% of the key facts. Median 31 s per summary.
- The judge agreed with the review on 83% of 30 sampled pairs. Of the pairs it called supported, the review agreed for 76%; corrected with the review, about 68% of all citations support their point.
<!-- /results:findings -->

## Retrieval

Each question is asked four ways, and each way returns its best 10 passages:

- **A. Semantic:** vector search alone, by meaning.
- **B. Lexical:** keyword search alone, Postgres full-text search.
- **C. Hybrid:** both searches, merged by Reciprocal Rank Fusion, as the app
  does before reranking.
- **D. Hybrid + reranker:** the app's search as it runs: the fused list, with
  a cross-encoder reading the best of it and ordering them again.

The scores:

- **Recall@k:** the share of a question's evidence passages among the first
  k results. A question needing two passages that finds one scores 0.5.
- **MRR@10:** the mean over the questions of 1 divided by the position of
  the first evidence passage among the first 10, or 0 if none is there. 1
  means the right passage always comes first.
- **Right passage first:** how often the first result is evidence.
- **Time:** each question is asked three times by each method after a
  warm-up, and the median of the three is that question's time. The table
  gives the median and the 95th percentile over the questions, measured on
  one machine with one person searching.

<!-- results:retrieval -->
| Method | Recall@5 | Recall@10 | MRR@10 | MRR@10, lowest to highest build | Right passage first | Median time | 95th percentile |
|---|---|---|---|---|---|---|---|
| A. Semantic | 0.925 | 0.969 | 0.818 | 0.818 | 74% | 8.9 ms | 11.1 ms |
| B. Lexical | 0.931 | 0.944 | 0.846 | 0.846 | 78% | 1.9 ms | 4.2 ms |
| C. Hybrid (fused) | 0.956 | 0.981 | 0.848 | 0.845 to 0.852 | 77% | 12.3 ms | 14.6 ms |
| D. Hybrid + reranker (the app) | 0.956 | 0.994 | 0.925 | 0.925 | 90% | 619.1 ms | 700.6 ms |
<!-- /results:retrieval -->

### By kind of question

MRR@10:

<!-- results:mrr-by-kind -->
| Method | Names the term (25) | In other words (30) | Rare term, everyday question (10) | Needs two passages (15) |
|---|---|---|---|---|
| A. Semantic | 1.000 | 0.605 | 0.733 | 1.000 |
| B. Lexical | 0.933 | 0.704 | 0.900 | 0.947 |
| C. Hybrid (fused) | 0.967 | 0.689 | 0.912 | 0.922 |
| D. Hybrid + reranker (the app) | 1.000 | 0.823 | 1.000 | 0.956 |
<!-- /results:mrr-by-kind -->

Recall@10:

<!-- results:recall10-by-kind -->
| Method | Names the term (25) | In other words (30) | Rare term, everyday question (10) | Needs two passages (15) |
|---|---|---|---|---|
| A. Semantic | 1.000 | 0.967 | 0.900 | 0.967 |
| B. Lexical | 1.000 | 0.867 | 1.000 | 0.967 |
| C. Hybrid (fused) | 1.000 | 0.967 | 1.000 | 0.967 |
| D. Hybrid + reranker (the app) | 1.000 | 1.000 | 1.000 | 0.967 |
<!-- /results:recall10-by-kind -->

Keyword search and semantic search fail on different questions, which is why
fusing them helps, and the reranker, which reads the question and each
passage together, does most of the ordering. Questions that name their topic
exactly are the easy case for every method. Questions in other words are the
hard case, and they are where the methods differ most.

Semantic search alone does worse than expected on questions in other words.
Those questions avoid the topic's own term but keep everyday words, and the
small embedding model places passages on near-identical topics, such as CPU
and disk scheduling, close together. The reranker recovers most of what it
loses.

## Generation

The app writes a summary of each document with the local language model,
each key point citing the passages it comes from (decision record 09). The
benchmark has it write the ten summaries exactly as the app does, then judges
them:

- **Citations supported:** the share of citations whose passage supports the
  point citing it.
- **Points grounded:** the share of key points supported by at least one of
  their citations. A point citing nothing counts as not grounded.
- **Key facts covered:** each document has five key facts a summary of it
  should cover ([`key-facts.json`](key-facts.json)). A summary covers a fact
  when, for each of the fact's word groups, a word of its overview or key
  points begins with one of the group's words.

Whether a passage supports a point is decided by the app's reranker, the same
check every practice item passes before it is kept (decision record 14): the
point is read against the passage, and a score of 0.5 or more counts as
supported. The reranker was trained to judge relevance, not truth, so a
sample of its verdicts was checked, below.

<!-- results:generation -->
| Document | Key points | Citations | Citations supported | Points grounded | Key facts covered | Seconds |
|---|---|---|---|---|---|---|
| 01-processes-and-threads.pdf | 7 | 8 | 7 of 8 | 7 of 7 | 5 of 5 | 36 |
| 02-cpu-scheduling.pdf | 7 | 7 | 7 of 7 | 7 of 7 | 5 of 5 | 26 |
| 03-synchronization.pdf | 7 | 7 | 7 of 7 | 7 of 7 | 4 of 5 | 30 |
| 04-deadlock.pdf | 7 | 7 | 7 of 7 | 7 of 7 | 5 of 5 | 26 |
| 05-memory-management.pdf | 7 | 7 | 7 of 7 | 7 of 7 | 5 of 5 | 31 |
| 06-virtual-memory.pdf | 7 | 8 | 8 of 8 | 7 of 7 | 5 of 5 | 31 |
| 07-file-systems.pdf | 7 | 8 | 8 of 8 | 7 of 7 | 5 of 5 | 26 |
| 08-crash-consistency.pdf | 7 | 8 | 8 of 8 | 7 of 7 | 5 of 5 | 28 |
| 09-storage-and-disk-scheduling.pdf | 7 | 10 | 8 of 10 | 7 of 7 | 5 of 5 | 33 |
| 10-io-and-system-calls.pdf | 7 | 13 | 7 of 13 | 7 of 7 | 5 of 5 | 42 |
| **All 10** | 70 | 83 | **89%** | **100%** | **98%** | median 31 |
<!-- /results:generation -->

### The judge, checked against a review

Thirty key point and passage pairs were set aside from the run: up to half
of them, as far as there were enough, pairs the judge called unsupported, and
the rest pairs it called supported. Each was then decided again, by the
strict rule that a point is supported only if the passage states everything
it claims, in two separate passes that agreed on every pair and never saw
the judge's verdicts ([`judge-review.json`](judge-review.json)). This was not
an independent human review.

The sample holds more of the pairs the judge rejected than all citations do,
so the judge's agreement on it is not its accuracy over all citations. The
corrected figure takes, within each of the judge's two verdicts, the share
the review called supported, and weights it by how many of all citations got
that verdict. With samples this small it is an approximation.

<!-- results:judge -->
| | Pairs | Review: supported |
|---|---|---|
| Judge said supported | 21 | 76% |
| Judge said unsupported | 9 | 0% |
| **All reviewed** | 30 | judge agreed on **83%** |

Citations supported, all 83: the judge says 89%; corrected with the review, about **68%**.
<!-- /results:judge -->

The judge errs in one direction: it accepts citations the review rejects,
and never the reverse. The rejected citations share a pattern. The point
itself is true of the document, and the summaries cover their documents'
key facts well, but the passage cited is a neighbouring one, not the one
that says it. In the I/O document several points cite the passage just
before or after the right one. One rejection comes from the chunker: a point
cited a passage that is only the end of a sentence split by a page break.

## The dataset

**The corpus** ([`corpus/`](corpus/)) is ten lecture notes on operating
systems, written for this benchmark so they can be published with it. They
cover the topics of an introductory course, and they deliberately contain
near-misses: CPU scheduling beside disk scheduling, journaling beside
write-ahead logging and log-structured file systems, mutexes beside spinlocks
and semaphores, internal beside external fragmentation, and starvation in
three different settings. The benchmark turns each into a PDF, with real
headings and paragraphs over A4 pages, and the app reads it as it reads any
upload.

**The questions** ([`questions.json`](questions.json)) come in four kinds:

- **Names the term:** "What is the convoy effect?"
- **In other words:** the topic described without its name. Each lists the
  words it must not contain, such as "thrashing", so it cannot be answered by
  matching them.
- **Rare term, everyday question:** "my laptop crawls when I open too many
  apps at once, is that thrashing?"
- **Needs two passages:** "How do a system call and a device interrupt each
  get the processor into the kernel, and how do they differ?"

Each question names its evidence by quoting it from the corpus. At run time
each quote is found in whichever passage the app's chunker put it in, so the
labels stay valid if the chunker changes. Before anything is measured, the
benchmark checks every label: each quote appears exactly once in the corpus
and inside exactly one passage of the document it names; a question needing
two passages names two different passages; a term question contains its term,
as does its evidence; a question in other words avoids its listed words. The
same checks run in CI (`api/tests/test_evaluation.py`).

**The second pass.** Before these results were published, every question
and its evidence, and every passage that some method ranked first without
being labelled, were rechecked against the text in a pass separate from
writing them. One passage was added as an alternative answer to part of a
question, two questions were reworded to ask exactly what their evidence
answers, and the key facts' words were tightened so that they credit only
summaries that state the fact. This was not an independent human review;
`questions.json` and the run table above record it.

## What these numbers do not show

- **The corpus is small:** 92 passages. The app's reranker reads 30
  candidates per search, a third of this corpus, while in a large environment
  it would read a much smaller share. Recall here is therefore higher than it
  would be among thousands of passages.
- **The questions were written alongside the corpus,** and may be closer to
  its wording than students' real questions would be, even in the kind that
  avoids the topic's terms.
- **No independent person checked the labels or the judge's sample.** A
  separate pass catches mistakes, but shares some blind spots of whoever
  wrote them.
- **The judge of support is a relevance model,** not a model of logical
  entailment. It is lenient, as the review above shows, so its own citation
  score is an overestimate; the corrected figure rests on a small sample.
- **Completeness is counted by words.** A summary that covers a fact in
  different words is not credited, and one that mentions the words without
  explaining the fact is.
- **Latency is one laptop,** warm, with one person searching. It shows the
  relative cost of each stage, not the speed of a deployed service.

# Decision records

One record per phase of the project. Each one says what was decided, what
was tried or rejected and why, how it was tested, and what it costs. Records
are not rewritten when a later one changes a decision; the later record says
what it replaces. All 23 are accepted.

Records 01 to 22 follow the original roadmap; its phase 23, the
documentation, has no record of its own. From record 24 on, the project
extends to mathematics, starting with linear algebra, in four planned
phases: maths notation (24), reading maths from PDFs (25), computed
exercises (26), and a maths evaluation (27). Record 24 sets out that plan
and the decisions that hold across it.

| # | Record | What was decided | Date |
|---|---|---|---|
| 01 | [Foundation](01-foundation.md) | One PostgreSQL database with pgvector instead of a separate vector database; FastAPI and Next.js; the AI parts run locally, behind interfaces. | 2026-09-18 |
| 02 | [Environments, migrations and testing](02-environments.md) | Every schema change is an Alembic migration, checked against the models; tests run on their own database, rolled back after each test. | 2026-10-13 |
| 03 | [PDF ingestion](03-pdf-ingestion.md) | Files on disk and page text in Postgres; uploads streamed as the raw body; PyMuPDF behind a parser interface; every dependency pinned. | 2026-11-02 |
| 04 | [Chunking and the content index](04-chunking.md) | Deterministic chunks along paragraphs and headings, with ids derived from content; keyword search inside Postgres. | 2026-11-02 |
| 05 | [Local embeddings and vector search](05-embeddings.md) | fastembed on ONNX Runtime instead of Sentence Transformers, bge-small-en-v1.5, vectors on the chunk rows, an HNSW index with iterative scans. | 2026-11-07 |
| 06 | [Hybrid retrieval and reranking](06-hybrid-retrieval.md) | Keyword and semantic search fused by Reciprocal Rank Fusion, then reranked by a local cross-encoder, every stage visible. | 2026-11-07 |
| 07 | [Citations and the evidence model](07-citations.md) | One citation shape built in one place; a document's version is its file's SHA-256; "Show in page" opens the passage in its page. | 2026-11-08 |
| 08 | [The language model as a service](08-llm-service.md) | ministral-3:8b on Ollama behind one structured-output interface, with timeouts, retries and versioned, locked prompts. | 2026-11-09 |
| 09 | [Automatic document summaries](09-document-summaries.md) | Summaries written in the background into one table of generated artifacts, keyed by what they were written from; history never overwritten. | 2026-11-09 |
| 10 | [The environment's summary](10-environment-summary.md) | The subject's summary is built from the documents' summaries, and rebuilt by itself only when they change. | 2026-11-09 |
| 11 | [Concept extraction](11-concepts.md) | The model proposes concepts; the backend normalizes names by fixed rules, validates every proposal and merges by name, never by alias. | 2026-11-09 |
| 12 | [Knowledge graph](12-knowledge-graph.md) | The backend finds the pairs a passage connects; the model only picks one of six statements per pair; decisions are remembered. | 2026-11-10 |
| 13 | [Learning roadmap](13-learning-roadmap.md) | Fixed rules decide the stages and their order; the model only writes each stage's title. | 2026-11-10 |
| 14 | [Practice engine](14-practice-engine.md) | Four items per concept, each checked against its passages before it is kept; graded by the stored answer or the learner, never the model. | 2026-11-11 |
| 15 | [Learner state and spaced review](15-learner-state.md) | Each concept's state is worked out from the answers, never stored apart; reviews 1 to 32 days apart; "due" is the learner's own day. | 2026-11-11 |
| 16 | [Automatic study plan](16-study-plan.md) | Today's plan by fixed rules: strengthen, review, learn, skim, with effort estimates and a reason for each, never written by the model. | 2026-11-12 |
| 17 | [Incremental updates](17-incremental-updates.md) | Embeddings reused by text, document versions, practice kept while its passages are, and a report of what every change did. | 2026-11-14 |
| 18 | [Background processing](18-background-jobs.md) | A job table in Postgres is the queue and Redis only wakes a worker with two lanes, heartbeats, retries and cancellation. | 2026-11-14 |
| 19 | [Dashboard and product polish](19-dashboard-polish.md) | The Overview tab is the dashboard, built from the tabs' own queries; session history from the answers; shared loading and failure states. | 2026-11-14 |
| 20 | [Evaluation and benchmarking](20-evaluation.md) | A corpus written for the benchmark, 80 questions labelled by quote, four search methods compared, every number written by a script. | 2026-11-15 |
| 21 | [Reliability, security and data integrity](21-reliability.md) | An audit of eleven risks: safe names, a page limit, duplicate jobs refused by the database, an orphan sweep, structured logs with request ids. | 2026-11-15 |
| 22 | [Automated testing and CI](22-testing-and-ci.md) | mypy, coverage reported but never enforced, component tests, one end-to-end journey with a stand-in model, three CI jobs. | 2026-11-15 |
| 24 | [Maths notation](24-maths-notation.md) | Maths stored as LaTeX between `\(` `\)` and `\[` `\]`, typeset by a bundled KaTeX with trust off; the model's dollar signs moved and its JSON damage repaired; every formula checked against KaTeX's own commands; prose rules blind to formulas. | 2026-11-19 |

How to run the project is in [../setup.md](../setup.md); the benchmark's
results are in [../evaluation/retrieval-benchmark.md](../evaluation/retrieval-benchmark.md).

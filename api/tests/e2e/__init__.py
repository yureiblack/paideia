"""What the end-to-end tests in web/e2e/ run (decision record 22).

The real API, worker and page, on their own database, data folder, Redis
database and ports, with one thing swapped: the language model is a
stand-in, because the local model cannot run in CI. PDF reading,
embeddings, the reranker, Postgres and Redis are the real ones.

    prepare  an empty database and data folder, and the PDFs to upload
    server   the API, with the mock language model
    worker   the background worker, with the mock language model
    model    the stand-in: the tests' MockProvider, naming concepts after
             their passages' headings

web/playwright.config.ts starts all three; nothing here is meant to be run
by hand.
"""

# 08. The language model as a service

Date: 2026-11-09
Status: accepted

## Context

Summaries, concept maps, roadmaps and practice questions will all be written
by a language model. The roadmap asks for that model to arrive as a
replaceable service before any of those features. Domain code calls one
generic operation, `generate_structured(prompt, schema)`. Ollama serves the
model locally, behind a provider interface that a mock or a hosted service
could also implement. The model name is configurable, requests have timeouts
and retries, prompts are versioned files, and every answer records the model
and prompt version behind it. One narrow feature proves it: a concise,
source-grounded summary of one document.

The project is free and local. The development machine is an Apple M3 Pro
with 18 GB of memory.

## Decisions

### Ministral 3 8B, run by Ollama

Ollama (MIT) serves open models on the machine and gives them an HTTP API.
It runs natively, as a Homebrew service, not in Docker: on a Mac, Docker
cannot use the GPU, and the model would run several times slower.

Three Apache-2.0 models of about 8 billion parameters fit the machine. Each
summarized four documents built from the retrieval fixture, from 6 to 28
passages. The prompt numbered every passage, the answer's shape was enforced
through Ollama, and the search reranker judged whether each key point was
supported by the passage it cited.

| Model | Valid answers | Points supported by their citation | 28-passage document covered | Time per summary |
|---|---|---|---|---|
| ministral-3:8b | 4/4 | 100% | 68% | 35 s |
| qwen3:8b, thinking off | 4/4 | 100% | 43% | 26 s |
| qwen3:8b, thinking on | 4/4 | 100% | 29% | 47 s |
| granite4.2:8b | 4/4 | 100% | 29% | 217 s |

Every model returned valid answers and cited correctly, so coverage and speed
decided. Ministral 3 cited two-thirds of the long document's passages where
Qwen3 cited under half, and coverage is what a summary is for. Granite wrote
3,000 to 6,000 tokens per answer. Qwen3's thinking mode doubled the time and
gained nothing. Llama and Gemma were not considered: their licences carry
their makers' conditions. The model is a setting, `LLM_MODEL`.

Either finalist takes about 7.5 GB of memory at a 32K context.

### One interface, `generate_structured`

`app/llm.py` defines `LLMProvider`. `generate_structured(prompt, schema)`
returns the answer validated against a Pydantic schema, wrapped in
`Generated` with the model's name, the prompt's version and the seconds it
took. `check()` reports whether the model is ready. `OllamaProvider` is the
production implementation. The tests use `MockProvider`. Nothing outside
`app/llm.py` knows that Ollama exists.

The provider calls Ollama's HTTP API with `httpx2`, Pydantic's maintained
fork of httpx, which FastAPI's test client already needed. It is now pinned
as a dependency of the app itself. Ollama's own Python package would have
added a dependency for one endpoint.

### Every request is constrained

Each request sends the answer's JSON schema as Ollama's `format`, so the
model can only write output of that shape. It also sends temperature 0 and a
fixed seed, so the same request gives the same answer; `LLM_CONTEXT_TOKENS`
(16,384); a cap of 2,048 tokens on the answer; and `think: false`, which
models without a thinking mode ignore.

Two findings from the prototype shaped the schemas:

- Without a maximum on every list and a cap on the answer, a model asked for
  structured output kept writing for minutes on a three-sentence request.
  With them, every request finished normally in 6 to 18 seconds. Every
  schema now bounds every list.
- Integer ranges in a schema are enforced while the model writes. Told to
  cite passage 7 when given three, both finalists cited only 1 to 3. A summary
  can therefore only cite passages it was given. The answer is validated
  again on arrival all the same.

Ollama 0.40.15's own timing fields came back garbled (a "2,106-second" read
inside a 34-second request), so the provider times requests itself.

### Timeouts and retries

A connection must open within 5 seconds, and a request may take
`LLM_TIMEOUT_SECONDS` (300). A refused connection, a timeout, a server error
or an answer that fails validation is retried up to `LLM_MAX_RETRIES` (2)
times, after pauses of 1 and then 2 seconds. A retry after an invalid answer
uses temperature 0.3 and a new seed, because at temperature 0 the model would
repeat its mistake.

A model that is not downloaded, or a request Ollama refuses, is reported at
once, since retrying cannot help. Every failure becomes an `LLMError` whose
message says what to do: "Start it with: brew services start ollama", "Run:
ollama pull ministral-3:8b". The API answers 503 with that message.
`GET /health/llm` reports the same, and the header shows it.

### Prompts are versioned files

Each prompt version is a file, such as `app/prompts/document_summary/v1.txt`,
with a system part and a user part. Placeholders are written `$name`
(Python's `string.Template`), so braces in a prompt never clash with them.
Every answer records the version it came from, such as
`document_summary/v1`.

A released version is never edited, because answers already generated name
it. `tests/test_prompting.py` holds each released file's SHA-256 and fails
when one changes; a change is a new file, `v2`. While writing version 1, a
trial summary came back with Markdown bold and one claim the passage did not
make ("round robin risks unfairness"). The prompt gained "state nothing the
passages do not say" and "plain sentences, without Markdown", and the next
trial had neither problem. These changes were made before release; after
release, the same fix would have been a v2.

### The summary feature

`POST /api/documents/{id}/summary` asks the model for an overview and three
to seven key points.

- **Numbered passages.** The passages are numbered `[1]`, `[2]` in reading
  order, each with its section heading. Key points cite those numbers, which
  are short and easy for a model to copy, unlike chunk ids. Each number is
  then turned back into its passage's `Citation`, the object search results
  carry (record 07), so a summary's sources open exactly as a search
  result's do.
- **Long documents.** A document whose text fits one request, an estimated
  10,000 tokens at four characters each (which overestimates), is summarized
  in one call. A longer one is cut into sections that each fit. Every section
  is summarized with the document-wide passage numbers, and a second prompt,
  `combine_summaries/v1`, joins the sections' notes into one summary, citing
  only numbers the notes cited.
- **Size limit.** On request, at most four sections are summarized, about
  five minutes. A longer document is refused with a 422 and the reason.
- **Not stored.** The summary is generated afresh on each request.

Measured: a three-page lecture in 17 to 26 seconds. A 28-passage course,
forced into three sections for the trial, took 118 seconds and cited 11 of
its 14 pages.

### Summarize in the Materials tab

Each ready document gets a "Summarize" button that shows the overview, then
each key point with chips naming the page and section of each passage it
cites ("p. 3 · File Systems"). A chip opens the passage in its page, the
panel the Search tab uses, so every claim can be checked against the
material. A footer names the model, the prompt version and the time taken.
The header shows the model's status next to the API's and the database's,
with the reason on hover when it is down.

## Testing

- `OllamaProvider` against a simulated Ollama (httpx2's `MockTransport`): the
  exact request body; retries and their pauses; the messages for an
  unreachable server, a timeout, a persistent server error, a missing model
  (not retried), a refused request (not retried) and invalid answers (retried
  with randomness); and the readiness check.
- Prompts: rendering, required placeholders, file structure, and the lock on
  released versions.
- Summaries with `MockProvider`:
  - passages numbered in reading order and cited back as the right
    citations, each listed once;
  - a long document read in sections with document-wide numbers, then
    combined, the combining call allowed only the numbers the notes cited;
  - refusals that come before any model call;
  - the answer schema's ranges, allowed values and list limits.
- The API: shape, citations identical to source previews, 404, 409, 422, 503,
  and the model status.
- A real-model test uploads a lecture and checks the summary's form and
  grounding: plain text, every point cited, every page covered, every point
  supported by a cited passage as judged by the reranker. It needs Ollama
  with the model and is skipped where they are missing, including CI, whose
  machines have no GPU and would take minutes per summary.
- Fourteen deliberate breaks, from not retrying a refused connection to
  editing a released prompt, are each caught by a test.

## Consequences

- Summaries need Ollama running with the 6 GB model, and about 7.5 GB of
  memory while working. Everything else in the app works without it.
- A small local model can still state something its passages do not say. The
  prompt asks it not to, and every claim carries citations a reader can open.
  Measuring grounding systematically belongs to Phase 20's evaluation.
- CI never runs the real model. The provider, prompts and summary logic are
  covered there by the simulated and mock tests; the real-model test runs
  locally.
- Phase 09 stores summaries and writes them automatically when a document is
  ready. The provider, prompts and summary service carry over unchanged.

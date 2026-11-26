# API

Every endpoint the backend serves. With the backend running, the generated,
interactive version is at http://localhost:8000/docs. How to run it is in
[setup.md](setup.md).

Every response carries an `X-Request-ID` header, and every error answers
`{"detail": ..., "request_id": ...}` with the same id, which finds the
request in the API's log. A caller may send its own `X-Request-ID`; it is
kept if it is at most 64 letters, digits, dots, dashes and underscores.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Is the API process alive. Touches nothing else. |
| GET | `/health/db` | Can the API reach Postgres, and is pgvector available. Returns 503 if not. |
| GET | `/health/worker` | Is a background worker running. Returns 503 with what to do if not. |
| GET | `/health/llm` | Is Ollama answering, with the configured model downloaded. Returns 503 with the reason if not. |
| GET | `/api/environments` | Every environment, newest first. |
| POST | `/api/environments` | Create one. Body: `name`, optional `description`. Returns 201. |
| GET | `/api/environments/{id}` | One environment, or 404. |
| PATCH | `/api/environments/{id}` | Change only the fields sent. Returns the updated environment. |
| DELETE | `/api/environments/{id}` | Delete one, with its documents and files. Returns 204. |
| POST | `/api/environments/{id}/documents?filename=...` | Upload a PDF as the raw request body. Returns 201; reading happens in the background: its text, then its maths and figures by the vision model, then what is made from it. |
| GET | `/api/environments/{id}/documents` | The environment's documents, newest first, with their status. |
| GET | `/api/documents/{id}` | One document: status is `uploaded`, `processing`, `ready` or `failed`. |
| GET | `/api/documents/{id}/pages` | The extracted text, page by page, numbered from 1. Paragraphs are separated by a blank line. Each page's `figures` give each figure's `key`, its `caption`, and where all its text is in the page (`start`, `end`), which the reader shows as its picture. |
| GET | `/api/documents/{id}/figures/{key}/image?version={sha256}` | A figure's picture, with its caption, as a PNG, for that version of the file. 404 for another version or a figure the page does not hold. |
| GET | `/api/documents/{id}/chunks` | The passages the document was cut into, in reading order, each with its heading and exact position in the pages. |
| POST | `/api/documents/{id}/reprocess` | Read a document again, for example after a failure, with any of its maths and figures not read yet. Returns 202. |
| GET | `/api/documents/{id}/summary` | The document's current summary: `status` (`pending`, `generating`, `ready` or `failed` with an `error`), then its `overview` and `key_points`, each with its `citations`, the `model` and `prompt_versions` that wrote it, and how many `earlier_versions` are kept. 404 if none yet. |
| POST | `/api/documents/{id}/summary` | Make sure the document has a summary: 200 with it if ready, 202 if it is waiting or being written, which this starts if it was missing or had failed. Asking again never writes a second one. 409 if the document is not read yet, 422 if it cannot be summarized (no text, or too long). |
| GET | `/api/documents/{id}/summaries` | Every summary of the document, newest first, `current` marking the one for its present text, model and prompts. |
| GET | `/api/environments/{id}/summary` | Where the environment's summary stands: `state` (`up_to_date`, `updating`, `waiting` for documents still being read or summarized, `stale`, `failed`, or `none`), the newest `summary` with its `overview`, cited `key_points` and the documents it is `based_on`, the documents `not_included` and why, and how many `earlier_versions` are kept. |
| POST | `/api/environments/{id}/summary` | Bring it up to date, or try again after a failure. It never writes twice for the same material, and waits while documents are on their way. 422 if there is nothing summarized to build it from. |
| GET | `/api/environments/{id}/summaries` | Every summary of the environment, newest first. |
| GET | `/api/environments/{id}/concepts` | Every concept in the environment, by name, with its `definition`, `aliases`, the `documents` it appears in and the `evidence` citations; and each document's extraction state (`proposed` and `kept` counts what passed validation). |
| GET | `/api/documents/{id}/concepts` | One document's extraction state and the concepts it contributes. |
| POST | `/api/documents/{id}/concepts` | Make sure the document's concepts are extracted, or try again after a failure: 200 if ready, 202 if waiting or being extracted. 409 if the document is not read yet, 422 if it has no text or is too long. |
| GET | `/api/environments/{id}/graph` | The environment's knowledge graph: every concept as a `node`, every relationship as an `edge` (`source`, `target`, `relationship_type` `PREREQUISITE_OF`, `PART_OF` or `RELATED_TO`, and the model's `confidence`), and where it stands: `state` as for the environment's summary, with `waiting` for documents still being read or having their concepts extracted; `pairs` considered and how many the model was `asked` about in the last build. |
| POST | `/api/environments/{id}/graph` | Bring the graph up to date, or try again after a failure: 200 if up to date, 202 if being built or waiting. It never asks the model twice about the same pair. 422 if no concepts are connected yet. |
| GET | `/api/concepts/{id}/neighbourhood` | One concept and what is next to it: its `prerequisites` and `dependents`, all the way along with their `depth`, what it is `part_of`, its `parts`, and what it is `related` to, each direct relationship with its `confidence` and `evidence` citations. |
| GET | `/api/environments/{id}/roadmap` | The learning roadmap: its `stages` in order, each with a `title` and `description` (`written` by the local model, or a plain title until then), the `documents` it draws on, and its `concepts` in order, each with what it `builds_on`, whether it is `in_cycle`, and its `evidence` citations; the `cycles` of prerequisites; and the `state` of the titles, as for the environment's summary, with `waiting` for the knowledge graph. |
| POST | `/api/environments/{id}/roadmap` | Write the titles of the current stages, or try again after a failure: 200 if up to date, 202 if being written or waiting for the graph. It never asks the model twice about the same stage. 422 if there are no concepts yet. |
| GET | `/api/environments/{id}/practice?until=...` | Practice at a glance, with `until` the end of the learner's day (with its time zone): how many items are practised, how many concepts are `due_concepts` today and `new_concepts`, the next later review, the concepts that `needs_attention` and are `recently_strong` with why, and each concept: its items' `state` (`none`, `pending`, `generating`, `ready`, `failed` with an `error`, or `outdated` when its material changed) and the learner's state worked out from their answers (`review` new, due or scheduled; `exposures`, `recalled`, `failed`, last attempted and recalled, `gap_days`, `next_review_at`, `attention`, and `strong`: recalled on its last answer after a gap of four days or more). |
| GET | `/api/environments/{id}/practice/history` | The last 20 practice sessions, newest first, worked out from the answers: answers less than 30 minutes apart are one session. Each has when it started and ended, its `answers`, how many were `recalled`, and its `concepts` in the order first answered. |
| POST | `/api/environments/{id}/practice` | Prepare practice items for the concepts in `concept_ids`, in the background: 202 while they are written. Never writes twice for the same passages, model and prompt. |
| POST | `/api/concepts/{id}/practice` | The same, for one concept. |
| GET | `/api/environments/{id}/practice/session?until=...` | A session of up to 10 items, interleaved: two items from each concept due by `until`, overdue first, then new ones in roadmap order; or with `concept_id` repeated (a stage) those concepts' items. Items of the kinds the backend grades never carry their answer. |
| POST | `/api/learning-items/{id}/attempts` | Answer an item: `choice` (multiple choice), `truth` (true/false) or `knew` (short answer, flashcard, after seeing the answer), with optional `text` and `seconds`. Returns whether it was right, the answer, why, the passages it comes from, and when its concept comes back (`due_at`, `gap_days`). 409 if the item was replaced, 422 for an answer of the wrong kind. |
| GET | `/api/environments/{id}/plan?until=...&minutes=...` | Today's study plan, worked out afresh: `sessions` in order, each with its `kind` (`strengthen`, `review`, `learn` or `skim`), `title`, estimated `minutes`, `rationale`, `concepts`, and the roadmap `stage` or `document` it opens; with an optional time budget `minutes` (5 to 600), the sessions that did not fit in `later`. `until` is the end of the learner's day, with its time zone. |
| POST | `/api/documents/{id}/versions` | Upload a new version of a document as the raw PDF body. The document keeps its id, name and place; only what changed is redone. Returns 202. 409 if the file is the current version, another document's file, or the document is being read. |
| GET | `/api/environments/{id}/updates` | Every change to the environment's material, newest first: its `kind` (`added`, `new_version`, `reprocessed`, `deleted`; `maths` and `figures` for readings asked for before record 31), `status`, `steps` with their state and what each did, and once done its `report`: concepts and relationships new and removed, passages new, kept and removed, embeddings computed and reused, what was updated and what was left unchanged. |
| GET | `/api/updates/{id}` | One update. |
| GET | `/api/environments/{id}/jobs` | The environment's background jobs, queued and running first: each with its `title`, `lane` (`read` or `model`), `status` (`queued`, `running`, `succeeded`, `failed`, `cancelled`), `progress` (0 to 100) and current `step`, `error`, `attempts` and when it may run again (`not_before`). |
| GET | `/api/jobs/{id}` | One job. |
| POST | `/api/jobs/{id}/cancel` | Cancel a job: a queued one at once, a running one before its next step. A finished job is left as it is. |
| DELETE | `/api/documents/{id}` | Delete one, with its pages and file. Returns 204. |
| POST | `/api/search` | Search one environment by keywords and meaning, fused and reranked. Body: `environment_id`, `query`, optional `top_k` (1 to 50, default 10), optional `debug`. Returns the best passages first, each as a `citation` (environment, document, `document_version`, the file's SHA-256, filename, chunk, pages, heading and `excerpt`) and a `score`, the reranker's judgement from 0 to 1. With `debug: true` it also returns every candidate with its keyword, semantic, fusion and rerank scores. |
| GET | `/api/chunks/{id}/preview` | A cited passage in its place: its citation, and every page it touches with the part it covers (`highlight_start` to `highlight_end`). 404 if the passage is no longer in its document. |

Invalid input gets a 422 listing each problem and the field it belongs to. An
upload is refused with 409 if the same file is already in that environment, 413
if it is larger than the limit (50 MB by default), and 415 if it is not a PDF.
Search returns 404 for an unknown environment, and 503 with the reason if the
embedding or reranking model cannot be loaded. A query written with search
syntax, a "quoted phrase", `OR` or a `-word`, is matched exactly; otherwise
any of its words may match.

Uploaded files are stored under `data/uploads/`, one folder per environment,
outside the database and outside git.

Documents read by an earlier version keep their old text format and may have
no chunks or no embeddings; a chunk without an embedding is still found by
its words.
`POST /api/documents/{id}/reprocess` reads one again with the current version,
embedding only the chunks that need it.

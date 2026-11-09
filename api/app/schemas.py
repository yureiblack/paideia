"""API schemas: the shape of data travelling over HTTP.

Purpose
-------
Models (app/models.py) describe stored tables. Schemas describe what a client
may send and what the API sends back. Keeping them separate means the API can
refuse fields a client must never set, such as id or created_at, and can change
its public shape without touching the table.

FastAPI validates every request body against these classes before an endpoint
runs, and answers 422 with a readable list of problems when one does not fit.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.config import settings

NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 2000

# Surrounding spaces are trimmed before the length rules apply, so "   " is not
# a valid name.
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH),
]


def _blank_to_none(value: str | None) -> str | None:
    """An empty description means "no description", stored as NULL."""
    return value or None


class EnvironmentCreate(BaseModel):
    """Body of POST /api/environments."""

    # Unknown fields are an error rather than silently ignored, so a client
    # sending "id" or a misspelt "nmae" finds out immediately.
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description | None = None

    _description = field_validator("description")(_blank_to_none)


class EnvironmentUpdate(BaseModel):
    """Body of PATCH /api/environments/{id}.

    Every field is optional and only the fields actually sent are changed.
    Sending "description": null clears the description. Sending "name": null
    is refused, because every environment needs a name.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None

    @field_validator("name")
    @classmethod
    def name_cannot_be_cleared(cls, value: str | None) -> str:
        # Validators do not run for fields left out of the request, so this
        # only fires when a client explicitly sends "name": null.
        if value is None:
            raise ValueError("name cannot be null")
        return value

    _description = field_validator("description")(_blank_to_none)


class EnvironmentRead(BaseModel):
    """What the API returns for an environment."""

    # Lets FastAPI build this from an Environment model object directly.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


DocumentStatus = Literal["uploaded", "processing", "ready", "failed"]


class DocumentRead(BaseModel):
    """What the API returns for an uploaded document.

    status is uploaded while waiting to be parsed, processing while being
    parsed, then ready or failed. error explains a failure. page_count,
    pages_with_text and repaired are filled in by a successful parse.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    environment_id: uuid.UUID
    filename: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    error: str | None
    page_count: int | None
    pages_with_text: int | None
    repaired: bool
    created_at: datetime
    updated_at: datetime


class PageRead(BaseModel):
    """The extracted text of one page, numbered from 1."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    content: str


class ChunkRead(BaseModel):
    """One passage of a document, with where its text sits in the pages."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    page_start: int
    char_start: int
    page_end: int
    char_end: int
    heading: str | None
    content: str
    content_hash: str


class SearchRequest(BaseModel):
    """Body of POST /api/search.

    top_k is how many results to return; without it, the RETRIEVAL_FINAL_K
    setting. debug adds every candidate and its scores at each stage.
    """

    model_config = ConfigDict(extra="forbid")

    environment_id: uuid.UUID
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    top_k: int = Field(default=settings.retrieval_final_k, ge=1, le=50)
    debug: bool = False


class Citation(BaseModel):
    """Where a passage came from: the one shape every part of the app cites
    with, search results now and generated summaries later.

    document_version is the SHA-256 of the document's file. The file never
    changes, and a chunk whose text changes gets a new chunk_id, so the
    version and the chunk id together pin one exact passage. filename serves
    as the document's title. excerpt is the passage itself.
    """

    environment_id: uuid.UUID
    document_id: uuid.UUID
    document_version: str
    filename: str
    chunk_id: uuid.UUID
    page_start: int
    page_end: int
    heading: str | None
    excerpt: str


class SourcePage(BaseModel):
    """One page a cited passage touches. The passage covers content from
    highlight_start up to, but not including, highlight_end."""

    page_number: int
    content: str
    highlight_start: int
    highlight_end: int


class SourcePreview(BaseModel):
    """A citation shown in its place: every page the passage touches, in
    order, each with the part the passage covers."""

    citation: Citation
    pages: list[SourcePage]


class SummaryPoint(BaseModel):
    """One key point of a summary and the passages it rests on."""

    text: str
    citations: list[Citation]


class SummaryRead(BaseModel):
    """A stored summary of one document and what it was written from.

    status is pending (waiting its turn), generating, ready or failed; error
    says why it failed. overview and key_points are filled in once ready.
    model, prompt_versions and source_version record what wrote it and from
    which text. current is false for a summary of an earlier text, or by an
    earlier model or prompt: kept, never overwritten. sections is how many
    parts the document was read in; seconds is the model's time.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    status: Literal["pending", "generating", "ready", "failed"]
    error: str | None
    overview: str | None
    key_points: list[SummaryPoint]
    model: str
    prompt_versions: list[str]
    source_version: str
    sections: int | None
    seconds: float | None
    current: bool
    created_at: datetime
    updated_at: datetime


class CurrentSummaryRead(SummaryRead):
    """The current summary, and how many earlier ones are kept."""

    earlier_versions: int


class SourceDocument(BaseModel):
    """A document an environment summary was built from, as it was then: the
    version of its file, and which of its summaries was used."""

    document_id: uuid.UUID
    filename: str
    document_version: str
    summary_id: uuid.UUID


class NotIncluded(BaseModel):
    """A document an environment summary leaves out, and why."""

    document_id: uuid.UUID
    filename: str
    reason: str


class EnvironmentSummaryRead(BaseModel):
    """A stored summary of a whole environment, built from its documents'
    summaries. based_on lists those documents as they were when it was built.
    current is false for one built from earlier material, model or prompt."""

    id: uuid.UUID
    environment_id: uuid.UUID
    status: Literal["pending", "generating", "ready", "failed"]
    error: str | None
    overview: str | None
    key_points: list[SummaryPoint]
    model: str
    prompt_versions: list[str]
    source_version: str
    based_on: list[SourceDocument]
    seconds: float | None
    current: bool
    created_at: datetime
    updated_at: datetime


class EnvironmentSummaryState(BaseModel):
    """Where an environment's summary stands, and the newest one to show.

    state is one of:
      up_to_date  the summary shown covers the material as it is now
      updating    a summary of the current material is being written; the
                  one shown, if any, is older
      waiting     documents are still being read or summarized
                  (waiting_for of them); it is built once they are done
      stale       the material changed and no rebuild has been asked for
      failed      building it failed; error says why
      none        nothing to summarize yet

    summary is the newest ready one, or none. not_included lists documents
    left out and why. earlier_versions counts older summaries kept.
    """

    state: Literal["up_to_date", "updating", "waiting", "stale", "failed", "none"]
    waiting_for: int
    error: str | None
    summary: EnvironmentSummaryRead | None
    not_included: list[NotIncluded]
    earlier_versions: int


class ConceptDocument(BaseModel):
    """A document a concept appears in."""

    document_id: uuid.UUID
    filename: str


class ConceptRead(BaseModel):
    """One concept of an environment: its name and definition as shown, its
    aliases, the documents it appears in, and the passages that explain it."""

    id: uuid.UUID
    name: str
    normalized_name: str
    definition: str
    aliases: list[str]
    documents: list[ConceptDocument]
    evidence: list[Citation]


class ExtractionState(BaseModel):
    """Where a document's concept extraction stands. document_status is the
    document's own (still being read, or could not be). status is none when
    no extraction was asked for, otherwise pending, generating, ready or
    failed (error says why). proposed and kept count the model's proposals and how
    many passed validation."""

    document_id: uuid.UUID
    filename: str
    document_status: Literal["uploaded", "processing", "ready", "failed"]
    status: Literal["none", "pending", "generating", "ready", "failed"]
    error: str | None
    model: str | None
    prompt_version: str | None
    proposed: int | None
    kept: int | None


class ConceptInventory(BaseModel):
    """Every concept in an environment, by name, and each document's
    extraction state."""

    concepts: list[ConceptRead]
    documents: list[ExtractionState]


class DocumentConceptsRead(BaseModel):
    """One document's extraction state and the concepts it contributes."""

    extraction: ExtractionState
    concepts: list[ConceptRead]


class SearchResult(BaseModel):
    """One passage that matched: where it came from, and how well it answers.

    score is the reranker's: between 0 and 1, higher means a better answer to
    the query. It orders results; it is not a probability.
    """

    citation: Citation
    score: float


class SearchCandidate(BaseModel):
    """One chunk either search found, with its place at every stage.

    Ranks count from 1. None means that stage never saw the chunk: keyword
    search did not match it, semantic search did not reach it, or it fell
    outside the reranked pool. lexical_score is Postgres's ts_rank,
    semantic_score cosine similarity, fusion_score the Reciprocal Rank Fusion
    sum, rerank_score the reranker's 0 to 1. final_rank is its place in the
    results, if it made them.
    """

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_start: int
    page_end: int
    heading: str | None
    lexical_rank: int | None
    lexical_score: float | None
    semantic_rank: int | None
    semantic_score: float | None
    fusion_score: float
    rerank_score: float | None
    final_rank: int | None


class SearchDebug(BaseModel):
    """How a search was ranked: the sizes it used and every candidate, in the
    merged order the reranker received them."""

    top_k_lexical: int
    top_k_dense: int
    candidate_pool: int
    final_k: int
    candidates: list[SearchCandidate]


class SearchResponse(BaseModel):
    results: list[SearchResult]
    debug: SearchDebug | None = None  # only when the request asked for it

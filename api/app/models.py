"""Database models: how the Python code sees each table.

Purpose
-------
A model is a Python class that mirrors one table. The class is the table, each
attribute is a column, and each object is one row. Code builds and reads these
objects; SQLAlchemy turns that into SQL.

The models describe the tables but never change them. Tables are created and
altered only by the Alembic migrations in migrations/versions/. `alembic check`
compares the two and fails if they disagree, so a model change that ships
without its migration is caught.

Tables so far: environments, documents, document_pages, document_chunks.
"""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

# Predictable names for constraints and indexes, so a later migration can find
# and drop them by name. The primary-key pattern matches Postgres's own default,
# "<table>_pkey", so the existing environments_pkey already conforms.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    # Every column, so a two-column constraint names both: uq_documents_environment_id_sha256.
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "%(table_name)s_pkey",
}


class Base(DeclarativeBase):
    """Parent of every model. Its metadata is the catalogue Alembic compares."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Environment(Base):
    """One learning environment: a subject such as Operating Systems.

    Mirrors revision 0a84e5243328 column for column.
    """

    __tablename__ = "environments"

    # Values the database generates (id, timestamps) come back in the same
    # INSERT or UPDATE statement through RETURNING, instead of a second query.
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # statement_timestamp(), not now(): Postgres's now() is frozen at the start
    # of the transaction, so an edit made later in the same transaction, which
    # is how every test runs, would not move it.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )


# The four stages of a document, in order. Stored lowercase as text with a
# CHECK constraint rather than a native Postgres ENUM, so adding a stage later
# is an ordinary migration.
DOCUMENT_STATUSES = ("uploaded", "processing", "ready", "failed")


class Document(Base):
    """One uploaded PDF belonging to an environment.

    The original file lives on disk at
    <data_dir>/uploads/<environment_id>/<id>.pdf, never in the database.
    status moves uploaded -> processing -> ready or failed; error says why a
    document failed. page_count, pages_with_text and repaired are filled in
    by a successful parse.
    """

    __tablename__ = "documents"
    __table_args__ = (
        # The same PDF twice in one environment is a mistake; the same PDF in
        # two environments is fine. Enforced here, not only in code, so two
        # simultaneous uploads cannot both slip through.
        UniqueConstraint("environment_id", "sha256"),
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')", name="status"
        ),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Deleting an environment deletes its documents in the database itself.
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    # The name the file had when it was uploaded. Display only: the file on
    # disk is named by id, so a hostile name can never become a path.
    filename: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the file as 64 lowercase hex characters: its fingerprint.
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(Text, server_default=text("'uploaded'"))
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    # Pages with any extractable text. 0 of 12 usually means a scanned PDF.
    pages_with_text: Mapped[int | None]
    # True when the file was damaged and PyMuPDF had to repair it to read it.
    repaired: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )


class DocumentPage(Base):
    """The text of one page of a document, as extracted.

    Pages are derived data: a reprocess deletes and rewrites all of a
    document's pages in one transaction, so they carry no timestamps of their
    own. page_number counts from 1, as a reader would.
    """

    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number"),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    page_number: Mapped[int]
    # Named content rather than text, which would shadow SQLAlchemy's text()
    # in this module and is also the name of a Postgres type.
    content: Mapped[str] = mapped_column(Text)


# What full-text search matches against. The English dictionary reduces words
# to their stems, so "processes" matches "process". The heading is weighted A
# and the body B, so a match in a chunk's heading ranks above one in its text.
SEARCH_VECTOR = (
    "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
    "setweight(to_tsvector('english', content), 'B')"
)


class DocumentChunk(Base):
    """A passage of a document, the unit of search and later of citation.

    Made by app/chunking.py. Its id is computed there from the document, the
    content and its occurrence, never by the database, so the same text always
    gets the same id and a reprocess never duplicates chunks. The position
    columns locate its exact text in the stored pages.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("ordinal >= 0", name="ordinal_not_negative"),
        CheckConstraint(
            "page_start >= 1 AND page_end >= page_start", name="page_range"
        ),
        CheckConstraint(
            "char_start >= 0 AND char_end >= 0", name="offsets_not_negative"
        ),
        # GIN is the index type built for full-text search.
        Index(
            "ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"
        ),
        # HNSW is pgvector's graph index for nearest-neighbour search, here by
        # cosine distance, the measure the BGE models are trained for.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int]
    page_start: Mapped[int]
    char_start: Mapped[int]
    page_end: Mapped[int]
    char_end: Mapped[int]
    heading: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # Indexed: identical text elsewhere gives its embedding (record 17).
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # Computed and stored by Postgres itself from heading and content, so it
    # can never drift from the text. Deferred: loaded only when asked for.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR, persisted=True), deferred=True
    )
    # The content's meaning as a vector, from app/embedding.py, and the model
    # that made it. Empty until computed. An embedding made by a model other
    # than the configured one counts as missing. Deferred, like search_vector:
    # 384 numbers per row are loaded only when asked for.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions), deferred=True
    )
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GeneratedArtifact(Base):
    """Something the language model wrote, kept with what it was written from.

    Four kinds so far (artifact_type): a document's summary (Phase 09), an
    environment's master summary (Phase 10), the concepts extracted from a
    document (Phase 11), and the build of an environment's knowledge graph
    (Phase 12). The environment-wide kinds have no document_id. source_version fingerprints exactly what an artifact
    read: for a document summary, the document's file version and its chunk
    ids in reading order, so it changes exactly when the text changes.
    model_name and prompt_version record what wrote it.

    One row per (document, type, source version, model, prompt version):
    asking again for the same thing finds the existing row instead of writing
    it twice. When any of them changes, a new row is written and the old one
    stays as history, never overwritten (decision record 09).

    status moves pending -> generating -> ready or failed; error says why.
    content holds the finished artifact, citations included in full so an
    old summary stays readable after its passages change; metadata_json
    records how it was made.
    """

    __tablename__ = "generated_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "artifact_type",
            "source_version",
            "model_name",
            "prompt_version",
            name="uq_generated_artifacts_key",
        ),
        CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'failed')", name="status"
        ),
        CheckConstraint(
            "artifact_type IN ('document_summary', 'environment_summary', "
            "'concept_extraction', 'knowledge_graph', 'learning_roadmap', "
            "'practice_set')",
            name="artifact_type",
        ),
        # The key above never matches a row without a document, since NULLs
        # are distinct in a unique constraint, so artifacts about a whole
        # environment get their own key.
        Index(
            "uq_generated_artifacts_environment_key",
            "environment_id",
            "artifact_type",
            "source_version",
            "model_name",
            "prompt_version",
            unique=True,
            postgresql_where=text("document_id IS NULL"),
        ),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    # Empty for artifacts about a whole environment (Phase 10). No index of
    # its own: the unique key starts with it and serves lookups by document.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    artifact_type: Mapped[str] = mapped_column(Text)
    source_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    error: Mapped[str | None] = mapped_column(Text)
    content: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    model_name: Mapped[str] = mapped_column(Text)
    # Every prompt version that wrote it, in order, separated by commas.
    prompt_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )


class Concept(Base):
    """One concept an environment's material teaches, such as "Deadlock".

    Concepts are proposed by the language model and validated by the backend
    (decision record 11). Identity is normalized_name within an environment,
    a deterministic cleaning of the name, so "Threads" in one lecture and
    "Thread" in another are one concept. name, definition and aliases are
    what is shown, taken from the document with the most evidence for it.
    Concept ids stay stable while any document mentions the concept, so the
    knowledge graph (Phase 12) can point at them.
    """

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("environment_id", "normalized_name"),)
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )


class DocumentConcept(Base):
    """A concept as one document presents it: the name, definition and
    aliases that document's extraction gave it."""

    __tablename__ = "document_concepts"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class ConceptEvidence(Base):
    """A passage that explains a concept: the evidence for it. Deleted with the
    chunk, so evidence always points at text that exists."""

    __tablename__ = "concept_evidence"

    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    # Indexed on its own as well: every reprocess deletes chunks, and each
    # deletion cascades here.
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class RelationshipDecision(Base):
    """What the model decided about one candidate pair of concepts, kept so
    the same pair is never asked about twice (decision record 12).

    A pair is two concepts that one of the environment's passages connects,
    found by the backend, never by the model. pair_key fingerprints the pair
    as the model saw it: both normalized names and the content of its
    passages. concept_a and concept_b are in normalized-name order, and
    decision is read in that order.

    A decision outlives its concepts (decision record 17): it belongs to its
    key, not to the concept rows, so deleting a document and adding it again
    finds every decision about its pairs. The concept links are then empty.
    """

    __tablename__ = "relationship_decisions"
    __table_args__ = (
        UniqueConstraint("environment_id", "pair_key", "model_name", "prompt_version"),
        CheckConstraint(
            "decision IN ('a_before_b', 'b_before_a', 'a_part_of_b', 'b_part_of_a', "
            "'related', 'none')",
            name="decision",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE")
    )
    pair_key: Mapped[str] = mapped_column(String(64))
    concept_a_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    concept_b_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConceptRelationship(Base):
    """An edge of the knowledge graph: source PREREQUISITE_OF target (target
    builds on source), source PART_OF target (a part, step or kind of it), or
    RELATED_TO. Derived from the decisions about the environment's current
    candidate pairs, with at most one relationship per pair of concepts in
    either direction, so contradictions and duplicates cannot be stored."""

    __tablename__ = "concept_relationships"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('PREREQUISITE_OF', 'RELATED_TO', 'PART_OF')",
            name="relationship_type",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        CheckConstraint("source_concept_id <> target_concept_id", name="no_self_edge"),
        Index(
            "uq_concept_relationships_pair",
            func.least(text("source_concept_id"), text("target_concept_id")),
            func.greatest(text("source_concept_id"), text("target_concept_id")),
            unique=True,
        ),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    source_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    target_concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RelationshipEvidence(Base):
    """A passage that shows a relationship. Deleted with its chunk."""

    __tablename__ = "relationship_evidence"

    relationship_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concept_relationships.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class LearningItem(Base):
    """A practice item about one concept, written by the model from the
    concept's passages and checked by the backend (decision record 14).

    kind is short_answer, multiple_choice, true_false or flashcard; content
    holds what the learner sees and the key: question and answer;
    question, options and correct (index from 0) with an explanation;
    statement, truth and explanation; front and back. difficulty is effort
    by kind, 1 to 3. evidence_key fingerprints the concept and its passages
    as the model saw them: an item is practised only while it matches the
    concept's current one, and is retired when a new set replaces it, kept
    with its attempts. metadata_json records how it was made: the support
    score of its passages, the generation it came from.
    """

    __tablename__ = "learning_items"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('short_answer', 'multiple_choice', 'true_false', 'flashcard')",
            name="kind",
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty"),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSONB)
    difficulty: Mapped[int] = mapped_column(Integer)
    evidence_key: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningItemSource(Base):
    """A passage a practice item's answer comes from. Deleted with its
    chunk."""

    __tablename__ = "learning_item_sources"

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_items.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )


class Attempt(Base):
    """One answer to a practice item. graded_by is key when the backend
    checked it against the item's stored answer (multiple choice,
    true/false), learner when the learner marked it after seeing the answer
    (short answer, flashcard). response holds what was answered."""

    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint("graded_by IN ('key', 'learner')", name="graded_by"),
        CheckConstraint("seconds IS NULL OR seconds >= 0", name="seconds"),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_items.id", ondelete="CASCADE"), index=True
    )
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response: Mapped[dict] = mapped_column(JSONB)
    correct: Mapped[bool] = mapped_column(Boolean)
    graded_by: Mapped[str] = mapped_column(Text)
    seconds: Mapped[float | None] = mapped_column(Float)


class ReviewSchedule(Base):
    """When a practice item comes back: its Leitner box (0 for a new item,
    then 1 to 5) and the time it is due."""

    __tablename__ = "review_schedule"
    __table_args__ = (CheckConstraint("box BETWEEN 0 AND 5", name="box"),)

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("learning_items.id", ondelete="CASCADE"), primary_key=True
    )
    box: Mapped[int] = mapped_column(Integer)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MaterialUpdate(Base):
    """One change to an environment's material, followed step by step so the
    page can show its progress, and what it changed (decision record 17).

    kind is added, new_version, reprocessed or deleted; filename is kept so
    an update about a deleted document still reads well. steps lists each
    step's name, label, state (waiting, running, done, failed or skipped)
    and a detail; report is what changed, written when the update finishes;
    before is the snapshot of the environment the report compares with.
    """

    __tablename__ = "material_updates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('added', 'new_version', 'reprocessed', 'deleted')", name="kind"
        ),
        CheckConstraint("status IN ('running', 'done', 'failed')", name="status"),
    )
    __mapper_args__: ClassVar[dict[str, Any]] = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    filename: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    before: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    report: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

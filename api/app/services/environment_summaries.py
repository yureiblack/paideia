"""An environment's master summary, kept up to date by itself.

Purpose
-------
The summary of a whole environment is derived state: it is built from the
summaries of its documents, never edited, and rebuilt only when what it is
built from changes. After every document summary finishes and every
deletion, refresh_environment_summary works out what the summary would be
built from now. If that is what the current summary was built from, nothing
happens; otherwise a new one is written and the old one is kept
(decision record 10).

It is built from document summaries rather than passages: a course of twenty
lectures is hundreds of thousands of tokens of text, but its summaries are a
few thousand. Every passage those summaries cite is numbered across the
environment; the model may cite only those numbers, and each is turned back
into the citation the document summary stored. When all the documents' notes
fit one request they are summarized together; otherwise groups of documents
are summarized first and the groups combined.

A summary is only built once no document in the environment is still being
read or summarized, so five documents uploaded together rebuild it once.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import prompting
from app.db import SessionFactory
from app.llm import ONE_AT_A_TIME, LLMError, LLMProvider
from app.models import Document, Environment, GeneratedArtifact
from app.schemas import (
    EnvironmentSummaryRead,
    EnvironmentSummaryState,
    NotIncluded,
    SourceDocument,
    SummaryPoint,
)
from app.services import summaries

logger = logging.getLogger(__name__)

ARTIFACT_TYPE = "environment_summary"
PROMPT = ("environment_summary", "v1")

# How much of the documents' notes one request carries, estimated as for
# document summaries.
NOTES_TOKENS = summaries.SECTION_TOKENS


@dataclass
class Inputs:
    """What the environment's summary would be built from now."""

    included: list[tuple[Document, GeneratedArtifact]] = field(default_factory=list)
    not_included: list[NotIncluded] = field(default_factory=list)
    waiting_for: int = 0  # documents still being read or summarized

    @property
    def source_version(self) -> str:
        """Which documents, and exactly which of their summaries."""
        used = sorted(f"{doc.id}:{summary.id}" for doc, summary in self.included)
        return hashlib.sha256("\n".join(used).encode()).hexdigest()


def gather(session: Session, environment: Environment, llm: LLMProvider) -> Inputs:
    """Every document in the environment, sorted into included, left out
    with a reason, or still on its way."""
    inputs = Inputs()
    documents = session.scalars(
        select(Document)
        .where(Document.environment_id == environment.id)
        .order_by(Document.created_at, Document.id)
    )
    for doc in documents:
        if doc.status in ("uploaded", "processing"):
            inputs.waiting_for += 1
            continue
        if doc.status == "failed":
            reason = f"It could not be read: {doc.error}"
        else:
            summary = summaries.current_summary(session, doc, llm)
            if summary is None:
                reason = "It has not been summarized yet."
            elif summary.status in ("pending", "generating"):
                inputs.waiting_for += 1
                continue
            elif summary.status == "failed":
                reason = f"Its summary failed: {summary.error}"
            else:
                inputs.included.append((doc, summary))
                continue
        inputs.not_included.append(
            NotIncluded(document_id=doc.id, filename=doc.filename, reason=reason)
        )
    return inputs


def _find(session: Session, environment: Environment, source_version: str, model: str):
    return session.scalar(
        select(GeneratedArtifact).where(
            GeneratedArtifact.environment_id == environment.id,
            GeneratedArtifact.document_id.is_(None),
            GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            GeneratedArtifact.source_version == source_version,
            GeneratedArtifact.model_name == model,
            GeneratedArtifact.prompt_version == _prompt_id(),
        )
    )


def _prompt_id() -> str:
    return "/".join(PROMPT)


def request_environment_summary(
    session: Session, environment: Environment, llm: LLMProvider
) -> tuple[GeneratedArtifact | None, bool]:
    """Make sure a summary of the environment's current material exists or is
    coming, if there is material to summarize and none is still on its way.

    Returns the summary's row, or None while documents are still being read
    or summarized or when none can be summarized, and whether it must be
    written now. Same material, model and prompt: the same row, so asking
    again never writes twice. A failed or abandoned one is tried again.
    """
    inputs = gather(session, environment, llm)
    if inputs.waiting_for or not inputs.included:
        return None, False
    version = inputs.source_version
    artifact = _find(session, environment, version, llm.model_name)
    if artifact is None:
        artifact = GeneratedArtifact(
            environment_id=environment.id,
            document_id=None,
            artifact_type=ARTIFACT_TYPE,
            source_version=version,
            model_name=llm.model_name,
            prompt_version=_prompt_id(),
            status="pending",
            metadata_json={
                "based_on": [
                    SourceDocument(
                        document_id=doc.id,
                        filename=doc.filename,
                        document_version=doc.sha256,
                        summary_id=summary.id,
                    ).model_dump(mode="json")
                    for doc, summary in inputs.included
                ]
            },
        )
        session.add(artifact)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()  # another request created it a moment ago
            return _find(session, environment, version, llm.model_name), False
        return artifact, True
    abandoned = (
        artifact.status == "generating"
        and datetime.now(UTC) - artifact.updated_at > summaries.STALE_GENERATING
    )
    if artifact.status == "failed" or abandoned:
        artifact.status, artifact.error = "pending", None
        session.commit()
        return artifact, True
    return artifact, False


@dataclass(frozen=True)
class _Part:
    """One document's notes, or one group's, ready to be put in a prompt."""

    title: str
    overview: str
    points: list[tuple[str, list[int]]]

    def text(self) -> str:
        lines = [self.title, f"Overview: {self.overview}", "Key points:"]
        lines += [f"- {point} [{', '.join(map(str, ns))}]" for point, ns in self.points]
        return "\n".join(lines)

    def numbers(self) -> set[int]:
        return {n for _, ns in self.points for n in ns}


def _compose(
    environment_name: str, parts: list[_Part], llm: LLMProvider
) -> tuple[object, float]:
    """Ask the model for the summary: of all the parts at once if their notes
    fit one request, otherwise of groups of parts first, then of the groups."""

    def ask(chosen: list[_Part]):
        numbers = sorted(set().union(*(p.numbers() for p in chosen)))
        prompt = prompting.render(
            *PROMPT,
            environment=environment_name,
            notes="\n\n".join(p.text() for p in chosen),
            min_points=min(summaries.MIN_POINTS, len(numbers)),
            max_points=summaries.MAX_POINTS,
        )
        return llm.generate_structured(prompt, summaries.answer_schema(numbers))

    groups: list[list[_Part]] = [[]]
    size = 0
    for part in parts:
        tokens = len(part.text()) // summaries.CHARS_PER_TOKEN + 1
        if groups[-1] and size + tokens > NOTES_TOKENS:
            groups.append([])
            size = 0
        groups[-1].append(part)
        size += tokens
    if len(groups) == 1:
        generated = ask(groups[0])
        return generated.value, generated.seconds

    seconds = 0.0
    combined = []
    for i, group in enumerate(groups, start=1):
        generated = ask(group)
        seconds += generated.seconds
        combined.append(
            _Part(
                title=f"Part {i}: {', '.join(p.title for p in group)}",
                overview=generated.value.overview,
                points=[
                    (kp.point, list(kp.sources)) for kp in generated.value.key_points
                ],
            )
        )
    final = ask(combined)
    return final.value, seconds + final.seconds


def write_environment_summary(
    session_factory: SessionFactory, artifact_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Write a pending environment summary. Runs as a background task.

    Shares the one-at-a-time lock with document summaries. Claims the row,
    reads the documents' stored summaries into plain values, lets the model
    work outside any transaction, and stores the result. If the material
    changed while it waited, it is not written: a newer one replaces it.
    """
    with ONE_AT_A_TIME:
        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "pending":
                return
            environment = session.get(Environment, artifact.environment_id)
            inputs = gather(session, environment, llm)
            if (
                inputs.waiting_for
                or inputs.source_version != artifact.source_version
                or llm.model_name != artifact.model_name
            ):
                artifact.status = "failed"
                artifact.error = "The material changed before this summary was written."
                session.commit()
                return
            # Number every cited passage across the environment, once each.
            numbers: dict[str, int] = {}
            citations: list[dict] = []
            parts = []
            for doc, summary in inputs.included:
                points = []
                for kp in summary.content["key_points"]:
                    cited = []
                    for citation in kp["citations"]:
                        key = citation["chunk_id"]
                        if key not in numbers:
                            citations.append(citation)
                            numbers[key] = len(citations)
                        cited.append(numbers[key])
                    points.append((kp["text"], cited))
                parts.append(
                    _Part(
                        title=f"Document: {doc.filename}",
                        overview=summary.content["overview"],
                        points=points,
                    )
                )
            name = environment.name
            artifact.status = "generating"
            session.commit()

        problem, content, seconds = None, None, None
        try:
            answer, seconds = _compose(name, parts, llm)
            content = {
                "overview": answer.overview,
                "key_points": [
                    {
                        "text": kp.point,
                        "citations": [
                            citations[n - 1] for n in dict.fromkeys(kp.sources)
                        ],
                    }
                    for kp in answer.key_points
                ],
            }
        except LLMError as exc:
            problem = str(exc)
        except Exception:
            logger.exception("Writing environment summary %s failed", artifact_id)
            problem = "An unexpected error occurred while writing the summary."

        with session_factory() as session:
            artifact = session.get(GeneratedArtifact, artifact_id, with_for_update=True)
            if artifact is None or artifact.status != "generating":
                return
            if problem is None:
                artifact.status, artifact.content = "ready", content
                artifact.metadata_json = {
                    **artifact.metadata_json,
                    "seconds": round(seconds, 1),
                }
            else:
                artifact.status, artifact.error = "failed", problem
            session.commit()


def refresh_environment_summary(
    session_factory: SessionFactory, environment_id: uuid.UUID, llm: LLMProvider
) -> None:
    """Bring the environment's summary up to date, if anything changed.
    Runs as a background task after document summaries and deletions."""
    with session_factory() as session:
        environment = session.get(Environment, environment_id)
        if environment is None:
            return
        artifact, write_now = request_environment_summary(session, environment, llm)
        artifact_id = artifact.id if artifact else None
    if write_now:
        write_environment_summary(session_factory, artifact_id, llm)


def history(session: Session, environment: Environment) -> list[GeneratedArtifact]:
    """Every summary of the environment, newest first."""
    return list(
        session.scalars(
            select(GeneratedArtifact)
            .where(
                GeneratedArtifact.environment_id == environment.id,
                GeneratedArtifact.artifact_type == ARTIFACT_TYPE,
            )
            .order_by(GeneratedArtifact.created_at.desc(), GeneratedArtifact.id)
        )
    )


def to_read(artifact: GeneratedArtifact, current: bool) -> EnvironmentSummaryRead:
    content = artifact.content or {}
    return EnvironmentSummaryRead(
        id=artifact.id,
        environment_id=artifact.environment_id,
        status=artifact.status,
        error=artifact.error,
        overview=content.get("overview"),
        key_points=[SummaryPoint(**kp) for kp in content.get("key_points", [])],
        model=artifact.model_name,
        prompt_versions=artifact.prompt_version.split(","),
        source_version=artifact.source_version,
        based_on=artifact.metadata_json.get("based_on", []),
        seconds=artifact.metadata_json.get("seconds"),
        current=current,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def state(
    session: Session, environment: Environment, llm: LLMProvider
) -> EnvironmentSummaryState:
    """Where the environment's summary stands, with the newest ready one."""
    inputs = gather(session, environment, llm)
    all_summaries = history(session, environment)
    current = None
    if inputs.included and not inputs.waiting_for:
        current = _find(session, environment, inputs.source_version, llm.model_name)
    newest_ready = next((a for a in all_summaries if a.status == "ready"), None)

    if inputs.waiting_for:
        label = "waiting"
    elif not inputs.included:
        label = "none"
    elif current is None:
        label = "stale"
    elif current.status in ("pending", "generating"):
        label = "updating"
    elif current.status == "failed":
        label = "failed"
    else:
        label = "up_to_date"

    # The current summary when it is ready; otherwise the newest earlier one,
    # shown as out of date while the current one is written.
    shown = (
        current if current is not None and current.status == "ready" else newest_ready
    )
    return EnvironmentSummaryState(
        state=label,
        waiting_for=inputs.waiting_for,
        error=current.error if label == "failed" else None,
        summary=(
            to_read(shown, current=current is not None and shown.id == current.id)
            if shown
            else None
        ),
        not_included=inputs.not_included,
        earlier_versions=sum(
            1 for a in all_summaries if a.status == "ready" and a is not shown
        ),
    )

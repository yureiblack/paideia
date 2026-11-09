"""Document summaries: the current one, a request for one, and the history.

Purpose
-------
    GET  /api/documents/{document_id}/summary     the current summary
    POST /api/documents/{document_id}/summary     make sure one exists
    GET  /api/documents/{document_id}/summaries   every summary, newest first

Summaries are written in the background, as soon as a document is read and
whenever one is requested. Asking for the same summary twice never writes it
twice: POST answers 200 with a summary that is ready, 202 with one that is
waiting or being written, and starts writing one that is missing or failed.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from app.db import SessionDep, SessionFactoryDep
from app.routers.deps import LLMDep
from app.routers.documents import DocumentDep
from app.schemas import CurrentSummaryRead, SummaryRead
from app.services import environment_summaries as environment_summary_service
from app.services import summaries as service

router = APIRouter(tags=["summaries"])


def _current(session, document, artifact) -> CurrentSummaryRead:
    return CurrentSummaryRead(
        **service.to_read(artifact, current=True).model_dump(),
        earlier_versions=len(service.history(session, document)) - 1,
    )


@router.get("/documents/{document_id}/summary", response_model=CurrentSummaryRead)
def read_summary(
    document: DocumentDep, session: SessionDep, llm: LLMDep
) -> CurrentSummaryRead:
    artifact = service.current_summary(session, document, llm)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No summary yet.")
    return _current(session, document, artifact)


@router.post(
    "/documents/{document_id}/summary",
    response_model=CurrentSummaryRead,
    responses={202: {"description": "Waiting or being written"}},
)
def request_summary(
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    background: BackgroundTasks,
    response: Response,
) -> CurrentSummaryRead:
    try:
        artifact, write_now = service.request_summary(session, document, llm)
    except service.NotReadyToSummarize as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if artifact.status == "failed":
        # Still failed after asking again: this document cannot be summarized.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=artifact.error
        )
    body = _current(session, document, artifact)
    # End this request's read before the background task starts. The session
    # stays open until the task has finished, and an open transaction would
    # sit idle on its connection for as long as the summary takes to write.
    session.commit()
    if write_now:
        background.add_task(service.write_summary, session_factory, artifact.id, llm)
        # A new document summary may change the environment's summary.
        background.add_task(
            environment_summary_service.refresh_environment_summary,
            session_factory,
            document.environment_id,
            llm,
        )
    if artifact.status != "ready":
        response.status_code = status.HTTP_202_ACCEPTED
    return body


@router.get("/documents/{document_id}/summaries", response_model=list[SummaryRead])
def read_summaries(
    document: DocumentDep, session: SessionDep, llm: LLMDep
) -> list[SummaryRead]:
    current = service.current_summary(session, document, llm)
    current_id = current.id if current else None
    return [
        service.to_read(artifact, current=artifact.id == current_id)
        for artifact in service.history(session, document)
    ]

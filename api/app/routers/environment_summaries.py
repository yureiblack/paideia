"""An environment's master summary: where it stands, a request, the history.

Purpose
-------
    GET  /api/environments/{environment_id}/summary     state and newest summary
    POST /api/environments/{environment_id}/summary     bring it up to date
    GET  /api/environments/{environment_id}/summaries   every one, newest first

The summary keeps itself up to date: it is checked after every document
summary and every deletion. POST asks for the same thing by hand, for
example to try again after a failure; it never writes twice for the same
material, and does nothing while documents are still being read or
summarized.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from app.db import SessionDep, SessionFactoryDep
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.schemas import EnvironmentSummaryRead, EnvironmentSummaryState
from app.services import environment_summaries as service

router = APIRouter(tags=["environment summaries"])


@router.get(
    "/environments/{environment_id}/summary", response_model=EnvironmentSummaryState
)
def read_environment_summary(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> EnvironmentSummaryState:
    return service.state(session, environment, llm)


@router.post(
    "/environments/{environment_id}/summary",
    response_model=EnvironmentSummaryState,
    responses={202: {"description": "Being written, or waiting for documents"}},
)
def request_environment_summary(
    environment: EnvironmentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    background: BackgroundTasks,
    response: Response,
) -> EnvironmentSummaryState:
    artifact, write_now = service.request_environment_summary(session, environment, llm)
    body = service.state(session, environment, llm)
    if artifact is None and body.state == "none":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="There is no summarized material to build a summary from yet.",
        )
    # End this request's read before the background task starts (record 09).
    session.commit()
    if write_now:
        background.add_task(
            service.write_environment_summary, session_factory, artifact.id, llm
        )
    if body.state != "up_to_date":
        response.status_code = status.HTTP_202_ACCEPTED
    return body


@router.get(
    "/environments/{environment_id}/summaries",
    response_model=list[EnvironmentSummaryRead],
)
def read_environment_summaries(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> list[EnvironmentSummaryRead]:
    shown = service.state(session, environment, llm).summary
    current_id = shown.id if shown is not None and shown.current else None
    return [
        service.to_read(artifact, current=artifact.id == current_id)
        for artifact in service.history(session, environment)
    ]

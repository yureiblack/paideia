"""Practice: preparing items, sessions, and answers.

Purpose
-------
    GET  /api/environments/{environment_id}/practice           what is due,
                                                               and each
                                                               concept's state
    POST /api/environments/{environment_id}/practice           prepare items
                                                               for concepts
    POST /api/concepts/{concept_id}/practice                   prepare one
    GET  /api/environments/{environment_id}/practice/session   a session:
                                                               due items, or a
                                                               stage's
                                                               (?concept_id=)
    POST /api/learning-items/{item_id}/attempts                answer one

Items are written in the background, one concept at a time, and never twice
for the same passages, model and prompt. Evidence-informed study support:
answering from memory, coming back at growing intervals, concepts mixed.
"""

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from app.db import SessionDep, SessionFactoryDep
from app.models import Environment, LearningItem
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.routers.graph import ConceptDep
from app.routers.search import RerankerDep
from app.schemas import (
    AttemptCreate,
    AttemptResult,
    PracticeItem,
    PracticeOverview,
    PrepareRequest,
)
from app.services import practice as service

router = APIRouter(tags=["practice"])


def item_or_404(item_id: uuid.UUID, session: SessionDep) -> LearningItem:
    item = session.get(LearningItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Practice item not found")
    return item


ItemDep = Annotated[LearningItem, Depends(item_or_404)]


@router.get("/environments/{environment_id}/practice", response_model=PracticeOverview)
def read_practice(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> PracticeOverview:
    return service.overview(session, environment, llm)


def _prepare(
    environment,
    concept_ids,
    session,
    session_factory,
    llm,
    reranker,
    background,
    response,
) -> PracticeOverview:
    pending = service.prepare(session, environment, concept_ids, llm)
    body = service.overview(session, environment, llm)
    session.commit()  # end this read before the background task (record 09)
    if pending:
        background.add_task(service.write_all, session_factory, pending, llm, reranker)
        response.status_code = status.HTTP_202_ACCEPTED
    return body


@router.post(
    "/environments/{environment_id}/practice",
    response_model=PracticeOverview,
    responses={202: {"description": "Items are being written"}},
)
def prepare_practice(
    data: PrepareRequest,
    environment: EnvironmentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    reranker: RerankerDep,
    background: BackgroundTasks,
    response: Response,
) -> PracticeOverview:
    return _prepare(
        environment,
        data.concept_ids,
        session,
        session_factory,
        llm,
        reranker,
        background,
        response,
    )


@router.post(
    "/concepts/{concept_id}/practice",
    response_model=PracticeOverview,
    responses={202: {"description": "Items are being written"}},
)
def prepare_concept_practice(
    concept: ConceptDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    reranker: RerankerDep,
    background: BackgroundTasks,
    response: Response,
) -> PracticeOverview:
    environment = session.get(Environment, concept.environment_id)
    return _prepare(
        environment,
        [concept.id],
        session,
        session_factory,
        llm,
        reranker,
        background,
        response,
    )


@router.get(
    "/environments/{environment_id}/practice/session",
    response_model=list[PracticeItem],
)
def read_session(
    environment: EnvironmentDep,
    session: SessionDep,
    concept_id: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> list[PracticeItem]:
    return service.session_items(session, environment, concept_id)


@router.post("/learning-items/{item_id}/attempts", response_model=AttemptResult)
def answer_item(
    item: ItemDep, data: AttemptCreate, session: SessionDep
) -> AttemptResult:
    try:
        return service.answer(session, item, data)
    except service.NotPractised as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

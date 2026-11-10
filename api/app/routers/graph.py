"""The knowledge graph: an environment's, and one concept's neighbourhood.

Purpose
-------
    GET  /api/environments/{environment_id}/graph    every concept and
                                                     relationship, and where
                                                     the build stands
    POST /api/environments/{environment_id}/graph    bring it up to date (or
                                                     try again)
    GET  /api/concepts/{concept_id}/neighbourhood    what a concept builds
                                                     on, what builds on it,
                                                     its parts and relations

The graph keeps itself up to date: it is checked after every concept
extraction and every deletion. POST asks for the same by hand; it never asks
the model twice about the same pair, and does nothing while documents are
still being read or their concepts extracted.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from app.db import SessionDep, SessionFactoryDep
from app.models import Concept
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.schemas import GraphState, Neighbourhood
from app.services import graph as service

router = APIRouter(tags=["knowledge graph"])


def concept_or_404(concept_id: uuid.UUID, session: SessionDep) -> Concept:
    concept = session.get(Concept, concept_id)
    if concept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Concept not found")
    return concept


ConceptDep = Annotated[Concept, Depends(concept_or_404)]


@router.get("/environments/{environment_id}/graph", response_model=GraphState)
def read_graph(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> GraphState:
    return service.state(session, environment, llm)


@router.post(
    "/environments/{environment_id}/graph",
    response_model=GraphState,
    responses={202: {"description": "Being built, or waiting for documents"}},
)
def request_graph(
    environment: EnvironmentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    background: BackgroundTasks,
    response: Response,
) -> GraphState:
    artifact, write_now = service.request_graph(session, environment, llm)
    body = service.state(session, environment, llm)
    if artifact is None and body.state == "none":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="There are no connected concepts to build a graph from yet.",
        )
    session.commit()  # end this read before the background task (record 09)
    if write_now:
        background.add_task(service.write_graph, session_factory, artifact.id, llm)
    if body.state != "up_to_date":
        response.status_code = status.HTTP_202_ACCEPTED
    return body


@router.get("/concepts/{concept_id}/neighbourhood", response_model=Neighbourhood)
def read_neighbourhood(concept: ConceptDep, session: SessionDep) -> Neighbourhood:
    return service.neighbourhood(session, concept)

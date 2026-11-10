"""The learning roadmap: an environment's concepts as an ordered path.

Purpose
-------
    GET  /api/environments/{environment_id}/roadmap    the stages in order,
                                                       their concepts and
                                                       sources, and where
                                                       the titles stand
    POST /api/environments/{environment_id}/roadmap    write the titles of
                                                       the current stages
                                                       (or try again)

The stages and their order always follow the current concepts and graph.
The titles keep themselves up to date: they are checked after every graph
build. POST asks for the same by hand; it never asks the model twice about
the same stage, and does nothing while the graph is still on its way.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from app.db import SessionDep, SessionFactoryDep
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.schemas import RoadmapState
from app.services import roadmap as service

router = APIRouter(tags=["learning roadmap"])


@router.get("/environments/{environment_id}/roadmap", response_model=RoadmapState)
def read_roadmap(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> RoadmapState:
    return service.state(session, environment, llm)


@router.post(
    "/environments/{environment_id}/roadmap",
    response_model=RoadmapState,
    responses={202: {"description": "Being written, or waiting for the graph"}},
)
def request_roadmap(
    environment: EnvironmentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    background: BackgroundTasks,
    response: Response,
) -> RoadmapState:
    artifact, write_now = service.request_roadmap(session, environment, llm)
    body = service.state(session, environment, llm)
    if artifact is None and body.state == "none":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="There are no concepts to build a roadmap from yet.",
        )
    session.commit()  # end this read before the background task (record 09)
    if write_now:
        background.add_task(service.write_roadmap, session_factory, artifact.id, llm)
    if body.state != "up_to_date":
        response.status_code = status.HTTP_202_ACCEPTED
    return body

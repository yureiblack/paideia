"""HTTP endpoints for learning environments, mounted under /api/environments.

Purpose
-------
Translate HTTP into service calls and back. Validation of request bodies
happens before these functions run, through the schemas in app/schemas.py.
Turning "no such environment" into a 404 happens once, in environment_or_404,
rather than in every endpoint that takes an id.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.models import Environment
from app.schemas import EnvironmentCreate, EnvironmentRead, EnvironmentUpdate
from app.services import environments as service

router = APIRouter(prefix="/environments", tags=["environments"])


def environment_or_404(environment_id: uuid.UUID, session: SessionDep) -> Environment:
    """Load the environment named in the URL, or stop the request with a 404.

    A malformed id, one that is not a UUID at all, never reaches this function:
    FastAPI rejects it with a 422 because of the uuid.UUID type above.
    """
    environment = service.get_environment(session, environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Environment not found")
    return environment


# An endpoint parameter of this type receives the loaded Environment. FastAPI
# reuses one Session per request, so this and the endpoint share it.
EnvironmentDep = Annotated[Environment, Depends(environment_or_404)]


@router.get("", response_model=list[EnvironmentRead])
def list_environments(session: SessionDep) -> list[Environment]:
    return service.list_environments(session)


@router.post("", response_model=EnvironmentRead, status_code=status.HTTP_201_CREATED)
def create_environment(data: EnvironmentCreate, session: SessionDep) -> Environment:
    return service.create_environment(session, data)


@router.get("/{environment_id}", response_model=EnvironmentRead)
def read_environment(environment: EnvironmentDep) -> Environment:
    return environment


@router.patch("/{environment_id}", response_model=EnvironmentRead)
def update_environment(
    data: EnvironmentUpdate, environment: EnvironmentDep, session: SessionDep
) -> Environment:
    return service.update_environment(session, environment, data)


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(environment: EnvironmentDep, session: SessionDep) -> None:
    service.delete_environment(session, environment)

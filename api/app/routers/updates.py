"""Update records: what each change to an environment's material did.

Purpose
-------
    GET /api/environments/{environment_id}/updates   newest first
    GET /api/updates/{update_id}                      one, with its steps
                                                      and report

Every document added, new version, reprocess or deletion has one, written as
its steps run (decision record 17), so the page can follow it and then show
what changed.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.db import SessionDep
from app.models import MaterialUpdate
from app.routers.environments import EnvironmentDep
from app.schemas import MaterialUpdateRead
from app.services import updates as service

router = APIRouter(tags=["updates"])


@router.get(
    "/environments/{environment_id}/updates", response_model=list[MaterialUpdateRead]
)
def read_updates(
    environment: EnvironmentDep, session: SessionDep
) -> list[MaterialUpdateRead]:
    return [service.to_read(u) for u in service.recent(session, environment.id)]


@router.get("/updates/{update_id}", response_model=MaterialUpdateRead)
def read_update(update_id: uuid.UUID, session: SessionDep) -> MaterialUpdateRead:
    update = session.get(MaterialUpdate, update_id)
    if update is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Update not found")
    return service.to_read(update)

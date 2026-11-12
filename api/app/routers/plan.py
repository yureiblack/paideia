"""Today's study plan.

Purpose
-------
    GET /api/environments/{environment_id}/plan?until=...&minutes=...

Worked out afresh by fixed rules from the learner's state, the roadmap and
the material (decision record 16). until is the end of the learner's day,
with its time zone; minutes is an optional time budget.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.db import SessionDep
from app.routers.deps import LLMDep
from app.routers.environments import EnvironmentDep
from app.routers.practice import UntilQuery, aware_until
from app.schemas import StudyPlan
from app.services import planner as service

router = APIRouter(tags=["study plan"])


@router.get("/environments/{environment_id}/plan", response_model=StudyPlan)
def read_plan(
    environment: EnvironmentDep,
    session: SessionDep,
    llm: LLMDep,
    until: UntilQuery = None,
    minutes: Annotated[
        int | None, Query(ge=5, le=600, description="A time budget, in minutes")
    ] = None,
) -> StudyPlan:
    return service.plan(
        session, environment, llm, until=aware_until(until), budget=minutes
    )

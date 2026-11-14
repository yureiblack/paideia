"""Background jobs: what the worker is doing, and cancelling.

Purpose
-------
    GET  /api/environments/{environment_id}/jobs   queued and running first,
                                                   then the latest finished
    GET  /api/jobs/{job_id}                        one, with its progress
    POST /api/jobs/{job_id}/cancel                 a queued job at once, a
                                                   running one before its
                                                   next step

Jobs are queued by the requests that ask for work, and run by the worker
process (decision record 18).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import SessionDep
from app.models import Job
from app.routers.environments import EnvironmentDep
from app.schemas import JobRead
from app.services import jobs as service

router = APIRouter(tags=["jobs"])


def job_or_404(job_id: uuid.UUID, session: SessionDep) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


JobDep = Annotated[Job, Depends(job_or_404)]


@router.get("/environments/{environment_id}/jobs", response_model=list[JobRead])
def read_jobs(environment: EnvironmentDep, session: SessionDep) -> list[JobRead]:
    return [service.to_read(job) for job in service.recent(session, environment.id)]


@router.get("/jobs/{job_id}", response_model=JobRead)
def read_job(job: JobDep) -> JobRead:
    return service.to_read(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobRead)
def cancel_job(job: JobDep, session: SessionDep) -> JobRead:
    return service.to_read(service.cancel(session, job))

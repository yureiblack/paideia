"""The five operations on learning environments.

Purpose
-------
The rules for environments live here, between the HTTP layer and the database.
Nothing in this module knows about requests, status codes or JSON, so the same
functions can be called from an endpoint, a test, or a future background job.

Each function receives the Session to work in. Changes are committed here, so a
caller never has to remember to.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Environment
from app.schemas import EnvironmentCreate, EnvironmentUpdate


def list_environments(session: Session) -> list[Environment]:
    """Every environment, newest first.

    The id breaks ties between environments created in the same instant, so
    the order is stable from one request to the next.
    """
    query = select(Environment).order_by(Environment.created_at.desc(), Environment.id)
    return list(session.scalars(query))


def get_environment(session: Session, environment_id: uuid.UUID) -> Environment | None:
    """One environment, or None when no environment has that id."""
    return session.get(Environment, environment_id)


def create_environment(session: Session, data: EnvironmentCreate) -> Environment:
    """Store a new environment. The database fills in id and timestamps."""
    environment = Environment(**data.model_dump())
    session.add(environment)
    session.commit()
    return environment


def update_environment(
    session: Session, environment: Environment, data: EnvironmentUpdate
) -> Environment:
    """Change only the fields the client actually sent.

    exclude_unset leaves out fields that were absent from the request, which is
    what makes PATCH partial: sending only a description keeps the name.
    """
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(environment, field, value)
    session.commit()
    return environment


def delete_environment(session: Session, environment: Environment) -> None:
    """Remove an environment for good."""
    session.delete(environment)
    session.commit()

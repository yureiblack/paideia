"""Tests for app/services/environments.py, called directly with no HTTP.

Purpose: prove each of the five operations does what it says, including what
it must leave alone. Every test runs in a rolled-back transaction, so each one
starts with an empty environments table.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Environment
from app.schemas import EnvironmentCreate, EnvironmentUpdate
from app.services import environments as service


def test_create_lets_the_database_fill_in_id_and_timestamps(session: Session):
    environment = service.create_environment(
        session, EnvironmentCreate(name="Operating Systems")
    )

    assert isinstance(environment.id, uuid.UUID)
    assert environment.name == "Operating Systems"
    assert environment.description is None
    assert environment.created_at is not None
    assert environment.updated_at == environment.created_at


def test_list_returns_newest_first(session: Session):
    # Postgres's now() is frozen for the whole test transaction, so rows created
    # here would share one created_at. Explicit times make the order observable.
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for offset, name in enumerate(["Oldest", "Middle", "Newest"]):
        session.add(Environment(name=name, created_at=start + timedelta(days=offset)))
    session.commit()

    names = [environment.name for environment in service.list_environments(session)]

    assert names == ["Newest", "Middle", "Oldest"]


def test_get_returns_none_for_an_unknown_id(session: Session):
    assert service.get_environment(session, uuid.uuid4()) is None


def test_update_changes_only_the_fields_sent(session: Session):
    environment = service.create_environment(
        session, EnvironmentCreate(name="Economics", description="Micro and macro")
    )

    service.update_environment(
        session, environment, EnvironmentUpdate(name="Economics I")
    )

    assert environment.name == "Economics I"
    assert environment.description == "Micro and macro"


def test_update_moves_updated_at_but_not_created_at(session: Session):
    environment = service.create_environment(
        session, EnvironmentCreate(name="Economics")
    )
    created_at, first_update = environment.created_at, environment.updated_at

    service.update_environment(
        session, environment, EnvironmentUpdate(description="Now described")
    )

    assert environment.updated_at > first_update
    assert environment.created_at == created_at


def test_update_can_clear_the_description(session: Session):
    environment = service.create_environment(
        session, EnvironmentCreate(name="Economics", description="Micro and macro")
    )

    service.update_environment(
        session, environment, EnvironmentUpdate(description=None)
    )

    assert environment.description is None


def test_delete_removes_only_that_environment(session: Session):
    kept = service.create_environment(session, EnvironmentCreate(name="Keep me"))
    doomed = service.create_environment(session, EnvironmentCreate(name="Delete me"))

    service.delete_environment(session, doomed)

    assert service.get_environment(session, doomed.id) is None
    assert service.get_environment(session, kept.id) is not None

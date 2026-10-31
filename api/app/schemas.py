"""API schemas: the shape of data travelling over HTTP.

Purpose
-------
Models (app/models.py) describe stored tables. Schemas describe what a client
may send and what the API sends back. Keeping them separate means the API can
refuse fields a client must never set, such as id or created_at, and can change
its public shape without touching the table.

FastAPI validates every request body against these classes before an endpoint
runs, and answers 422 with a readable list of problems when one does not fit.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

NAME_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 2000

# Surrounding spaces are trimmed before the length rules apply, so "   " is not
# a valid name.
Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH),
]
Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH),
]


def _blank_to_none(value: str | None) -> str | None:
    """An empty description means "no description", stored as NULL."""
    return value or None


class EnvironmentCreate(BaseModel):
    """Body of POST /api/environments."""

    # Unknown fields are an error rather than silently ignored, so a client
    # sending "id" or a misspelt "nmae" finds out immediately.
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description | None = None

    _description = field_validator("description")(_blank_to_none)


class EnvironmentUpdate(BaseModel):
    """Body of PATCH /api/environments/{id}.

    Every field is optional and only the fields actually sent are changed.
    Sending "description": null clears the description. Sending "name": null
    is refused, because every environment needs a name.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    description: Description | None = None

    @field_validator("name")
    @classmethod
    def name_cannot_be_cleared(cls, value: str | None) -> str:
        # Validators do not run for fields left out of the request, so this
        # only fires when a client explicitly sends "name": null.
        if value is None:
            raise ValueError("name cannot be null")
        return value

    _description = field_validator("description")(_blank_to_none)


class EnvironmentRead(BaseModel):
    """What the API returns for an environment."""

    # Lets FastAPI build this from an Environment model object directly.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

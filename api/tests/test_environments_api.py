"""Tests for the /api/environments endpoints in app/routers/environments.py.

Purpose: prove the HTTP contract a frontend relies on: status codes, response
bodies, partial updates, and clean 404 and 422 errors. Requests run through the
real app and service against the test database, rolled back after each test.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.schemas import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH

URL = "/api/environments"


def create(client: TestClient, **body) -> dict:
    response = client.post(URL, json={"name": "Operating Systems", **body})
    assert response.status_code == 201, response.text
    return response.json()


# --- create -----------------------------------------------------------------


def test_create_returns_201_and_the_new_environment(client: TestClient):
    response = client.post(
        URL, json={"name": "  Operating Systems  ", "description": "Processes"}
    )

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert body["name"] == "Operating Systems"
    assert body["description"] == "Processes"
    assert body["created_at"] == body["updated_at"]


def test_create_stores_a_blank_description_as_null(client: TestClient):
    assert create(client, description="   ")["description"] is None


def test_create_accepts_a_name_at_the_length_limit(client: TestClient):
    assert create(client, name="x" * NAME_MAX_LENGTH)["name"] == "x" * NAME_MAX_LENGTH


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="missing name"),
        pytest.param({"name": ""}, id="empty name"),
        pytest.param({"name": "   "}, id="whitespace-only name"),
        pytest.param({"name": None}, id="null name"),
        pytest.param({"name": 42}, id="name not a string"),
        pytest.param({"name": "x" * (NAME_MAX_LENGTH + 1)}, id="name too long"),
        pytest.param(
            {"name": "Ok", "description": "x" * (DESCRIPTION_MAX_LENGTH + 1)},
            id="description too long",
        ),
        pytest.param({"name": "Ok", "id": str(uuid.uuid4())}, id="client-chosen id"),
        pytest.param({"name": "Ok", "nmae": "typo"}, id="unknown field"),
    ],
)
def test_create_rejects_invalid_bodies_with_422(client: TestClient, body: dict):
    response = client.post(URL, json=body)

    assert response.status_code == 422
    # FastAPI's error format: a list of problems, each naming where it is.
    assert response.json()["detail"][0]["loc"][0] == "body"


# --- read -------------------------------------------------------------------


def test_list_is_empty_to_begin_with(client: TestClient):
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_every_environment(client: TestClient):
    created = {create(client, name=name)["id"] for name in ["A", "B", "C"]}

    listed = {environment["id"] for environment in client.get(URL).json()}

    assert listed == created


def test_get_returns_the_environment(client: TestClient):
    environment = create(client)

    response = client.get(f"{URL}/{environment['id']}")

    assert response.status_code == 200
    assert response.json() == environment


def test_get_unknown_id_is_404(client: TestClient):
    response = client.get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Environment not found"}


def test_get_malformed_id_is_422(client: TestClient):
    assert client.get(f"{URL}/not-a-uuid").status_code == 422


# --- update -----------------------------------------------------------------


def test_patch_changes_only_the_fields_sent(client: TestClient):
    environment = create(client, description="Processes")

    response = client.patch(f"{URL}/{environment['id']}", json={"name": "OS"})

    assert response.status_code == 200
    assert response.json()["name"] == "OS"
    assert response.json()["description"] == "Processes"


def test_patch_moves_updated_at(client: TestClient):
    environment = create(client)

    updated = client.patch(
        f"{URL}/{environment['id']}", json={"description": "Now described"}
    ).json()

    assert updated["updated_at"] > environment["updated_at"]
    assert updated["created_at"] == environment["created_at"]


def test_patch_with_null_description_clears_it(client: TestClient):
    environment = create(client, description="Processes")

    response = client.patch(f"{URL}/{environment['id']}", json={"description": None})

    assert response.json()["description"] is None


def test_patch_with_empty_body_changes_nothing(client: TestClient):
    environment = create(client)

    response = client.patch(f"{URL}/{environment['id']}", json={})

    assert response.status_code == 200
    assert response.json() == environment


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": None}, id="null name"),
        pytest.param({"name": "   "}, id="blank name"),
        pytest.param({"name": "x" * (NAME_MAX_LENGTH + 1)}, id="name too long"),
        pytest.param({"created_at": "2026-01-01T00:00:00Z"}, id="read-only field"),
    ],
)
def test_patch_rejects_invalid_bodies_with_422(client: TestClient, body: dict):
    environment = create(client)

    response = client.patch(f"{URL}/{environment['id']}", json=body)

    assert response.status_code == 422
    assert client.get(f"{URL}/{environment['id']}").json() == environment


def test_patch_unknown_id_is_404(client: TestClient):
    assert client.patch(f"{URL}/{uuid.uuid4()}", json={"name": "X"}).status_code == 404


# --- delete -----------------------------------------------------------------


def test_delete_returns_204_and_the_environment_is_gone(client: TestClient):
    environment = create(client)

    response = client.delete(f"{URL}/{environment['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{URL}/{environment['id']}").status_code == 404


def test_delete_unknown_id_is_404(client: TestClient):
    assert client.delete(f"{URL}/{uuid.uuid4()}").status_code == 404


def test_deleting_one_environment_leaves_the_others_untouched(client: TestClient):
    # Acceptance criterion: deleting an environment removes only its data.
    kept = create(client, name="Operating Systems", description="Processes")
    doomed = create(client, name="Economics")

    client.delete(f"{URL}/{doomed['id']}")

    assert client.get(f"{URL}/{kept['id']}").json() == kept
    assert [environment["id"] for environment in client.get(URL).json()] == [kept["id"]]

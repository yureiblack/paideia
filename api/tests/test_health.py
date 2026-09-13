"""Tests for the health endpoints in app/main.py.

Purpose: prove the API starts, answers, and can reach the database. These run
against the real Postgres container, so `docker compose up -d` must be running.
"""

from fastapi.testclient import TestClient

from app.main import app

# Calls the app directly in-process. No server, no port, no network. Each
# client.get() below runs the exact same code a real HTTP request would.
client = TestClient(app)


def test_health_reports_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_reports_ok_with_pgvector():
    response = client.get("/health/db")

    assert response.status_code == 200, "got 503: is docker compose up?"
    body = response.json()
    assert body["status"] == "ok"
    assert body["pgvector_available"] is True

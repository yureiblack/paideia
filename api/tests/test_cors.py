"""Tests for CORS: the setting in app/config.py and its effect in app/main.py.

Purpose: prove that allowed browser origins come from configuration, that an
allowed origin is echoed back, and that an unknown origin gets nothing.
"""

from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app

client = TestClient(app)


def test_configured_origin_is_allowed():
    origin = settings.cors_origin_list[0]

    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_is_not_allowed():
    response = client.get("/health", headers={"Origin": "http://unknown.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_are_split_and_trimmed():
    custom = Settings(
        database_url="postgresql+psycopg://unused",
        cors_origins=" http://a.test , http://b.test ,",
    )

    assert custom.cors_origin_list == ["http://a.test", "http://b.test"]

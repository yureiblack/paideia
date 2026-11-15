"""Tests for app/logs.py and app/correlation.py (decision record 21).

Purpose: every request gets an id, kept from the caller when it looks like
one; the id comes back in a header and in every error body, and is on every
log line written for the request and on every job it queues, whose own log
lines carry it with the job and update ids. Log lines are JSON objects whose
extra values are fields of their own. An error nothing else handled becomes
a 500 with a short message and the id, never a traceback.
"""

import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import context, logs
from app.db import get_session
from app.main import app
from app.models import Job
from app.services import jobs
from tests import pdfs
from tests.test_documents_api import new_environment


def record(message="Something happened", **extra) -> logging.LogRecord:
    rec = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(rec, key, value)
    return rec


def test_a_json_line_has_the_ids_and_the_extra_values_as_fields():
    token = context.request_id.set("req-1")
    job = context.job_id.set("job-1")
    try:
        line = json.loads(logs.JsonFormatter().format(record(status=201, ms=12.5)))
    finally:
        context.job_id.reset(job)
        context.request_id.reset(token)

    assert line["message"] == "Something happened"
    assert (line["level"], line["logger"]) == ("info", "app.test")
    assert (line["request_id"], line["job_id"]) == ("req-1", "job-1")
    assert (line["status"], line["ms"]) == (201, 12.5)
    assert "update_id" not in line  # not set, so not written
    assert line["time"].endswith("+00:00")


def test_an_exception_is_written_whole_under_error():
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.LogRecord(
            "app.test",
            logging.ERROR,
            __file__,
            1,
            "Failed",
            (),
            sys.exc_info(),
        )

    line = json.loads(logs.JsonFormatter().format(rec))

    assert "ValueError: boom" in line["error"]


def test_a_text_line_reads_plainly_with_its_ids():
    token = context.request_id.set("req-2")
    try:
        line = logs.TextFormatter().format(record("Saved", path="/x"))
    finally:
        context.request_id.reset(token)

    assert "INFO    app.test: Saved  [request_id=req-2 path=/x]" in line


def test_configure_sends_everything_through_one_handler():
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        logs.configure()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, logs.JsonFormatter)
        assert logging.getLogger("uvicorn.access").disabled
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
        logging.getLogger("uvicorn.access").disabled = False


def test_every_response_has_a_request_id_and_a_good_one_is_kept(client: TestClient):
    made = client.get("/health")
    kept = client.get("/health", headers={"X-Request-ID": "upload-7.retry_2"})
    bad = client.get("/health", headers={"X-Request-ID": "has spaces; and more"})
    long = client.get("/health", headers={"X-Request-ID": "x" * 65})

    assert len(made.headers["X-Request-ID"]) == 32
    assert kept.headers["X-Request-ID"] == "upload-7.retry_2"
    assert bad.headers["X-Request-ID"] != "has spaces; and more"
    assert long.headers["X-Request-ID"] != "x" * 65


def test_error_bodies_carry_the_request_id(client: TestClient):
    missing = client.get(
        "/api/environments/00000000-0000-0000-0000-000000000000",
        headers={"X-Request-ID": "look-404"},
    )
    invalid = client.get("/api/environments/not-a-uuid")

    assert missing.status_code == 404
    assert missing.json() == {
        "detail": "Environment not found",
        "request_id": "look-404",
    }
    assert invalid.status_code == 422
    assert invalid.json()["request_id"] == invalid.headers["X-Request-ID"]
    assert isinstance(invalid.json()["detail"], list)


def test_an_unexpected_error_is_a_500_with_the_id_and_no_traceback(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    def broken():
        raise RuntimeError("the database fell over")

    app.dependency_overrides[get_session] = broken

    with caplog.at_level(logging.INFO, logger="app.requests"):
        response = client.get("/api/environments", headers={"X-Request-ID": "oops-1"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Something went wrong on the server.",
        "request_id": "oops-1",
    }
    assert "fell over" not in response.text
    logged = [r for r in caplog.records if r.name == "app.requests"]
    assert logged[0].levelno == logging.ERROR and "fell over" in logged[0].exc_text
    assert logged[-1].status == 500


def test_each_request_is_one_log_line_and_health_checks_are_quiet(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.DEBUG, logger="app.requests"):
        client.get("/api/environments")
        client.get("/health")

    lines = [r for r in caplog.records if r.name == "app.requests"]
    assert [(r.levelno, r.method, r.path, r.status) for r in lines] == [
        (logging.INFO, "GET", "/api/environments", 200),
        (logging.DEBUG, "GET", "/health", 200),
    ]
    assert all(r.ms >= 0 for r in lines)


def test_the_page_may_read_the_request_id_across_origins(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_a_job_records_the_request_that_queued_it_and_logs_with_its_ids(
    client: TestClient, session: Session, caplog: pytest.LogCaptureFixture
):
    env = new_environment(client)
    seen = []
    original = jobs.STEPS["process_document"]

    def watching(tools, args):
        seen.append((context.request_id.get(), context.job_id.get()))
        return original(tools, args)

    jobs.STEPS["process_document"] = watching
    try:
        with caplog.at_level(logging.INFO, logger="app.services.jobs"):
            response = client.post(
                f"/api/environments/{env}/documents",
                params={"filename": "lecture.pdf"},
                content=pdfs.pdf("Threads."),
                headers={"Content-Type": "application/pdf", "X-Request-ID": "upload-1"},
            )
    finally:
        jobs.STEPS["process_document"] = original

    assert response.status_code == 201
    queued = session.scalars(select(Job).where(Job.environment_id == env)).all()
    assert {j.request_id for j in queued} == {"upload-1"}
    reading = next(j for j in queued if j.kind == "read")
    assert seen == [("upload-1", str(reading.id))]
    started = [r for r in caplog.records if r.getMessage().startswith("Job started")]
    assert {r.title for r in started} >= {"Reading lecture.pdf"}

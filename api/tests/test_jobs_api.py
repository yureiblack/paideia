"""Tests for jobs through the API, run in-process (no worker, no Redis).

Purpose: every request that asks for work queues a job: an upload a reading
job and, after it, the job deriving everything from the document, both
linked to its update; preparing practice one job with a step per concept.
Jobs end succeeded or failed with what their steps recorded; finished jobs
cannot be cancelled; the worker's health is reported, and a real Redis
carries the queue's signals where one is running.
"""

import uuid

import pytest
import redis
from fastapi.testclient import TestClient

from app.main import app
from app.parsing import ParseError
from app.routers.deps import get_dispatcher
from app.routers.documents import get_parser
from app.services import jobs
from tests.test_concepts_api import environment, upload
from tests.test_graph_api import SCHEDULING
from tests.test_practice_api import concept_ids


def listed(client: TestClient, env: str) -> list[dict]:
    return client.get(f"/api/environments/{env}/jobs").json()


def test_an_upload_queues_reading_then_deriving(client: TestClient):
    env = environment(client)
    document = upload(client, env, "scheduling.pdf", SCHEDULING)

    derive, read = listed(client, env)
    [update] = client.get(f"/api/environments/{env}/updates").json()

    assert (read["kind"], read["lane"], read["title"]) == (
        "read",
        "read",
        "Reading scheduling.pdf",
    )
    assert (derive["kind"], derive["lane"], derive["title"]) == (
        "derive",
        "model",
        "Updating from scheduling.pdf",
    )
    for job in (read, derive):
        assert (job["status"], job["progress"], job["step"], job["error"]) == (
            "succeeded",
            100,
            None,
            None,
        )
        assert job["update_id"] == update["id"]
        assert job["attempts"] == 1
    assert client.get(f"/api/jobs/{read['id']}").json() == read
    assert document["id"] == update["document_id"]


class Unreadable:
    def parse(self, path):
        raise ParseError("This PDF is damaged and could not be opened.")


def test_a_failure_a_step_records_fails_the_job_with_its_message(client: TestClient):
    app.dependency_overrides[get_parser] = Unreadable
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)

    derive, read = listed(client, env)

    assert (read["status"], read["error"]) == (
        "failed",
        "This PDF is damaged and could not be opened.",
    )
    assert derive["status"] == "failed"
    assert derive["error"] == (
        "Reading the document: This PDF is damaged and could not be opened."
    )


def test_preparing_practice_is_one_job_with_a_step_per_concept(client: TestClient):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    ids = concept_ids(client, env)

    client.post(
        f"/api/environments/{env}/practice", json={"concept_ids": list(ids.values())}
    )

    practice = listed(client, env)[0]
    assert (practice["kind"], practice["title"], practice["status"]) == (
        "practice",
        f"Preparing practice for {len(ids)} concepts",
        "succeeded",
    )


def test_finished_jobs_cannot_be_cancelled_and_unknown_ones_are_not_found(
    client: TestClient,
):
    env = environment(client)
    upload(client, env, "scheduling.pdf", SCHEDULING)
    read = listed(client, env)[1]

    response = client.post(f"/api/jobs/{read['id']}/cancel")

    assert (response.status_code, response.json()["status"]) == (200, "succeeded")
    assert client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 404
    assert client.post(f"/api/jobs/{uuid.uuid4()}/cancel").status_code == 404


class Workers:
    def __init__(self, count):
        self.count = count

    def dispatch(self, job, background, tools):
        pass

    def workers(self):
        return self.count


def test_the_workers_health_is_reported(client: TestClient):
    assert client.get("/health/worker").json() == {"status": "ok", "workers": 1}

    app.dependency_overrides[get_dispatcher] = lambda: Workers(0)
    none = client.get("/health/worker")
    app.dependency_overrides[get_dispatcher] = lambda: Workers(None)
    unreachable = client.get("/health/worker")

    assert (none.status_code, none.json()["detail"]) == (
        503,
        "No worker is running. Start one with: python -m app.worker",
    )
    assert unreachable.status_code == 503


REDIS_TEST = "redis://localhost:6379/15"  # a database of its own


def redis_running() -> bool:
    try:
        return redis.Redis.from_url(REDIS_TEST, socket_connect_timeout=1).ping()
    except redis.RedisError:
        return False


@pytest.mark.skipif(not redis_running(), reason="needs Redis running locally")
def test_redis_carries_signals_and_sees_workers():
    client = redis.Redis.from_url(REDIS_TEST)
    client.flushdb()
    dispatcher = jobs.RedisDispatcher(REDIS_TEST)
    job = type("J", (), {"id": uuid.uuid4(), "lane": "read"})()

    dispatcher.dispatch(job, None, None)
    client.set(f"{jobs.WORKER_KEY}test", "alive", ex=30)

    assert client.rpop(jobs.SIGNAL.format(lane="read")).decode() == str(job.id)
    assert dispatcher.workers() == 1
    client.flushdb()
    assert jobs.RedisDispatcher("redis://localhost:1/0").workers() is None

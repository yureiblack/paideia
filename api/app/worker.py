"""The background job worker.

Purpose
-------
Runs the jobs the API queues (app/services/jobs.py, decision record 18):
reading documents and all the work for the language model, outside any
request, so restarting the API loses nothing.

Run it beside the API with:  python -m app.worker

One thread per lane: read (reading documents) and model (everything the
language model writes). A document being read never waits behind model work,
and model calls stay one at a time. Each lane takes the oldest job it may
run, waits for a signal from Redis when there is none, and looks at the jobs
table again every POLL seconds whatever Redis says. A third thread keeps the
worker's running jobs alive (their heartbeat) and its key in Redis, and every
RECOVER seconds runs again the jobs a stopped worker left running.
"""

import logging
import os
import signal
import socket
import threading
import uuid

import redis

from app.config import settings
from app.db import SessionLocal
from app.embedding import default_embedder
from app.llm import default_provider
from app.parsing import PyMuPDFParser
from app.reranking import default_reranker
from app.services import jobs

logger = logging.getLogger("app.worker")

POLL = 5.0  # seconds a lane waits for a signal before looking again
BEAT = 10.0  # seconds between heartbeats
RECOVER = 60.0  # seconds between looks for jobs a stopped worker left
KEY_TTL = 30  # seconds a worker's key in Redis outlives its last beat
STOP_WAIT = 300.0  # seconds to wait for the steps running when stopping


class Worker:
    def __init__(self, tools: jobs.Tools, redis_url: str, name: str | None = None):
        self.tools = tools
        self.name = (
            name or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        )
        self.redis = redis.Redis.from_url(redis_url, socket_timeout=POLL + 5)
        self.stopping = threading.Event()
        self.tools.stopping = self.stopping

    def run_one(self, lane: str) -> bool:
        """Claim and run one job of the lane. False if there was none."""
        with self.tools.session_factory() as session:
            job = jobs.claim(session, lane, self.name)
            job_id = job.id if job else None
        if job_id is None:
            return False
        logger.info("Running job %s (%s)", job_id, lane)
        jobs.run(self.tools, job_id)
        return True

    def _wait(self, lane: str) -> None:
        try:
            self.redis.brpop([jobs.SIGNAL.format(lane=lane)], timeout=POLL)
        except redis.RedisError:
            self.stopping.wait(POLL)  # no Redis: the table is looked at anyway

    def _lane(self, lane: str) -> None:
        while not self.stopping.is_set():
            try:
                if not self.run_one(lane):
                    self._wait(lane)
            except Exception:
                logger.exception("The %s lane hit an error; going on", lane)
                self.stopping.wait(POLL)

    def _keep_alive(self) -> None:
        since_recovery = RECOVER
        while not self.stopping.is_set():
            try:
                with self.tools.session_factory() as session:
                    jobs.beat(session, self.name)
                    if since_recovery >= RECOVER:
                        found = jobs.recover(session)
                        if found:
                            logger.info("Found %s jobs a stopped worker left", found)
                        since_recovery = 0.0
                self.redis.set(f"{jobs.WORKER_KEY}{self.name}", "alive", ex=KEY_TTL)
            except redis.RedisError:
                logger.warning(
                    "Redis is not reachable; jobs are still found in the table"
                )
            except Exception:
                logger.exception("Could not record the worker's heartbeat")
            self.stopping.wait(BEAT)
            since_recovery += BEAT

    def run(self) -> None:
        threads = [
            threading.Thread(target=self._keep_alive, name="keep-alive", daemon=True),
            *(
                threading.Thread(
                    target=self._lane, args=(lane,), name=lane, daemon=True
                )
                for lane in jobs.LANES
            ),
        ]
        for thread in threads:
            thread.start()
        logger.info("Worker %s started", self.name)
        self.stopping.wait()
        # Each lane finishes the step it is on (a model call may take a
        # minute or two), then puts its job back in the queue.
        for thread in threads:
            thread.join(timeout=STOP_WAIT)
        try:
            self.redis.delete(f"{jobs.WORKER_KEY}{self.name}")
        except redis.RedisError:
            pass
        logger.info("Worker %s stopped", self.name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    tools = jobs.Tools(
        session_factory=SessionLocal,
        llm=default_provider(),
        embedder=default_embedder(),
        parser=PyMuPDFParser(),
        reranker=default_reranker(),
    )
    worker = Worker(tools, settings.redis_url)
    # Ctrl+C or a stop signal: finish the steps running now, put their jobs
    # back in the queue, then stop. A worker that is killed instead leaves
    # its jobs running; the next worker finds them once their heartbeat is
    # STALE and runs them again.
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: worker.stopping.set())
    worker.run()


if __name__ == "__main__":
    main()

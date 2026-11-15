"""What the code is working on right now, for the logs (decision record 21).

Each request gets an id (app/main.py), and the worker sets the job and the
material update it is running (app/services/jobs.py). Context variables
follow each request and each worker thread on their own, so two requests or
two lanes never see each other's ids. Every log line carries the ids set
where it was written (app/logs.py), and a job records the request that
queued it, so one action can be followed from the request through every
step of its jobs.
"""

from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
update_id: ContextVar[str | None] = ContextVar("update_id", default=None)

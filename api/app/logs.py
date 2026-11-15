"""Structured logs for the API and the worker (decision record 21).

Purpose
-------
Every log line is one JSON object: the time, the level, where it came from,
the message, and the ids of what was being worked on (app/context.py): the
request, and in the worker the job and the material update. Anything passed
to a log call as extra= becomes a field of its own, so a request's line
carries its method, path, status and duration as data rather than as words
to parse. One upload can then be followed from the request that queued it
through every step of its jobs by searching for one id.

LOG_FORMAT=text gives one readable line per event instead, with the same
ids, for working locally. Python's standard logging does all of it; no
logging library is added.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from app import context
from app.config import settings

# The attributes every log record has. Anything else on a record was passed
# as extra= and is written out as its own field, except uvicorn's copy of
# its message with terminal colours in it.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}
_IDS = (
    ("request_id", context.request_id),
    ("job_id", context.job_id),
    ("update_id", context.update_id),
)


def _fields(record: logging.LogRecord) -> dict:
    fields = {name: var.get() for name, var in _IDS if var.get()}
    fields.update(
        (key, value)
        for key, value in vars(record).items()
        if key not in _STANDARD and not key.startswith("_")
    )
    return fields


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            **_fields(record),
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Local time, for reading at a terminal.
        time = (
            datetime.fromtimestamp(record.created, UTC)
            .astimezone()
            .strftime("%H:%M:%S")
        )
        extras = " ".join(f"{k}={v}" for k, v in _fields(record).items())
        line = f"{time} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if extras:
            line += f"  [{extras}]"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure() -> None:
    """Send every log line, uvicorn's included, through one handler in the
    chosen format. Called when the API or the worker starts, never on
    import, so the tests keep pytest's own log capture."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter() if settings.log_format == "json" else TextFormatter()
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    # Each request already gets one line from the API itself, with its id.
    logging.getLogger("uvicorn.access").disabled = True
    # The HTTP clients log every call to the model at INFO.
    for name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

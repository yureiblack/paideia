"""Request ids, request log lines and error bodies (decision record 21).

Purpose
-------
Every request gets an id. A caller may send its own in the X-Request-ID
header, and it is kept if it looks like one (letters, digits, dots, dashes
and underscores, at most 64); otherwise a new one is made. The id is

- returned in the X-Request-ID header of every response;
- added as request_id to every error body, so a message on the page can be
  matched to the server's log;
- on every log line written while the request is handled (app/logs.py),
  and on every job the request queues, so the worker's lines carry it too.

Each request also gets one log line with its method, path, status and
duration. The health checks, which the page polls, are logged at DEBUG.

An error nothing else handled becomes a 500 with a short message and the id,
never a traceback; the traceback goes to the log under the same id.
"""

import json
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import context

logger = logging.getLogger("app.requests")

HEADER = "X-Request-ID"
VALID = re.compile(r"[A-Za-z0-9._-]{1,64}")
QUIET = ("/health",)


def request_id_for(incoming: str | None) -> str:
    if incoming and VALID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def _with_id(response: Response) -> Response:
    """The same error response, with the request id in its body."""
    request_id = context.request_id.get()
    try:
        body = json.loads(response.body)
    except (AttributeError, ValueError):
        return response
    if isinstance(body, dict) and request_id:
        body["request_id"] = request_id
        headers = {
            k: v for k, v in response.headers.items() if k.lower() != "content-length"
        }
        return JSONResponse(body, status_code=response.status_code, headers=headers)
    return response


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        return _with_id(await http_exception_handler(request, exc))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, exc: RequestValidationError
    ) -> Response:
        return _with_id(await request_validation_exception_handler(request, exc))

    @app.middleware("http")
    async def correlate(request: Request, call_next) -> Response:
        request_id = request_id_for(request.headers.get(HEADER))
        token = context.request_id.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "Unhandled error in %s %s", request.method, request.url.path
                )
                response = JSONResponse(
                    {
                        "detail": "Something went wrong on the server.",
                        "request_id": request_id,
                    },
                    status_code=500,
                )
            response.headers[HEADER] = request_id
            quiet = request.url.path.startswith(QUIET) and response.status_code < 400
            logger.log(
                logging.DEBUG if quiet else logging.INFO,
                "%s %s %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round(1000 * (time.perf_counter() - start), 1),
                },
            )
            return response
        finally:
            context.request_id.reset(token)

"""The API as the end-to-end tests run it: the application itself, with the
language model swapped for the end-to-end stand-in (tests/e2e/model.py)
through FastAPI's own dependency overrides, as the backend tests do.

    uvicorn tests.e2e.server:app --port 8100
"""

from app.main import app
from app.routers.deps import get_llm
from tests.e2e import model

_llm = model.provider()
app.dependency_overrides[get_llm] = lambda: _llm

__all__ = ["app"]

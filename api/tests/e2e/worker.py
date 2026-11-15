"""The background worker as the end-to-end tests run it: the worker's own
main(), with the language model it builds swapped for the end-to-end
stand-in (tests/e2e/model.py). Everything else, including stopping on a
signal, is the real worker's.

    python -m tests.e2e.worker
"""

from app import worker
from tests.e2e import model

if __name__ == "__main__":
    worker.default_provider = model.provider
    worker.main()

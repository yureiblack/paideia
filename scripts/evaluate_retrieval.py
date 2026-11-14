"""Reproduce the retrieval and generation benchmark in docs/evaluation/.

From the repository root, with the services running (docker compose up -d)
and the virtual environment active:

    python scripts/evaluate_retrieval.py                # retrieval, about twenty minutes
    python scripts/evaluate_retrieval.py --generation   # also the summaries

--generation needs the local language model (Ollama) and adds about five
minutes. Each run rebuilds its own database, the development
database's name with _eval appended, so development and test data are never
touched. It writes docs/evaluation/results.json and refreshes the tables in
docs/evaluation/retrieval-benchmark.md. See decision record 20.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from evaluation.benchmark import main

if __name__ == "__main__":
    sys.exit(main())

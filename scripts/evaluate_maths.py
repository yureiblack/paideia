"""Reproduce the maths benchmark in docs/evaluation/maths-benchmark.md.

From the repository root, with the services running (docker compose up -d),
the virtual environment active and Tectonic installed (brew install tectonic):

    python scripts/evaluate_maths.py                # a few minutes, no model needed
    python scripts/evaluate_maths.py --read         # also reads new pages with the local model
    python scripts/evaluate_maths.py --practice     # also extracts concepts and chooses exercises

The model's readings are kept in docs/evaluation/maths/readings.json, so a
run without --read scores them again with the current code; --read asks the
local model only for pages it has not read, about forty seconds a part. Each
run rebuilds its own database, the development database's name with
_maths_eval appended, so development and test data are never touched. It
writes docs/evaluation/maths/results.json and refreshes the tables in
docs/evaluation/maths-benchmark.md. See decision record 30.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from evaluation.maths_benchmark import main

if __name__ == "__main__":
    sys.exit(main())

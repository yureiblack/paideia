"""The benchmark report's tables (decision record 20).

Purpose: every number in docs/evaluation/retrieval-benchmark.md comes from
results.json, written there by evaluation/report.py between markers, and
the prose around the markers is written by hand. A number typed or edited
by hand, results.json changed without the report, or a table that lost its
markers fails here, without running the twenty-minute benchmark.
"""

import json

from app.config import REPO_ROOT
from evaluation import report

DOCS = REPO_ROOT / "docs" / "evaluation"


def committed() -> tuple[str, dict]:
    document = (DOCS / "retrieval-benchmark.md").read_text(encoding="utf-8")
    results = json.loads((DOCS / "results.json").read_text(encoding="utf-8"))
    return document, results


def test_every_table_in_the_report_is_the_one_its_results_give():
    document, results = committed()

    for name in report.tables(results):
        assert f"<!-- results:{name} -->" in document
        assert f"<!-- /results:{name} -->" in document
    assert report.update(document, results) == document


def test_only_what_lies_between_the_markers_is_replaced():
    _, results = committed()
    document = (
        "# Prose kept\n\n"
        "<!-- results:retrieval -->\nold numbers\n<!-- /results:retrieval -->\n\n"
        "More prose.\n"
        "<!-- results:run --><!-- /results:run -->\n"
    )

    updated = report.update(document, results)

    assert updated.startswith("# Prose kept\n\n<!-- results:retrieval -->\n| Method |")
    assert "old numbers" not in updated
    assert "\n\nMore prose.\n" in updated
    # A pair of markers with nothing between them is filled too.
    assert (
        f"<!-- results:run -->\n{report.run_table(results)}\n<!-- /results:run -->"
        in updated
    )
    # Running again changes nothing.
    assert report.update(updated, results) == updated

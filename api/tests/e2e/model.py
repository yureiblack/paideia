"""The language model the end-to-end tests use: the backend tests'
MockProvider, answering as simple_answer does, except that each concept is
named after the heading of the passage it comes from ("Threads", not
"Concept 2").

Real names matter here because the knowledge map pairs two concepts when a
passage of one names the other (app/graph.py): "Threads" is paired with
"Processes" because the passage on threads mentions processes. With the
numbered names no passage names another concept, and the map would never
show a relationship.
"""

import re

from app import exercises
from tests.fakes import MockProvider, simple_answer


def answer(prompt, schema) -> dict:
    if prompt.name == "exercise_types":
        # The exercise types whose words the passages use, as the real
        # model's choice is kept only when they do (decision record 27).
        passages = prompt.user.split("Passages:", 1)[1].split("Exercises:", 1)[0]
        return {
            "exercises": [k for k in exercises.KINDS if exercises.fits(k, passages)][:3]
        }
    value = simple_answer(prompt, schema)
    if "concepts" in value:
        # Every passage starts with its section's heading on a line of its
        # own (app/services/sources.with_heading).
        headings = dict(re.findall(r"^\[(\d+)\] (.+)$", prompt.user, re.MULTILINE))
        for concept in value["concepts"]:
            heading = headings[str(concept["sources"][0])].strip()
            concept["name"] = heading
            concept["definition"] = f"What the passage on {heading.lower()} explains."
    return value


# The page whose maths the journey reads (decision record 26), and how the
# vision model reads it: the formula set in the Symbol font, whose text layer
# reads l for the λ it draws, so the reading writes l too and agrees with it.
EIGENVALUES_PROSE = (
    "An eigenvalue of a matrix is a root of its characteristic polynomial. "
    "For the matrix of the example, the polynomial is"
)
EIGENVALUES_FORMULA = "l2 - 6l + 1 = 0"
EIGENVALUES_READ = f"## Eigenvalues\n\n{EIGENVALUES_PROSE}\n\n$$l^2 - 6l + 1 = 0$$"


# The figure the journey reads (decision record 29): a chart of time slices,
# and how the vision model reads it. Its labels are the chart's own, and its
# description gives no number, so the check accepts it.
CHART_CAPTION = "Figure 1. Round robin time slices."
CHART_LABELS = ("P1", "P2", "P3")
CHART_READ = (
    "KIND\nchart\n\nTEXT\nP1\nP2\nP3\n\nTABLE\nnone\n\nDESCRIPTION\n"
    "Three bars of equal width, one for each process, in turn along a time line."
)


def transcription(prompt, image) -> str:
    return CHART_READ if prompt.name == "figure_reading" else EIGENVALUES_READ


def provider() -> MockProvider:
    return MockProvider(answer=answer, transcription=transcription)

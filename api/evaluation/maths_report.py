"""The tables of docs/evaluation/maths-benchmark.md, from maths/results.json.

As for the retrieval benchmark (evaluation/report.py), the report's prose is
written by hand and its numbers never are: each table sits between a pair of
markers, <!-- maths:name --> and <!-- /maths:name -->, and every run of the
maths benchmark replaces what lies between them.
"""

import re

from evaluation import notation

QUESTION_KINDS = {
    "term": "Names the term",
    "meaning": "In other words",
    "formula": "Asks for a formula",
    "notation": "Types the maths as words",
}
ATTEMPTS = {"whole": "Whole page", "halves": "In two halves"}


def _share(part: float, whole: float) -> str:
    return "n/a" if not whole else f"{100 * part / whole:.0f}%"


def _precise(part: float, whole: float) -> str:
    return "n/a" if not whole else f"{100 * part / whole:.1f}%"


def _score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def run_table(results: dict) -> str:
    run = results["run"]
    machine = run["machine"]
    rows = [
        ("Run", run["date"]),
        (
            "Commit",
            f"{run['commit']}{' with uncommitted changes' if run['uncommitted_changes'] else ''}",
        ),
        ("Inputs fingerprint", run["fingerprint"]),
        (
            "Machine",
            f"{machine['processor']}, {machine['memory_gb']} GB, {machine['system']}",
        ),
        ("Model", f"{run['model']}, prompt {run['prompt']}"),
        ("Typesetting", run["tectonic"]),
        (
            "Corpus",
            "{lectures} lectures, {pages} pages, {formulas} formulas, {words} words".format(
                **results["corpus"]
            ),
        ),
        ("Questions reviewed", run.get("reviewed") or "not yet"),
    ]
    return "\n".join(
        ["| | |", "|---|---|", *(f"| {a} | {_cell(str(b))} |" for a, b in rows)]
    )


def truth_table(results: dict) -> str:
    truth = results["truth"]
    lines = [
        f"{truth['accepted']} of {truth['pages']} perfect readings accepted.",
        "",
        "| Lecture | Page | Why the check refused the perfect reading |",
        "|---|---|---|",
    ]
    refused = [r for r in truth["rows"] if r["reason"]]
    for r in refused:
        lines.append(
            f"| {r['lecture'].removesuffix('.pdf')} | {r['page']} | {_cell(r['reason'])} |"
        )
    if not refused:
        lines.append("| | | none |")
    return "\n".join(lines)


def planted_table(results: dict) -> str:
    planted = results["planted"]
    lines = [
        (
            f"Planted in the {planted['pages']} pages whose perfect reading the check accepts, "
            f"up to {planted['per_page']} of each kind per page."
        ),
        "",
        "| Mistake | Planted | Caught | Share caught | A mistake it let through |",
        "|---|---|---|---|---|",
    ]
    for row in planted["kinds"].values():
        missed = row["missed"][0] if row["missed"] else None
        example = (
            f"`{_cell(missed['before'][:60])}` → `{_cell(missed['after'][:60])}`"
            if missed
            else ""
        )
        lines.append(
            f"| {row['label']} | {row['planted']} | {row['caught']} "
            f"| {_share(row['caught'], row['planted'])} | {example} |"
        )
    return "\n".join(lines)


def reading_table(results: dict) -> str:
    summary = results["reading"]["summary"]
    lines = [
        (
            "| Attempt | Pages usable | Formulas right | Pages with every formula right "
            "| Maths tokens wrong | Prose words wrong | Median seconds |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for name, label in ATTEMPTS.items():
        s = summary[name]
        lines.append(
            f"| {label} | {s['usable']} of {s['attempts']} "
            f"| {s['right']} of {s['formulas']} ({_precise(s['right'], s['formulas'])}) "
            f"| {s['pages_all_right']} of {s['usable']} "
            f"| {_precise(s['maths_errors'], s['maths_tokens'])} "
            f"| {_precise(s['prose_errors'], s['prose_words'])} "
            f"| {s['seconds'].get('median', 'n/a')} |"
        )
    return "\n".join(lines)


def app_table(results: dict) -> str:
    app = results["reading"]["summary"]["app"]
    kept = app["kept"]
    rows = [
        ("Pages read whole and accepted", kept.get("whole", 0)),
        ("Pages accepted on the second attempt, in halves", kept.get("halves", 0)),
        ("Pages that kept the PDF's text layer", kept.get("text layer", 0)),
        (
            "Formulas right on the pages read",
            (
                f"{app['right_in_read_pages']} of {app['formulas_in_read_pages']} "
                f"({_precise(app['right_in_read_pages'], app['formulas_in_read_pages'])})"
            ),
        ),
        (
            "Pages read with a wrong formula the check let through",
            app["read_pages_with_a_wrong_formula"],
        ),
        (
            "Model time per page, median (both attempts when needed)",
            f"{app['seconds_per_page'].get('median')} s",
        ),
    ]
    return "\n".join(["| | |", "|---|---|", *(f"| {a} | {b} |" for a, b in rows)])


def check_table(results: dict) -> str:
    check = results["reading"]["check"]
    lines = [
        "| Attempt | Wrong, refused | Wrong, accepted | Right, refused | Right, accepted | Not usable |",
        "|---|---|---|---|---|---|",
    ]
    for name, label in ATTEMPTS.items():
        c = check[name]
        lines.append(
            f"| {label} | {c.get('wrong_refused', 0)} | {c.get('wrong_accepted', 0)} "
            f"| {c.get('right_refused', 0)} | {c.get('right_accepted', 0)} | {c.get('unusable', 0)} |"
        )
    because = check.get("right_refused_because") or {}
    if because:
        lines += ["", "Right readings were refused because:", ""]
        lines += [
            f"- {_cell(reason)}: {n}"
            for reason, n in sorted(because.items(), key=lambda x: -x[1])
        ]
    return "\n".join(lines)


def notation_table(results: dict) -> str:
    rows = results["reading"]["notation"]
    counts = results["corpus"]["notation"]
    lines = [
        (
            "| Notation | Formulas in the corpus | Read right, whole page | Read right, in halves "
            "| Right among the formulas the app keeps |"
        ),
        "|---|---|---|---|---|",
    ]
    for kind in notation.KINDS:
        r = rows[kind.name]
        lines.append(
            f"| {kind.label} | {counts.get(kind.name, 0)} "
            f"| {_share(r.get('whole_right', 0), r.get('whole_formulas', 0))} "
            f"| {_share(r.get('halves_right', 0), r.get('halves_formulas', 0))} "
            f"| {_share(r.get('kept_right', 0), r.get('kept_formulas', 0))} |"
        )
    return "\n".join(lines)


def changes_table(results: dict) -> str:
    changes = results["reading"]["changes"]
    if not changes:
        return "No formula was read wrong."
    lines = ["| How a wrong formula differed | Times |", "|---|---|"]
    lines += [
        f"| {kind} | {n} |" for kind, n in sorted(changes.items(), key=lambda x: -x[1])
    ]
    return "\n".join(lines)


def wrong_formulas(results: dict) -> str:
    lines = [
        "| Lecture | Page | Attempt | Check | The page says | The reading has |",
        "|---|---|---|---|---|---|",
    ]
    for p in results["reading"]["pages"]:
        for name in ATTEMPTS:
            a = p[name]
            for f in a.get("results", []):
                if f["right"]:
                    continue
                said = "; ".join(c["page"] or "(nothing)" for c in f["changes"]) or "?"
                has = (
                    "; ".join(c["reading"] or "(nothing)" for c in f["changes"]) or "?"
                )
                lines.append(
                    f"| {p['lecture'][:2]} | {p['page']} | {name} | {'accepted' if a['accepted'] else 'refused'} "
                    f"| `{_cell(said[:70])}` | `{_cell(has[:70])}` |"
                )
    return "\n".join(lines) if len(lines) > 2 else "No formula was read wrong."


def timing_table(results: dict) -> str:
    t = results["timing"]
    rows = [
        ("Parse a page (text, blocks, headings)", f"{t['parse_ms_per_page']} ms"),
        ("Find which pages hold maths", f"{t['find_maths_ms_per_page']} ms a page"),
        ("Render a page for the model", f"{t['page_image_ms']} ms"),
        ("Read a page's text layer for the check", f"{t['page_layer_ms']} ms"),
        ("Make page text and check it", f"{t['check_ms']} ms"),
    ]
    if "model_seconds_per_page" in t:
        rows.append(
            (
                "The model's reading of a page, median",
                f"{t['model_seconds_per_page']} s",
            )
        )
        rows.append(
            ("A 400-page textbook, at that rate", f"{t['hours_for_400_pages']} hours")
        )
    retrieval = results.get("retrieval")
    if retrieval:
        for variant in ("read", "truth"):
            v = retrieval["variants"].get(variant)
            if v and "seconds_to_read_again" in v:
                rows.append(
                    (
                        f"Read the lectures again with {variant} pages in place, and embed",
                        f"{v['seconds_to_read_again']} s for {results['corpus']['pages']} pages",
                    )
                )
    return "\n".join(
        ["| Step | Time |", "|---|---|", *(f"| {a} | {b} |" for a, b in rows)]
    )


def retrieval_table(results: dict) -> str:
    retrieval = results.get("retrieval")
    if not retrieval:
        return "Not measured in this run."
    lines = [
        "| Lectures as | Method | Recall@5 | MRR@10 | Right passage first |",
        "|---|---|---|---|---|",
    ]
    for variant in retrieval["variants"].values():
        for method in variant["methods"].values():
            lines.append(
                f"| {variant['name']} | {method['name']} | {_score(method['recall@5']['all'])} "
                f"| {_score(method['rr']['all'])} | {100 * method['hit@1']['all']:.0f}% |"
            )
    return "\n".join(lines)


def retrieval_kinds(results: dict) -> str:
    retrieval = results.get("retrieval")
    if not retrieval:
        return "Not measured in this run."
    variants = retrieval["variants"]
    header = "| Question | " + " | ".join(v["name"] for v in variants.values()) + " |"
    lines = [header, "|---|" + "---|" * len(variants)]
    for kind, label in QUESTION_KINDS.items():
        cells = [
            _score(v["methods"]["hybrid_rerank"]["rr"].get(kind))
            for v in variants.values()
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    cells = [
        _score(v["methods"]["hybrid_rerank"]["rr"]["all"]) for v in variants.values()
    ]
    lines.append("| All | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def latex_words_table(results: dict) -> str:
    retrieval = results.get("retrieval")
    if not retrieval:
        return "Not measured in this run."
    lines = [
        "| Lectures as | Passages | LaTeX commands, most frequent | Environments |",
        "|---|---|---|---|",
    ]
    for v in retrieval["variants"].values():
        words = v["latex_words"]
        commands = ", ".join(
            f"\\{w} {n}" for w, n in list(words["commands"].items())[:6]
        )
        environments = ", ".join(f"{w} {n}" for w, n in words["environments"].items())
        lines.append(
            f"| {v['name']} | {words['passages']} | {commands or 'none'} | {environments or 'none'} |"
        )
    return "\n".join(lines)


def practice_table(results: dict) -> str:
    p = results.get("practice")
    if not p:
        return "Not measured in this run."
    rows = [
        ("Concepts extracted from the lectures as read", p["concepts"]),
        (
            "Concepts offered at least one computed exercise",
            p["concepts_with_an_exercise"],
        ),
        ("Exercises offered", p["exercises_offered"]),
        (
            "Exercises of a type their lecture teaches",
            f"{p['exercises_that_fit']} of {p['exercises_offered']} ({_share(p['exercises_that_fit'], p['exercises_offered'])})",
        ),
        (
            "Exercise types the lectures teach that were offered somewhere",
            f"{p['lecture_types_offered']} of {p['lecture_types_taught']}",
        ),
        (
            "Time to extract concepts, and to choose exercises",
            f"{p['seconds_extracting']} s and {p['seconds_choosing']} s",
        ),
    ]
    lines = ["| | |", "|---|---|", *(f"| {a} | {b} |" for a, b in rows)]
    misfits = [r for r in p["rows"] if r["misfit"]]
    if misfits:
        lines += [
            "",
            "| Concept | Lectures | Exercise offered that its lecture does not teach |",
            "|---|---|---|",
        ]
        lines += [
            f"| {_cell(r['concept'])} | {', '.join(x[:2] for x in r['lectures'])} | {', '.join(r['misfit'])} |"
            for r in misfits
        ]
    return "\n".join(lines)


def findings(results: dict) -> str:
    """The main results in sentences, every number from results.json."""
    out = []
    truth = results["truth"]
    out.append(
        f"- The check accepted the perfect reading of {truth['accepted']} of {truth['pages']} pages."
    )
    s = results["reading"]["summary"]
    for name, label in (("whole", "Read whole"), ("halves", "Read in halves")):
        a = s[name]
        out.append(
            f"- {label}, the model got {a['right']} of {a['formulas']} formulas right "
            f"({_precise(a['right'], a['formulas'])}), and every formula on "
            f"{a['pages_all_right']} of {a['usable']} pages."
        )
    app = s["app"]
    read = app["kept"].get("whole", 0) + app["kept"].get("halves", 0)
    out.append(
        f"- The app would keep the model's reading of {read} of {app['pages']} pages, "
        f"and {app['right_in_read_pages']} of their {app['formulas_in_read_pages']} formulas are right; "
        f"the check let a differing formula through on {app['read_pages_with_a_wrong_formula']} of them."
    )
    check = results["reading"]["check"]
    wrong_refused = sum(check[n].get("wrong_refused", 0) for n in ATTEMPTS)
    wrong = wrong_refused + sum(check[n].get("wrong_accepted", 0) for n in ATTEMPTS)
    right_refused = sum(check[n].get("right_refused", 0) for n in ATTEMPTS)
    right = right_refused + sum(check[n].get("right_accepted", 0) for n in ATTEMPTS)
    out.append(
        f"- Of the model's {wrong} wrong readings the check refused {wrong_refused}; "
        f"of its {right} right readings it refused {right_refused}."
    )
    kinds = results["planted"]["kinds"].values()
    caught = sum(k["caught"] for k in kinds)
    planted = sum(k["planted"] for k in kinds)
    always = [k["label"] for k in kinds if k["planted"] and k["caught"] == k["planted"]]
    never = [k["label"] for k in kinds if k["planted"] and k["caught"] == 0]
    out.append(
        f"- Planted mistakes: {caught} of {planted} caught ({_share(caught, planted)})."
    )
    if always:
        out.append(f"- Always caught: {'; '.join(always).lower()}.")
    if never:
        out.append(f"- Never caught: {'; '.join(never).lower()}.")
    rows = results["reading"]["notation"]
    weak = sorted(
        (r["whole_right"] / r["whole_formulas"], r["label"])
        for r in rows.values()
        if r.get("whole_formulas", 0) >= 5 and r["whole_right"] < r["whole_formulas"]
    )[:5]
    if weak:
        out.append(
            "- The notation read least well, whole page: "
            + "; ".join(f"{label.lower()} {100 * share:.0f}%" for share, label in weak)
            + "."
        )
    retrieval = results.get("retrieval")
    if retrieval:
        scores = {
            k: v["methods"]["hybrid_rerank"]["rr"]
            for k, v in retrieval["variants"].items()
        }
        if {"layer", "read", "truth"} <= scores.keys():
            out.append(
                f"- The app's search, MRR@10: {_score(scores['layer']['all'])} on the text layer, "
                f"{_score(scores['read']['all'])} with the model's readings, "
                f"{_score(scores['truth']['all'])} with perfect readings; for maths typed as words "
                f"{_score(scores['layer'].get('notation'))}, {_score(scores['read'].get('notation'))} and "
                f"{_score(scores['truth'].get('notation'))}."
            )
    t = results["timing"]
    if "model_seconds_per_page" in t:
        out.append(
            f"- A page took the model {t['model_seconds_per_page']} s (median, both attempts when needed): "
            f"about {t['hours_for_400_pages']} hours for a 400-page textbook."
        )
    p = results.get("practice")
    if p:
        out.append(
            f"- Practice: {p['concepts_with_an_exercise']} of {p['concepts']} concepts were offered a computed "
            f"exercise; {p['exercises_that_fit']} of {p['exercises_offered']} exercises were of a type their "
            f"lecture teaches."
        )
    return "\n".join(out)


def tables(results: dict) -> dict[str, str]:
    return {
        "findings": findings(results),
        "run": run_table(results),
        "truth": truth_table(results),
        "planted": planted_table(results),
        "reading": reading_table(results),
        "app": app_table(results),
        "check": check_table(results),
        "notation": notation_table(results),
        "changes": changes_table(results),
        "wrong": wrong_formulas(results),
        "timing": timing_table(results),
        "retrieval": retrieval_table(results),
        "retrieval-kinds": retrieval_kinds(results),
        "latex-words": latex_words_table(results),
        "practice": practice_table(results),
    }


def update(document: str, results: dict) -> str:
    """The report with every marked table replaced by the current one."""
    for name, table in tables(results).items():
        pattern = re.compile(
            rf"(<!-- maths:{re.escape(name)} -->).*?(<!-- /maths:{re.escape(name)} -->)",
            re.DOTALL,
        )
        document = pattern.sub(_filled(table), document)
    return document


def _filled(table: str):
    def fill(m: re.Match[str]) -> str:
        return f"{m.group(1)}\n{table}\n{m.group(2)}"

    return fill


def headline(results: dict) -> str:
    """A few lines for the terminal."""
    s = results["reading"]["summary"]
    app = s["app"]
    lines = [
        f"Perfect readings accepted by the check: {results['truth']['accepted']} of {results['truth']['pages']} pages",
        (
            f"Formulas read right: whole {_precise(s['whole']['right'], s['whole']['formulas'])}, "
            f"halves {_precise(s['halves']['right'], s['halves']['formulas'])}"
        ),
        (
            f"Pages the app would keep read: "
            f"{app['kept'].get('whole', 0) + app['kept'].get('halves', 0)} of {app['pages']}, "
            f"{app['read_pages_with_a_wrong_formula']} with a wrong formula let through"
        ),
    ]
    planted = results["planted"]["kinds"]
    caught = sum(k["caught"] for k in planted.values())
    total = sum(k["planted"] for k in planted.values())
    lines.append(f"Planted mistakes caught: {caught} of {total}")
    retrieval = results.get("retrieval")
    if retrieval:
        for v in retrieval["variants"].values():
            lines.append(
                f"Search, the app's method, MRR@10 with {v['name'].lower()}: "
                f"{_score(v['methods']['hybrid_rerank']['rr']['all'])}"
            )
    return "\n".join(lines)

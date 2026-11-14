"""The tables of docs/evaluation/retrieval-benchmark.md, from results.json.

The report's prose is written by hand; its numbers never are. Each table
sits between a pair of markers, such as

    <!-- results:retrieval -->
    ...
    <!-- /results:retrieval -->

and every run of the benchmark replaces what lies between them, leaving the
rest of the file as it was.
"""

import re

KIND_NAMES = {
    "term": "Names the term",
    "meaning": "In other words",
    "mixed": "Rare term, everyday question",
    "multi": "Needs two passages",
}


def _score(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _share(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.0f}%"


def _range(pair: list[float] | None) -> str:
    if not pair:
        return "n/a"
    low, high = pair
    return _score(low) if f"{low:.3f}" == f"{high:.3f}" else f"{low:.3f} to {high:.3f}"


def retrieval_table(results: dict) -> str:
    methods = results["retrieval"]["methods"]
    lines = [
        (
            "| Method | Recall@5 | Recall@10 | MRR@10 | MRR@10, lowest to highest build "
            "| Right passage first | Median time | 95th percentile |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in methods.values():
        lines.append(
            f"| {m['name']} | {_score(m['recall@5']['all'])} | {_score(m['recall@10']['all'])} "
            f"| {_score(m['rr']['all'])} | {_range(m.get('rr range'))} "
            f"| {_share(m['hit@1']['all'])} "
            f"| {m['latency_ms']['p50']:.1f} ms | {m['latency_ms']['p95']:.1f} ms |"
        )
    return "\n".join(lines)


def kinds_table(results: dict, score: str) -> str:
    retrieval = results["retrieval"]
    counts: dict[str, int] = {}
    for row in retrieval["questions"]:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    kinds = [k for k in KIND_NAMES if k in counts]
    head = " | ".join(f"{KIND_NAMES[k]} ({counts[k]})" for k in kinds)
    lines = [f"| Method | {head} |", "|---|" + "---|" * len(kinds)]
    for m in retrieval["methods"].values():
        cells = " | ".join(_score(m[score][k]) for k in kinds)
        lines.append(f"| {m['name']} | {cells} |")
    return "\n".join(lines)


def generation_table(results: dict) -> str:
    generation = results.get("generation")
    if not generation:
        return "_Not measured yet: run the benchmark with --generation._"
    lines = [
        "| Document | Key points | Citations | Citations supported | Points grounded | Key facts covered | Seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in generation["documents"]:
        if d["status"] != "ready":
            lines.append(
                f"| {d['document']} | not written: {d.get('error')} | | | | | {d['seconds']:.0f} |"
            )
            continue
        points = d["key_points"]
        citations = [c for p in points for c in p["citations"]]
        supported = sum(c["supported"] for c in citations)
        grounded = sum(any(c["supported"] for c in p["citations"]) for p in points)
        covered = sum(d["facts"].values())
        lines.append(
            f"| {d['document']} | {len(points)} | {len(citations)} | {supported} of {len(citations)} "
            f"| {grounded} of {len(points)} | {covered} of {len(d['facts'])} | {d['seconds']:.0f} |"
        )
    s = generation["scores"]
    lines.append(
        f"| **All {s['summaries']}** | {s['key_points']} | {s['citations']} "
        f"| **{_share(s['citation_correctness'])}** | **{_share(s['groundedness'])}** "
        f"| **{_share(s['completeness'])}** | median {s['seconds_per_summary']['p50']:.0f} |"
    )
    return "\n".join(lines)


def judge_table(results: dict) -> str:
    generation = results.get("generation")
    agreement = generation and generation.get("judge_agreement")
    if not agreement or "agreement" not in agreement:
        return "_The judge's sample has not been reviewed yet._"
    a = agreement
    return "\n".join(
        [
            "| | Pairs | Review: supported |",
            "|---|---|---|",
            (
                f"| Judge said supported | {a['judge_said_supported']} "
                f"| {_share(a['review_supported_when_judge_said_supported'])} |"
            ),
            (
                f"| Judge said unsupported | {a['judge_said_unsupported']} "
                f"| {_share(a['review_supported_when_judge_said_unsupported'])} |"
            ),
            f"| **All reviewed** | {a['pairs']} | judge agreed on **{_share(a['agreement'])}** |",
            "",
            (
                f"Citations supported, all {generation['scores']['citations']}: the judge says "
                f"{_share(generation['scores']['citation_correctness'])}; corrected with the "
                f"review, about **{_share(a['estimated_citation_correctness'])}**."
            ),
        ]
    )


def run_table(results: dict) -> str:
    r = results["retrieval"]
    run, corpus, sizes = r["run"], r["corpus"], r["sizes"]
    machine = run["machine"]
    rows = [
        (
            "Retrieval run",
            f"{run['date']}, commit {run['commit']}"
            + (" with uncommitted changes" if run["uncommitted_changes"] else ""),
        ),
        (
            "Inputs fingerprint",
            (
                f"{run.get('fingerprint', 'n/a')}: the corpus, labels, app and benchmark "
                "code and pinned dependencies; a rerun on the same files prints the same"
            ),
        ),
        (
            "Machine",
            f"{machine['processor']}, {machine['memory_gb']} GB, {machine['system']}",
        ),
        (
            "Corpus",
            (
                f"{corpus['documents']} documents, {corpus['pages']} pages, "
                f"{corpus['words']} words, {corpus['passages']} passages"
            ),
        ),
        (
            "Questions",
            (
                f"{len(r['questions'])}, each asked {r['rounds']} times per method, "
                f"in each of {r.get('builds', 1)} fresh builds of the database"
            ),
        ),
        (
            "Models",
            f"embedding {run['embedding_model']}, reranker {run['rerank_model']}",
        ),
        (
            "Search sizes",
            (
                f"{sizes['top_k_lexical']} from keyword search, {sizes['top_k_dense']} "
                f"from semantic search, {sizes['candidate_pool']} reranked, "
                f"{r['k']} returned"
            ),
        ),
        ("Labels checked", run["reviewed"] or "not yet"),
    ]
    generation = results.get("generation")
    if generation:
        g = generation["run"]
        rows.append(
            (
                "Generation run",
                f"{g['date']}, commit {g['commit']}, model {generation['llm']}",
            )
        )
    lines = ["| | |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def findings(results: dict) -> str:
    """The main observations, each computed from the results."""
    retrieval = results["retrieval"]
    m = retrieval["methods"]
    questions = retrieval["questions"]
    app, fused = m["hybrid_rerank"], m["hybrid"]
    semantic, lexical = m["semantic"], m["lexical"]
    missed_first = [
        q["id"] for q in questions if q["methods"]["hybrid_rerank"]["hit@1"] < 1
    ]
    missed_ten = [
        q["id"] for q in questions if q["methods"]["hybrid_rerank"]["recall@10"] < 1
    ]
    best = max(m.values(), key=lambda x: x["rr"]["all"])
    lines = [
        f"- Highest MRR@10: {best['name']}, {_score(best['rr']['all'])}.",
        (
            f"- Reranking the fused list raised MRR@10 from {_score(fused['rr']['all'])} to "
            f"{_score(app['rr']['all'])} and put the right passage first for "
            f"{_share(app['hit@1']['all'])} of questions instead of {_share(fused['hit@1']['all'])}, "
            f"at a median {app['latency_ms']['p50']:.0f} ms per search instead of "
            f"{fused['latency_ms']['p50']:.0f} ms."
        ),
        (
            f"- Questions in other words: semantic search alone reached MRR@10 "
            f"{_score(semantic['rr']['meaning'])}, keyword search alone {_score(lexical['rr']['meaning'])}, "
            f"the app {_score(app['rr']['meaning'])}."
        ),
        (
            f"- Questions naming the term: semantic {_score(semantic['rr']['term'])}, "
            f"keyword {_score(lexical['rr']['term'])}, the app {_score(app['rr']['term'])}."
        ),
        (
            f"- The app put a labelled passage first for {len(questions) - len(missed_first)} of "
            f"{len(questions)} questions; it missed some evidence in its top 10 for "
            f"{len(missed_ten)} ({', '.join(missed_ten) or 'none'})."
        ),
    ]
    generation = results.get("generation")
    if generation:
        s = generation["scores"]
        lines.append(
            f"- Summaries: {s['written']} of {s['summaries']} written; "
            f"{_share(s['citation_correctness'])} of {s['citations']} citations supported their "
            f"point, {_share(s['groundedness'])} of {s['key_points']} key points were grounded, "
            f"and they covered {_share(s['completeness'])} of the key facts. Median "
            f"{s['seconds_per_summary']['p50']:.0f} s per summary."
        )
        agreement = generation.get("judge_agreement") or {}
        if "agreement" in agreement:
            lines.append(
                f"- The judge agreed with the review on {_share(agreement['agreement'])} of "
                f"{agreement['pairs']} sampled pairs. Of the pairs it called supported, the "
                f"review agreed for {_share(agreement['review_supported_when_judge_said_supported'])}; "
                f"corrected with the review, about "
                f"{_share(agreement['estimated_citation_correctness'])} of all citations support "
                "their point."
            )
    return "\n".join(lines)


def tables(results: dict) -> dict[str, str]:
    return {
        "findings": findings(results),
        "retrieval": retrieval_table(results),
        "mrr-by-kind": kinds_table(results, "rr"),
        "recall10-by-kind": kinds_table(results, "recall@10"),
        "generation": generation_table(results),
        "judge": judge_table(results),
        "run": run_table(results),
    }


def update(document: str, results: dict) -> str:
    """The report with every marked table replaced by the current one."""
    for name, table in tables(results).items():
        pattern = re.compile(
            rf"(<!-- results:{re.escape(name)} -->).*?(<!-- /results:{re.escape(name)} -->)",
            re.DOTALL,
        )
        document = pattern.sub(
            lambda m, t=table: f"{m.group(1)}\n{t}\n{m.group(2)}", document
        )
    return document

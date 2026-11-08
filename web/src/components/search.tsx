"use client";

// The Search tab: ask in your own words and get back the passages that best
// answer it, each cited with its document and pages. "Show in page" opens a
// citation: the page the passage sits on, with the passage marked. Search
// runs when the form is submitted, not on every keystroke. "Show scoring"
// reveals how each result was ranked: its place in keyword search and in
// semantic search, their fused score, and the reranker's verdict, plus every
// candidate.

import { useEffect, useRef, useState, type FormEvent, type Ref } from "react";

import { useSearch } from "@/hooks/use-search";
import { usePreview } from "@/hooks/use-sources";
import {
  SEARCH_QUERY_MAX_LENGTH,
  type SearchCandidate,
  type SearchDebug,
  type SearchResult,
  type SourcePage,
} from "@/lib/types";

export function Search({ environmentId }: { environmentId: string }) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [showScoring, setShowScoring] = useState(false);
  const search = useSearch(environmentId, query, showScoring);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  const debug = search.data?.debug ?? null;
  const scoresById = new Map(
    debug?.candidates.map((candidate) => [candidate.chunk_id, candidate]),
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <form
          role="search"
          onSubmit={handleSubmit}
          className="flex flex-wrap gap-2"
        >
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={SEARCH_QUERY_MAX_LENGTH}
            placeholder="e.g. material related to process scheduling"
            aria-label="Search this environment's materials"
            className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
          />
          <button
            type="submit"
            disabled={!draft.trim()}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            Search
          </button>
        </form>
        <label className="flex items-center gap-2 self-start text-sm text-zinc-600 dark:text-zinc-400">
          <input
            type="checkbox"
            checked={showScoring}
            onChange={(event) => setShowScoring(event.target.checked)}
          />
          Show scoring
        </label>
      </div>

      {!query ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Search matches your words and their meaning, so passages need not
          contain your exact words. It covers materials that have finished
          reading.
        </p>
      ) : search.isPending ? (
        <p className="text-zinc-500">Searching…</p>
      ) : search.isError ? (
        <p role="alert" className="text-red-600 dark:text-red-400">
          Search failed: {search.error.message}
        </p>
      ) : search.data.results.length === 0 ? (
        <p className="text-zinc-500">
          Nothing to search yet. Upload materials and wait for them to finish
          reading.
        </p>
      ) : (
        <>
          <ol className="flex flex-col gap-3" aria-label="Search results">
            {search.data.results.map((result) => (
              <li key={result.citation.chunk_id}>
                <ResultCard
                  environmentId={environmentId}
                  result={result}
                  scores={scoresById.get(result.citation.chunk_id)}
                />
              </li>
            ))}
          </ol>
          {debug && <Candidates debug={debug} />}
        </>
      )}
    </div>
  );
}

function pagesLabel(start: number, end: number) {
  return start === end ? `Page ${start}` : `Pages ${start}–${end}`;
}

function ResultCard({
  environmentId,
  result,
  scores,
}: {
  environmentId: string;
  result: SearchResult;
  scores: SearchCandidate | undefined;
}) {
  const { citation } = result;
  const [showingPage, setShowingPage] = useState(false);

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="truncate font-medium">{citation.filename}</h3>
          <p className="text-xs text-zinc-500">
            {pagesLabel(citation.page_start, citation.page_end)}
            {citation.heading && ` · ${citation.heading}`}
          </p>
        </div>
        <span
          className="shrink-0 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          title="How well this passage answers your query, from 0 to 1"
        >
          {result.score.toFixed(2)}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm">{citation.excerpt}</p>
      {scores && <StageScores scores={scores} />}
      <button
        type="button"
        onClick={() => setShowingPage(!showingPage)}
        aria-expanded={showingPage}
        className="self-start rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium dark:border-zinc-700"
      >
        {showingPage ? "Hide page" : "Show in page"}
      </button>
      {showingPage && (
        <SourcePanel environmentId={environmentId} chunkId={citation.chunk_id} />
      )}
    </article>
  );
}

// The pages a cited passage sits on, with the passage marked and scrolled
// into view, so it can be read in its context.
function SourcePanel({
  environmentId,
  chunkId,
}: {
  environmentId: string;
  chunkId: string;
}) {
  const preview = usePreview(environmentId, chunkId, true);
  const scroller = useRef<HTMLDivElement>(null);
  const marked = useRef<HTMLElement>(null);

  // Scroll only the panel, not the whole page, to the start of the passage.
  useEffect(() => {
    if (scroller.current && marked.current) {
      scroller.current.scrollTop = Math.max(0, marked.current.offsetTop - 24);
    }
  }, [preview.data]);

  if (preview.isPending) {
    return <p className="text-sm text-zinc-500">Loading the page…</p>;
  }
  if (preview.isError) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        {preview.error.message}
      </p>
    );
  }
  const { citation, pages } = preview.data;
  return (
    <section
      aria-label={`${citation.filename}, ${pagesLabel(citation.page_start, citation.page_end)}`}
      className="flex flex-col gap-2"
    >
      <p className="text-sm font-medium">
        {citation.filename} · {pagesLabel(citation.page_start, citation.page_end)}
      </p>
      <div
        ref={scroller}
        className="relative flex max-h-[28rem] flex-col gap-4 overflow-y-auto rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900"
      >
        {pages.map((page, index) => (
          <PageWithPassage
            key={page.page_number}
            page={page}
            markRef={index === 0 ? marked : undefined}
          />
        ))}
      </div>
    </section>
  );
}

function PageWithPassage({
  page,
  markRef,
}: {
  page: SourcePage;
  markRef?: Ref<HTMLElement>;
}) {
  const { content, highlight_start: start, highlight_end: end } = page;
  return (
    <section aria-label={`Page ${page.page_number}`}>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Page {page.page_number}
      </h4>
      <p className="whitespace-pre-wrap text-sm">
        {content.slice(0, start)}
        <mark
          ref={markRef}
          className="rounded-sm bg-amber-100 text-inherit dark:bg-amber-900/60"
        >
          {content.slice(start, end)}
        </mark>
        {content.slice(end)}
      </p>
    </section>
  );
}

// "#2 · 0.061" for a stage that found the chunk, a dash for one that did not.
function rankAndScore(rank: number | null, score: number | null, digits: number) {
  return rank === null || score === null ? "—" : `#${rank} · ${score.toFixed(digits)}`;
}

function StageScores({ scores }: { scores: SearchCandidate }) {
  const stages = [
    ["Keywords", rankAndScore(scores.lexical_rank, scores.lexical_score, 3)],
    ["Meaning", rankAndScore(scores.semantic_rank, scores.semantic_score, 3)],
    ["Fused", scores.fusion_score.toFixed(4)],
    ["Reranker", scores.rerank_score?.toFixed(4) ?? "—"],
  ];
  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1 border-t border-zinc-100 pt-2 text-xs text-zinc-500 dark:border-zinc-800">
      {stages.map(([label, value]) => (
        <div key={label} className="flex gap-1">
          <dt>{label}</dt>
          <dd className="font-mono text-zinc-700 dark:text-zinc-300">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Candidates({ debug }: { debug: SearchDebug }) {
  const lexical = debug.candidates.filter((c) => c.lexical_rank !== null).length;
  const semantic = debug.candidates.filter((c) => c.semantic_rank !== null).length;
  const reranked = debug.candidates.filter((c) => c.rerank_score !== null).length;
  const kept = debug.candidates.filter((c) => c.final_rank !== null).length;

  return (
    <section aria-labelledby="candidates-heading" className="flex flex-col gap-2">
      <h3 id="candidates-heading" className="font-medium">
        Every candidate
      </h3>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Keyword search found {lexical} (of up to {debug.top_k_lexical}),
        semantic search {semantic} (of up to {debug.top_k_dense}). Merged, they
        made {debug.candidates.length} candidates. The reranker read the first{" "}
        {reranked} and kept its best {kept}, shown above.
      </p>
      <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-xs">
          <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">#</th>
              <th scope="col" className="px-3 py-2 font-medium">Passage</th>
              <th scope="col" className="px-3 py-2 font-medium">Keywords</th>
              <th scope="col" className="px-3 py-2 font-medium">Meaning</th>
              <th scope="col" className="px-3 py-2 font-medium">Fused</th>
              <th scope="col" className="px-3 py-2 font-medium">Reranker</th>
              <th scope="col" className="px-3 py-2 font-medium">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 font-mono dark:divide-zinc-800">
            {debug.candidates.map((c, index) => (
              <tr key={c.chunk_id}>
                <td className="px-3 py-2">{index + 1}</td>
                <td className="max-w-64 truncate px-3 py-2 font-sans">
                  {c.filename} · {pagesLabel(c.page_start, c.page_end).toLowerCase()}
                  {c.heading && ` · ${c.heading}`}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  {rankAndScore(c.lexical_rank, c.lexical_score, 3)}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  {rankAndScore(c.semantic_rank, c.semantic_score, 3)}
                </td>
                <td className="px-3 py-2">{c.fusion_score.toFixed(4)}</td>
                <td className="px-3 py-2">{c.rerank_score?.toFixed(4) ?? "—"}</td>
                <td className="px-3 py-2">
                  {c.final_rank === null ? "—" : `#${c.final_rank}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

"use client";

// The Search tab: ask in your own words and get back the passages that best
// answer it, each cited with its document and pages. "Show in page" opens a
// citation: the page the passage sits on, with the passage marked. Search
// runs when the form is submitted, not on every keystroke. "Show scoring"
// reveals how each result was ranked: its place in keyword search and in
// semantic search, their fused score, and the reranker's verdict, plus every
// candidate.

import { useState, type FormEvent } from "react";

import { MathsText } from "@/components/maths-text";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, OpenSign, Standfirst } from "@/components/ui";
import { useSearch } from "@/hooks/use-search";
import { pagesLabel, SourcePanel } from "@/components/source-panel";
import {
  SEARCH_QUERY_MAX_LENGTH,
  type SearchCandidate,
  type SearchDebug,
  type SearchResult,
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
    <div className="flex flex-col gap-7">
      <p className="label max-tab:sr-only">
        <span aria-hidden>03 / </span>Search
      </p>
      <form role="search" onSubmit={handleSubmit} className="flex flex-col gap-3 tab:flex-row tab:items-end tab:gap-5">
        <input
          type="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={SEARCH_QUERY_MAX_LENGTH}
          placeholder="e.g. material related to process scheduling"
          aria-label="Search this environment's materials"
          className="display min-w-0 flex-1 border-b-2 border-ink bg-transparent pb-2 text-[28px] leading-tight tracking-[-0.02em] placeholder:text-ink-3 focus:border-accent focus:outline-none tab:text-[44px]"
        />
        <button type="submit" disabled={!draft.trim()} className={`${button.primary} w-full tab:w-fit`}>
          Search <span aria-hidden>→</span>
        </button>
      </form>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="label text-[10px] text-ink-2">
          {query && search.data && !search.isPending
            ? `${search.data.results.length} ${search.data.results.length === 1 ? "passage" : "passages"}`
            : "Searches materials that have finished reading"}
        </p>
        <label className="label flex cursor-pointer items-center gap-2 text-[10px] text-ink-3">
          <input
            type="checkbox"
            checked={showScoring}
            onChange={(event) => setShowScoring(event.target.checked)}
            className="peer sr-only"
          />
          Show scoring
          <span aria-hidden className={`px-1.5 py-0.5 ${showScoring ? "bg-ink text-paper" : "text-ink-3"}`}>On</span>
          <span aria-hidden className={`px-1.5 py-0.5 ${showScoring ? "text-ink-3" : "bg-ink text-paper"}`}>Off</span>
        </label>
      </div>

      {!query ? (
        <Standfirst>
          Search matches your words and their meaning, so passages need not contain your exact
          words. It covers materials that have finished reading.
        </Standfirst>
      ) : search.isPending ? (
        <Loading what="results" lines={4} />
      ) : search.isError ? (
        <LoadError
          what="results"
          error={search.error}
          onRetry={() => void search.refetch()}
          retrying={search.isFetching}
        />
      ) : search.data.results.length === 0 ? (
        <Empty>
          Nothing to search yet. Upload materials and wait for them to finish
          reading.
        </Empty>
      ) : (
        <>
          <ol className="border-t border-ink" aria-label="Search results">
            {search.data.results.map((result, index) => (
              <li key={result.citation.chunk_id} className="border-b border-rule">
                <ResultCard
                  environmentId={environmentId}
                  number={index + 1}
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

function ResultCard({
  environmentId,
  number,
  result,
  scores,
}: {
  environmentId: string;
  number: number;
  result: SearchResult;
  scores: SearchCandidate | undefined;
}) {
  const { citation } = result;
  const [showingPage, setShowingPage] = useState(false);
  const blocks = Math.round(result.score * 5);

  return (
    <article className="flex flex-col gap-2.5 py-[18px]">
      <div className="flex items-baseline gap-4">
        <span className="label text-[10px] text-ink-3">{String(number).padStart(2, "0")}</span>
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5">
          <h3 className="label truncate text-[10px]">{citation.filename}</h3>
          <p className="label text-[10px] text-ink-2">
            <span aria-hidden>· </span>
            {pagesLabel(citation.page_start, citation.page_end)}
            {citation.heading && ` · ${citation.heading}`}
          </p>
        </div>
        <span
          className="label flex shrink-0 items-baseline gap-2.5"
          title="How well this passage answers your query, from 0 to 1"
        >
          <span aria-hidden className="tracking-[0.15em]">
            {"■".repeat(blocks)}
            {"□".repeat(5 - blocks)}
          </span>
          <span className="font-semibold">{result.score.toFixed(2)}</span>
        </span>
      </div>
      <div className="flex flex-col gap-2.5 tab:pl-9">
        <p className="max-w-3xl text-base leading-relaxed whitespace-pre-wrap">
          <MathsText text={citation.excerpt} />
        </p>
        {scores && <StageScores scores={scores} />}
        <button
          type="button"
          onClick={() => setShowingPage(!showingPage)}
          aria-expanded={showingPage}
          className={`${button.link} w-fit text-[10px]`}
        >
          {showingPage ? "Hide page" : "Show in page"} <OpenSign open={showingPage} />
        </button>
        {showingPage && (
          <SourcePanel environmentId={environmentId} chunkId={citation.chunk_id} />
        )}
      </div>
    </article>
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
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1 border-t border-rule pt-2 tab:flex tab:flex-wrap tab:gap-x-7">
      {stages.map(([label, value]) => (
        <div key={label} className="flex gap-2">
          <dt className="label text-[10px] text-ink-3">{label}</dt>
          <dd className="label text-[10px] tracking-[0.04em]">{value}</dd>
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
  const cell = "px-2 py-1.5 first:pl-0 last:pr-0";

  return (
    <section aria-labelledby="candidates-heading" className="flex flex-col gap-3 border-t border-ink pt-2.5">
      <h3 id="candidates-heading" className="label">
        Every candidate
      </h3>
      <p className="max-w-3xl text-sm leading-normal text-ink-2">
        Keyword search found {lexical} (of up to {debug.top_k_lexical}),
        semantic search {semantic} (of up to {debug.top_k_dense}). Merged, they
        made {debug.candidates.length} candidates. The reranker read the first{" "}
        {reranked} and kept its best {kept}, shown above.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="label border-b border-ink text-[10px] text-ink-3">
            <tr>
              <th scope="col" className={cell}>#</th>
              <th scope="col" className={cell}>Passage</th>
              <th scope="col" className={cell}>Keywords</th>
              <th scope="col" className={cell}>Meaning</th>
              <th scope="col" className={cell}>Fused</th>
              <th scope="col" className={cell}>Reranker</th>
              <th scope="col" className={cell}>Result</th>
            </tr>
          </thead>
          <tbody className="font-mono text-[11px]">
            {debug.candidates.map((c, index) => (
              <tr key={c.chunk_id} className={`border-b border-rule ${c.final_rank === null ? "text-ink-3" : ""}`}>
                <td className={cell}>{index + 1}</td>
                <td className={`max-w-64 truncate font-sans text-xs ${cell}`}>
                  {c.filename} · {pagesLabel(c.page_start, c.page_end).toLowerCase()}
                  {c.heading && ` · ${c.heading}`}
                </td>
                <td className={`whitespace-nowrap ${cell}`}>
                  {rankAndScore(c.lexical_rank, c.lexical_score, 3)}
                </td>
                <td className={`whitespace-nowrap ${cell}`}>
                  {rankAndScore(c.semantic_rank, c.semantic_score, 3)}
                </td>
                <td className={cell}>{c.fusion_score.toFixed(4)}</td>
                <td className={cell}>{c.rerank_score?.toFixed(4) ?? "—"}</td>
                <td className={cell}>{c.final_rank === null ? "—" : `#${c.final_rank}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

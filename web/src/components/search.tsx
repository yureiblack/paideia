"use client";

// The Search tab: ask in your own words and get back the passages that best
// answer it, each cited with its document and pages. "Show in page" opens a
// citation: the page the passage sits on, with the passage marked. Search
// runs when the form is submitted, not on every keystroke. Passages are
// held to a reading width (decision record 28). Scoring stays off until
// asked for; on, it shows how each result was ranked: its place in keyword
// search and in semantic search, their fused score, and the reranker's
// verdict, plus every candidate. With nothing found, the page says so
// plainly and suggests what to try: other words, a concept's name from the
// knowledge map, or later, while documents are still being read. A passage
// that is a figure the model read (decision record 29) shows the figure's
// picture, and says its words are the model's.

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

import { sectionNumber } from "@/components/environment-tabs";
import { MathsText } from "@/components/maths-text";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { pagesLabel, SourcePanel } from "@/components/source-panel";
import { button, OpenSign } from "@/components/ui";
import { useDocuments } from "@/hooks/use-documents";
import { useGraph } from "@/hooks/use-graph";
import { useSearch } from "@/hooks/use-search";
import { figureImageUrl } from "@/lib/api";
import {
  SEARCH_QUERY_MAX_LENGTH,
  type Document,
  type SearchCandidate,
  type SearchDebug,
  type SearchResult,
} from "@/lib/types";

// Passages and their pages are read at about 70 characters a line.
const READING_WIDTH = "max-w-[660px]";

export function Search({ environmentId }: { environmentId: string }) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [showScoring, setShowScoring] = useState(false);
  const search = useSearch(environmentId, query, showScoring);
  const documents = useDocuments(environmentId);
  const field = useRef<HTMLInputElement>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  function clear() {
    setDraft("");
    setQuery("");
    field.current?.focus();
  }

  const ready = documents.data?.filter((d) => d.status === "ready").length ?? null;
  const debug = search.data?.debug ?? null;
  const scoresById = new Map(
    debug?.candidates.map((candidate) => [candidate.chunk_id, candidate]),
  );
  const results = query && search.data && !search.isPending ? search.data.results : null;
  // "4 documents that have finished reading", "1 document that has".
  const covered =
    ready === null
      ? "the documents that have"
      : `${ready} ${ready === 1 ? "document that has" : "documents that have"}`;

  return (
    <div className="flex flex-col gap-7">
      <p className="label max-tab:sr-only">
        <span aria-hidden>{sectionNumber("Search")} / </span>Search
        <span className="text-ink-2"> — matches your words and their meaning</span>
      </p>
      <form role="search" onSubmit={handleSubmit} className="flex flex-col gap-3 tab:flex-row tab:items-end tab:gap-5">
        <input
          ref={field}
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
        <p className="text-[13px] leading-[1.4] text-ink-2">
          {results
            ? `${results.length} ${results.length === 1 ? "passage" : "passages"} from ${covered} finished reading`
            : `Searches ${covered} finished reading`}
        </p>
        <label className="label flex cursor-pointer items-center gap-2 text-ink-2">
          <input
            type="checkbox"
            checked={showScoring}
            onChange={(event) => setShowScoring(event.target.checked)}
            className="peer sr-only"
          />
          <span>
            <span className="sr-only">Show </span>Scoring
          </span>
          <span aria-hidden className={`px-1.5 py-0.5 ${showScoring ? "bg-ink text-paper" : "text-ink-3"}`}>On</span>
          <span aria-hidden className={`px-1.5 py-0.5 ${showScoring ? "text-ink-3" : "bg-ink text-paper"}`}>Off</span>
        </label>
      </div>

      {ready === 0 && (!query || (results && results.length === 0)) ? (
        <NothingToSearch environmentId={environmentId} />
      ) : !query ? (
        <p className={`${READING_WIDTH} text-[15px] leading-[1.55] text-ink-2`}>
          Search matches your words and their meaning, so passages need not contain your exact
          words. It covers materials that have finished reading.
        </p>
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
        <NothingFound
          environmentId={environmentId}
          query={query}
          documents={documents.data ?? []}
          onClear={clear}
        />
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

const isBeingRead = (d: Document) => d.status === "uploaded" || d.status === "processing";

// Nothing has finished reading, so there is nothing to search.
function NothingToSearch({ environmentId }: { environmentId: string }) {
  return (
    <Empty
      title="Nothing to search yet."
      action={
        <Link
          href={`/environments/${encodeURIComponent(environmentId)}/materials`}
          className={button.link}
        >
          Go to Materials <span aria-hidden>→</span>
        </Link>
      }
    >
      Search covers documents that have finished reading. Upload one; it can be searched as
      soon as its pages are read.
    </Empty>
  );
}

// A search that found nothing: say so plainly, and what to try instead.
function NothingFound({
  environmentId,
  query,
  documents,
  onClear,
}: {
  environmentId: string;
  query: string;
  documents: Document[];
  onClear: () => void;
}) {
  const graph = useGraph(environmentId);
  const names = conceptsToTry(query, graph.data?.nodes.map((n) => n.name) ?? []);
  const reading = documents.filter(isBeingRead).length;
  return (
    <section aria-labelledby="nothing-found" className="flex flex-col items-start gap-4">
      <h2 id="nothing-found" className="display text-[28px] leading-[1.05] tracking-[-0.015em] tab:text-[32px]">
        Nothing in these documents answers that.
      </h2>
      <div className="flex flex-col gap-2">
        <p className="label text-ink-2">Try</p>
        <ul className="flex max-w-[660px] flex-col gap-2 text-[16px] leading-[1.5]">
          <li>
            <span aria-hidden>— </span>Fewer or other words.
          </li>
          {names.length > 0 && (
            <li>
              <span aria-hidden>— </span>A concept&apos;s name from the knowledge map, such as{" "}
              {names.join(" or ")}.
            </li>
          )}
          {reading > 0 && (
            <li>
              <span aria-hidden>— </span>Again later: {reading}{" "}
              {reading === 1 ? "document is" : "documents are"} still being read, and search
              covers only those that have finished.
            </li>
          )}
        </ul>
      </div>
      <button type="button" onClick={onClear} className={button.link}>
        Clear the search
      </button>
    </section>
  );
}

// One or two concept names to suggest: any that share a word with the
// query first, then the first in the index.
function conceptsToTry(query: string, names: string[]): string[] {
  const words = query
    .toLowerCase()
    .split(/\W+/)
    .filter((w) => w.length > 3);
  const sharing = names.filter((name) =>
    name
      .toLowerCase()
      .split(/\W+/)
      .some((w) => words.includes(w)),
  );
  const rest = [...names].sort((a, b) => a.localeCompare(b));
  return [...new Set([...sharing, ...rest])].slice(0, 2);
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
        <span className="label text-ink-3">{String(number).padStart(2, "0")}</span>
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5">
          <h3 className="label truncate">{citation.filename}</h3>
          <p className="label text-ink-2">
            <span aria-hidden>· </span>
            {pagesLabel(citation.page_start, citation.page_end)}
            {citation.heading && ` · ${citation.heading}`}
          </p>
          {citation.figure_id && (
            <p className="label text-ink-3">
              <span aria-hidden>· </span>Figure · described by the model
            </p>
          )}
        </div>
        <span
          className="label flex shrink-0 items-baseline gap-2.5"
          title="How well this passage answers your query, from 0 to 1"
        >
          <span aria-hidden className="hidden tracking-[0.15em] tab:inline">
            {"■".repeat(blocks)}
            {"□".repeat(5 - blocks)}
          </span>
          <span className="font-semibold">{result.score.toFixed(2)}</span>
        </span>
      </div>
      <div className={`flex flex-col gap-2.5 tab:pl-9 ${READING_WIDTH} tab:max-w-[696px]`}>
        {citation.figure_id && (
          // The picture comes from the API, on another origin; Next's image
          // optimiser would only fetch it again.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={figureImageUrl(citation.figure_id)}
            alt={citation.heading ?? "A figure"}
            loading="lazy"
            className="block h-auto max-h-[180px] w-auto max-w-full self-start object-contain"
          />
        )}
        <p className="text-[17px] leading-[1.6] whitespace-pre-wrap">
          <MathsText text={citation.excerpt} />
        </p>
        {scores && <StageScores scores={scores} />}
        <button
          type="button"
          onClick={() => setShowingPage(!showingPage)}
          aria-expanded={showingPage}
          className={`${button.link} w-fit`}
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
          <dt className="label text-ink-3">{label}</dt>
          <dd className="label tracking-[0.04em]">{value}</dd>
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
      <p className="max-w-[640px] text-[15px] leading-[1.55] text-ink-2">
        Keyword search found {lexical} (of up to {debug.top_k_lexical}),
        semantic search {semantic} (of up to {debug.top_k_dense}). Merged, they
        made {debug.candidates.length} candidates. The reranker read the first{" "}
        {reranked} and kept its best {kept}, shown above.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="label border-b border-ink text-ink-3">
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
                <td className={`max-w-64 truncate font-sans text-[13px] ${cell}`}>
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

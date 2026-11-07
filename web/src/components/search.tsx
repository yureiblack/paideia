"use client";

// The Search tab: ask in your own words and get back the passages closest in
// meaning, with the document and pages each came from. Search runs when the
// form is submitted, not on every keystroke.

import { useState, type FormEvent } from "react";

import { useSearch } from "@/hooks/use-search";
import { SEARCH_QUERY_MAX_LENGTH, type SearchResult } from "@/lib/types";

export function Search({ environmentId }: { environmentId: string }) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const search = useSearch(environmentId, query);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  return (
    <div className="flex flex-col gap-6">
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

      {!query ? (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Search finds passages by meaning, so they need not contain your exact
          words. It covers materials that have finished reading.
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
        <ol className="flex flex-col gap-3" aria-label="Search results">
          {search.data.results.map((result) => (
            <li key={result.chunk_id}>
              <ResultCard result={result} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ResultCard({ result }: { result: SearchResult }) {
  const pages =
    result.page_start === result.page_end
      ? `Page ${result.page_start}`
      : `Pages ${result.page_start}–${result.page_end}`;

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="truncate font-medium">{result.filename}</h3>
          <p className="text-xs text-zinc-500">
            {pages}
            {result.heading && ` · ${result.heading}`}
          </p>
        </div>
        <span
          className="shrink-0 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          title="Similarity in meaning to your query: higher is closer"
        >
          {result.score.toFixed(2)}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm">{result.text}</p>
    </article>
  );
}

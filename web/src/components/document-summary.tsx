"use client";

// A document's summary, written by the local language model in the
// background once the document is read, and kept. Shows where it stands
// (waiting, being written, failed with the reason and Try again) and, once
// ready, the overview and key points, each with chips for the passages it
// cites. A chip opens that passage in its page, so every claim can be
// checked against the material itself.

import { useState } from "react";

import { pagesLabel, SourcePanel } from "@/components/source-panel";
import { formatDateTime } from "@/lib/format";
import type { Citation, CurrentSummary, SummaryPoint } from "@/lib/types";

export function DocumentSummaryPanel({
  environmentId,
  summary,
  loadError,
  onTryAgain,
  retrying,
  retryError,
}: {
  environmentId: string;
  summary: CurrentSummary | null | undefined;
  loadError: Error | null;
  onTryAgain: () => void;
  retrying: boolean;
  retryError: Error | null;
}) {
  if (loadError) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        Could not load the summary: {loadError.message}
      </p>
    );
  }
  if (summary === undefined) {
    return <p className="text-sm text-zinc-500">Loading the summary…</p>;
  }
  if (summary === null || summary.status === "pending") {
    return (
      <p className="text-sm text-zinc-500" role="status">
        Waiting to be summarized. Summaries are written one at a time, as soon
        as the model is free.
      </p>
    );
  }
  if (summary.status === "generating") {
    return (
      <p className="text-sm text-zinc-500" role="status">
        Writing the summary with the local model… usually under a minute; a
        long document can take several.
      </p>
    );
  }
  if (summary.status === "failed") {
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          The summary could not be written: {summary.error}
        </p>
        <button
          type="button"
          onClick={onTryAgain}
          disabled={retrying}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
        >
          {retrying ? "Asking…" : "Try again"}
        </button>
        {retryError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {retryError.message}
          </p>
        )}
      </div>
    );
  }
  return (
    <section
      aria-label="Summary"
      className="flex flex-col gap-3 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900"
    >
      <p className="text-sm">{summary.overview}</p>
      <ul className="flex flex-col gap-3">
        {summary.key_points.map((point, index) => (
          <li key={index}>
            <KeyPoint environmentId={environmentId} point={point} />
          </li>
        ))}
      </ul>
      <p className="text-xs text-zinc-500">
        Written by {summary.model} from this document&apos;s passages
        {summary.sections !== null &&
          summary.sections > 1 &&
          `, read in ${summary.sections} sections`}
        , {formatDateTime(summary.updated_at)}
        {summary.seconds !== null && `, in ${summary.seconds.toFixed(1)} s`}, with
        prompt {summary.prompt_versions.join(" and ")}.
        {summary.earlier_versions > 0 &&
          ` ${summary.earlier_versions} earlier ${
            summary.earlier_versions === 1 ? "summary is" : "summaries are"
          } kept.`}
      </p>
    </section>
  );
}

function chipLabel(citation: Citation) {
  const pages = pagesLabel(citation.page_start, citation.page_end)
    .replace("Pages ", "pp. ")
    .replace("Page ", "p. ");
  return citation.heading ? `${pages} · ${citation.heading}` : pages;
}

function KeyPoint({
  environmentId,
  point,
}: {
  environmentId: string;
  point: SummaryPoint;
}) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-sm">{point.text}</p>
      <div className="flex flex-wrap gap-1.5">
        {point.citations.map((citation) => {
          const isOpen = open === citation.chunk_id;
          return (
            <button
              key={citation.chunk_id}
              type="button"
              onClick={() => setOpen(isOpen ? null : citation.chunk_id)}
              aria-expanded={isOpen}
              title="Show this passage in its page"
              className={`max-w-full truncate rounded-full border px-2.5 py-0.5 text-xs ${
                isOpen
                  ? "border-zinc-900 dark:border-zinc-100"
                  : "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"
              }`}
            >
              {chipLabel(citation)}
            </button>
          );
        })}
      </div>
      {open && <SourcePanel environmentId={environmentId} chunkId={open} />}
    </div>
  );
}

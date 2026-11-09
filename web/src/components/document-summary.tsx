"use client";

// A document's summary, written by the local language model on request:
// an overview, then key points, each with chips for the passages it cites.
// A chip opens that passage in its page, so every claim can be checked
// against the material itself.

import { useState } from "react";

import { pagesLabel, SourcePanel } from "@/components/source-panel";
import type { Citation, DocumentSummary, SummaryPoint } from "@/lib/types";

export function DocumentSummaryPanel({
  environmentId,
  isPending,
  error,
  summary,
}: {
  environmentId: string;
  isPending: boolean;
  error: Error | null;
  summary: DocumentSummary | undefined;
}) {
  if (isPending) {
    return (
      <p className="text-sm text-zinc-500" role="status">
        Summarizing with the local model… usually under a minute; a long
        document can take a few minutes.
      </p>
    );
  }
  if (error) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        Could not summarize: {error.message}
      </p>
    );
  }
  if (!summary) return null;
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
        {summary.sections > 1 && `, read in ${summary.sections} sections`}, in{" "}
        {summary.seconds.toFixed(1)} s, with prompt{" "}
        {summary.prompt_versions.join(" and ")}. Not saved: asking again
        writes a fresh one.
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

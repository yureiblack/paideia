"use client";

// Key points with chips for the passages each cites. A chip opens that passage
// in its page. Used by document summaries and by the environment's summary,
// whose chips also name the document, since its points span several.

import { useState } from "react";

import { pagesLabel, SourcePanel } from "@/components/source-panel";
import type { Citation, SummaryPoint } from "@/lib/types";

export function CitedPoints({
  environmentId,
  points,
  showFilename = false,
}: {
  environmentId: string;
  points: SummaryPoint[];
  showFilename?: boolean;
}) {
  return (
    <ul className="flex flex-col gap-3">
      {points.map((point, index) => (
        <li key={index}>
          <KeyPoint
            environmentId={environmentId}
            point={point}
            showFilename={showFilename}
          />
        </li>
      ))}
    </ul>
  );
}

function chipLabel(citation: Citation, showFilename: boolean) {
  const pages = pagesLabel(citation.page_start, citation.page_end)
    .replace("Pages ", "pp. ")
    .replace("Page ", "p. ");
  if (showFilename) return `${citation.filename} · ${pages}`;
  return citation.heading ? `${pages} · ${citation.heading}` : pages;
}

function KeyPoint({
  environmentId,
  point,
  showFilename,
}: {
  environmentId: string;
  point: SummaryPoint;
  showFilename: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-sm">{point.text}</p>
      <CitationChips
        environmentId={environmentId}
        citations={point.citations}
        showFilename={showFilename}
      />
    </div>
  );
}

// A chip per cited passage; a chip opens its passage in its page, one at a
// time, below the chips.
export function CitationChips({
  environmentId,
  citations,
  showFilename = false,
}: {
  environmentId: string;
  citations: Citation[];
  showFilename?: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((citation) => {
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
              {chipLabel(citation, showFilename)}
            </button>
          );
        })}
      </div>
      {open && <SourcePanel environmentId={environmentId} chunkId={open} />}
    </>
  );
}

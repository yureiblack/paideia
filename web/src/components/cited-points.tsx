"use client";

// Key points, numbered and ruled, with a reference for each passage they
// cite. A reference opens that passage in its page. Used by document
// summaries and by the environment's summary, whose references also name the
// document, since its points span several.

import { useState } from "react";

import { MathsText } from "@/components/maths-text";
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
    <ol className="border-t border-ink">
      {points.map((point, index) => (
        <li key={index} className="flex gap-4 border-b border-rule py-4 tab:gap-5">
          <span aria-hidden className="label w-6 shrink-0 pt-1 text-[10px] text-ink-3">
            {String(index + 1).padStart(2, "0")}
          </span>
          <KeyPoint
            environmentId={environmentId}
            point={point}
            showFilename={showFilename}
          />
        </li>
      ))}
    </ol>
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
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <p className="max-w-3xl text-base leading-relaxed">
        <MathsText text={point.text} />
      </p>
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
      <div className="flex flex-wrap gap-x-3.5 gap-y-1.5">
        {citations.map((citation) => {
          const isOpen = open === citation.chunk_id;
          return (
            <button
              key={citation.chunk_id}
              type="button"
              onClick={() => setOpen(isOpen ? null : citation.chunk_id)}
              aria-expanded={isOpen}
              title="Show this passage in its page"
              className={`label max-w-full truncate text-[10px] tracking-[0.06em] ${
                isOpen
                  ? "bg-ink px-1.5 py-0.5 text-paper"
                  : "border-b border-rule pb-0.5 text-ink-2 hover:border-accent hover:text-ink"
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

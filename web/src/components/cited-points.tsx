"use client";

// Key points, numbered and ruled, with a reference for each passage they
// cite; a reference opens that passage in its page. Two ways to set them
// (decision record 28). A document's summary puts each point's references
// under it. The environment's summary numbers them as notes, as in a
// printed book: the numbers stand beside each point and the notes are
// listed in the margin, and either opens the passage under its point.
// Points are reading text, in the sans at 18 px and at most 640 px wide;
// sources are written in the sans too, "Week 1.pdf · p. 2" on a reference
// and "Week 1.pdf, p. 2" where they are read as a note.

import { Fragment, useEffect, useRef, useState } from "react";

import { MathsText } from "@/components/maths-text";
import { pagesLabel, SourcePanel } from "@/components/source-panel";
import type { Citation, SummaryPoint } from "@/lib/types";

// "p. 2", "pp. 2–3".
function pages(citation: Citation) {
  return pagesLabel(citation.page_start, citation.page_end)
    .replace("Pages ", "pp. ")
    .replace("Page ", "p. ");
}

// A reference's name: "Week 1.pdf · p. 2", or "p. 2 · Heading" when every
// reference is in the same document.
export function chipLabel(citation: Citation, showFilename: boolean) {
  if (showFilename) return `${citation.filename} · ${pages(citation)}`;
  return citation.heading ? `${pages(citation)} · ${citation.heading}` : pages(citation);
}

// A source written out as a note: "Week 1.pdf, p. 2".
export function sourceLabel(citation: Citation) {
  return `${citation.filename}, ${pages(citation)}`;
}

// A point's text, as reading text.
const READING = "max-w-[640px] text-[18px] leading-[1.7]";

// A point's number in the margin: "01".
function Folio({ number }: { number: number }) {
  return (
    <span aria-hidden className="label w-6 shrink-0 pt-2 text-ink-3">
      {String(number).padStart(2, "0")}
    </span>
  );
}

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
          <Folio number={index + 1} />
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            <p className={READING}>
              <MathsText text={point.text} />
            </p>
            <CitationChips
              environmentId={environmentId}
              citations={point.citations}
              showFilename={showFilename}
            />
          </div>
        </li>
      ))}
    </ol>
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
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {citations.map((citation) => {
          const isOpen = open === citation.chunk_id;
          return (
            <button
              key={citation.chunk_id}
              type="button"
              onClick={() => setOpen(isOpen ? null : citation.chunk_id)}
              aria-expanded={isOpen}
              title="Show this passage in its page"
              className={`max-w-full truncate text-left text-[13px] leading-[1.4] ${
                isOpen
                  ? "bg-ink px-1.5 py-0.5 text-paper"
                  : "border-b border-rule pb-px text-ink-2 hover:border-accent hover:text-ink"
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

// A numbered note: a passage the points cite, numbered in the order it is
// first cited, with the first point citing it.
export type Note = { number: number; citation: Citation; point: number };

export function numberNotes(points: SummaryPoint[]): Note[] {
  const notes = new Map<string, Note>();
  points.forEach((point, index) => {
    for (const citation of point.citations) {
      if (!notes.has(citation.chunk_id)) {
        notes.set(citation.chunk_id, { number: notes.size + 1, citation, point: index });
      }
    }
  });
  return [...notes.values()];
}

// The note open under a point, and whether it was opened from the margin,
// which may be far from the point on a narrow screen.
export type OpenNote = { chunkId: string; point: number; fromMargin: boolean } | null;

// One passage per chunk, in the order cited.
function distinct(citations: Citation[]) {
  return citations.filter(
    (c, index) => citations.findIndex((d) => d.chunk_id === c.chunk_id) === index,
  );
}

export function NotedPoints({
  environmentId,
  points,
  notes,
  open,
  onOpen,
}: {
  environmentId: string;
  points: SummaryPoint[];
  notes: Note[];
  open: OpenNote;
  onOpen: (note: OpenNote) => void;
}) {
  const numbers = new Map(notes.map((n) => [n.citation.chunk_id, n.number]));
  return (
    <ol className="border-t border-rule">
      {points.map((point, index) => {
        const cited = distinct(point.citations);
        return (
          <li key={index} className="flex flex-col gap-3 border-b border-rule py-5">
            <div className="flex gap-4 tab:gap-5">
              <Folio number={index + 1} />
              <p className={`min-w-0 flex-1 ${READING}`}>
                <MathsText text={point.text} />
              </p>
              {cited.length > 0 && (
                <span className="label flex shrink-0 items-start pt-1 text-ink-3">
                  {cited.map((citation, n) => {
                    const number = numbers.get(citation.chunk_id) ?? 0;
                    const isOpen = open?.chunkId === citation.chunk_id && open.point === index;
                    return (
                      <Fragment key={citation.chunk_id}>
                        {n > 0 && <span aria-hidden className="pt-1">,</span>}
                        <button
                          type="button"
                          onClick={() =>
                            onOpen(isOpen ? null : { chunkId: citation.chunk_id, point: index, fromMargin: false })
                          }
                          aria-expanded={isOpen}
                          aria-label={`Note ${number}, ${chipLabel(citation, true)}`}
                          title={sourceLabel(citation)}
                          className={`flex h-6 min-w-6 items-center justify-center px-1 ${
                            isOpen ? "bg-ink text-paper" : "hover:text-ink hover:underline hover:decoration-accent"
                          }`}
                        >
                          {number}
                        </button>
                      </Fragment>
                    );
                  })}
                </span>
              )}
            </div>
            {open && open.point === index && (
              <OpenPassage
                key={open.chunkId}
                environmentId={environmentId}
                chunkId={open.chunkId}
                fromMargin={open.fromMargin}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

// A note's passage, under its point. Opened from the margin, the point is
// brought into view, as on a phone the margin comes after every point.
function OpenPassage({
  environmentId,
  chunkId,
  fromMargin,
}: {
  environmentId: string;
  chunkId: string;
  fromMargin: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (fromMargin) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [fromMargin]);
  return (
    <div ref={ref} className="max-w-[684px] tab:pl-11">
      <SourcePanel environmentId={environmentId} chunkId={chunkId} />
    </div>
  );
}

// The notes in the margin, each opening its passage under the first point
// that cites it.
export function NoteList({
  notes,
  open,
  onOpen,
}: {
  notes: Note[];
  open: OpenNote;
  onOpen: (note: OpenNote) => void;
}) {
  return (
    <section aria-labelledby="notes-heading" className="flex flex-col gap-2.5">
      <h3 id="notes-heading" className="label text-ink-2">
        Notes
      </h3>
      <ol className="flex flex-col gap-1">
        {notes.map((note) => {
          const isOpen = open?.chunkId === note.citation.chunk_id;
          return (
            <li key={note.citation.chunk_id} className="flex items-baseline gap-3">
              <span aria-hidden className="label w-4 shrink-0 text-ink-3">
                {note.number}
              </span>
              <button
                type="button"
                onClick={() =>
                  onOpen(
                    isOpen
                      ? null
                      : { chunkId: note.citation.chunk_id, point: note.point, fromMargin: true },
                  )
                }
                aria-expanded={isOpen}
                className={`min-w-0 text-left text-[13px] leading-[1.4] break-words ${
                  isOpen ? "underline decoration-accent decoration-2 underline-offset-[3px]" : "hover:underline hover:decoration-accent"
                }`}
              >
                {sourceLabel(note.citation)}
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

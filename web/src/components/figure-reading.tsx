"use client";

// Reading a document's figures with the local vision model (decision record
// 29), offered on the Figures tab of the document's page, never done unasked:
// how many figures were found and on how many pages, a range to read, how
// long it should take, and which figures earlier readings kept as the PDF had
// them. Once started, the reading shows in the background work like any
// other, and can be cancelled there.

import { useState, type FormEvent } from "react";

import { duration } from "@/components/maths-reading";
import { Empty, LoadError, Loading } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import { useFigures, useReadFigures } from "@/hooks/use-documents";
import type { Document } from "@/lib/types";

const field =
  "w-20 border-b border-ink bg-transparent pb-1 text-center text-base focus:border-b-2 focus:border-accent focus:pb-[3px] focus:outline-none";

const figures = (n: number) => `${n} ${n === 1 ? "figure" : "figures"}`;
const pagesOf = (n: number) => `${n} ${n === 1 ? "page" : "pages"}`;

export function FiguresPanel({
  document,
  environmentId,
}: {
  document: Document;
  environmentId: string;
}) {
  const overview = useFigures(document.id);
  const read = useReadFigures(environmentId, document.id);
  const pages = document.page_count ?? 1;
  const [first, setFirst] = useState(1);
  const [last, setLast] = useState(pages);
  const [showingKept, setShowingKept] = useState(false);
  // The reading just started: how many figures, and how long they should take.
  const [started, setStarted] = useState<{ figures: number; seconds: number } | null>(null);

  const label = `Figures of ${document.filename}`;
  if (started) {
    return (
      <section aria-label={label} className="flex max-w-[640px] flex-col items-start gap-3">
        <p role="status" className="text-base leading-[1.55]">
          Reading {figures(started.figures)}, {duration(started.seconds)}. The text takes{" "}
          {started.figures === 1 ? "it" : "them"} in once the reading is done; the background
          work shows how far it has got.
        </p>
        <button type="button" onClick={() => setStarted(null)} className={button.link}>
          Choose other pages
        </button>
      </section>
    );
  }
  if (overview.isPending) {
    return (
      <section aria-label={label}>
        <Loading what="the figures" />
      </section>
    );
  }
  if (overview.error) {
    return (
      <section aria-label={label}>
        <LoadError
          what="the figures"
          error={overview.error}
          onRetry={() => void overview.refetch()}
          retrying={overview.isFetching}
        />
      </section>
    );
  }

  const { figures: found, kept, seconds_per_figure } = overview.data;
  const done = new Set([...overview.data.read, ...kept.map((k) => k.key)]);
  // Read before by a reading that was cancelled: to read, but in no time.
  const waiting = new Set(overview.data.waiting);
  const valid = 1 <= first && first <= last && last <= pages;
  const inRange = valid ? found.filter((f) => first <= f.page && f.page <= last) : [];
  const toRead = inRange.filter((f) => !done.has(f.key));
  const seconds = toRead.filter((f) => !waiting.has(f.key)).length * seconds_per_figure;
  const onPages = new Set(found.map((f) => f.page)).size;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!toRead.length) return;
    const estimate = { figures: toRead.length, seconds };
    read.mutate({ first, last }, { onSuccess: () => setStarted(estimate) });
  }

  if (!found.length) {
    return (
      <section aria-label={label} className="max-w-[640px]">
        <Empty>
          Paideia finds no figures in “{document.filename}”: no drawings or pictures, and no
          tables with a caption, so there are none to read.
        </Empty>
      </section>
    );
  }

  return (
    <section aria-label={label} className="flex max-w-[640px] flex-col gap-5">
      <div className="flex flex-col gap-2">
        <h3 className="display text-[28px] leading-[1.05] tracking-[-0.015em]">Read the figures</h3>
        <p className="text-[15px] leading-[1.55] text-ink-2">
          The local model writes down what is written in each figure and describes what it
          shows: what is written is checked against the figure, but the description cannot be,
          so it is marked as the model&apos;s and nothing in summaries or practice is made from
          it. {figures(found.length)} {found.length === 1 ? "was" : "were"} found on{" "}
          {pagesOf(onPages)}.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-[13px] leading-[1.4] text-ink-2">From page</span>
            <input
              type="number"
              min={1}
              max={pages}
              value={first}
              onChange={(event) => setFirst(Number(event.target.value))}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[13px] leading-[1.4] text-ink-2">To page</span>
            <input
              type="number"
              min={1}
              max={pages}
              value={last}
              onChange={(event) => setLast(Number(event.target.value))}
              className={field}
            />
          </label>
          <p role="status" className="pb-1.5 text-[15px] leading-[1.4] text-ink-2">
            {!valid
              ? `Choose pages from 1 to ${pages}.`
              : !inRange.length
                ? "No figure on these pages."
                : !toRead.length
                  ? "Every figure here has been read."
                  : `${figures(toRead.length)} to read · ${duration(seconds)}`}
          </p>
        </div>

        {read.error && (
          <p role="alert" className="flex items-start gap-2 text-[15px] leading-[1.45]">
            <span className="pt-[7px]">
              <Mark />
            </span>
            {read.error.message}
          </p>
        )}

        <div>
          <button
            type="submit"
            disabled={!toRead.length || read.isPending}
            className={button.primary}
          >
            {read.isPending ? "Starting…" : "Read the figures"}
          </button>
        </div>
      </form>

      {(overview.data.read.length > 0 || kept.length > 0) && (
        <div className="flex flex-col gap-2 border-t border-rule pt-3">
          <p className="text-[13px] leading-[1.4] text-ink-2">
            {figures(overview.data.read.length)} read
            {kept.length > 0 && (
              <>
                {" · "}
                <button
                  type="button"
                  onClick={() => setShowingKept(!showingKept)}
                  aria-expanded={showingKept}
                  className="label hover:underline"
                >
                  {kept.length} {kept.length === 1 ? "keeps" : "keep"} the PDF&apos;s own text{" "}
                  <OpenSign open={showingKept} />
                </button>
              </>
            )}
          </p>
          {showingKept && (
            <ul
              aria-label="Figures that keep the PDF's own text"
              className="flex flex-col gap-2.5 text-[15px] leading-[1.55]"
            >
              {kept.map(({ key, page, caption, reason }) => (
                <li key={key} className="flex flex-col">
                  <span>
                    {caption ?? `A figure on page ${page}`}
                    {caption && <span className="text-ink-2"> · page {page}</span>}
                  </span>
                  <span className="text-ink-2">{reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

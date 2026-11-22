"use client";

// Reading a document's maths with the local vision model (decision record
// 26), offered on the Maths tab of the document's page, never done unasked:
// which pages set maths in maths fonts, a range to read, how long it should
// take, and what earlier readings kept. Once started, the reading shows in
// the background work like any other, and can be cancelled there.

import { useState, type FormEvent } from "react";

import { LoadError, Loading } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import { useMaths, useReadMaths } from "@/hooks/use-documents";
import type { Document } from "@/lib/types";

// "about 9 minutes", "about 2 hours 10 minutes": how long a reading takes.
export function duration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "under a minute";
  if (minutes === 1) return "about a minute";
  if (minutes < 60) return `about ${minutes} minutes`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const hoursText = hours === 1 ? "1 hour" : `${hours} hours`;
  return rest ? `about ${hoursText} ${rest} minutes` : `about ${hoursText}`;
}

const field =
  "w-20 border-b border-ink bg-transparent pb-1 text-center text-base focus:border-b-2 focus:border-accent focus:pb-[3px] focus:outline-none";

export function MathsPanel({
  document,
  environmentId,
}: {
  document: Document;
  environmentId: string;
}) {
  const maths = useMaths(document.id);
  const read = useReadMaths(environmentId, document.id);
  const pages = document.page_count ?? 1;
  const [first, setFirst] = useState(1);
  const [last, setLast] = useState(pages);
  const [showingKept, setShowingKept] = useState(false);
  // The reading just started: how many pages, and how long they should take.
  const [started, setStarted] = useState<{ pages: number; seconds: number } | null>(null);

  const label = `Maths of ${document.filename}`;
  if (started) {
    return (
      <section aria-label={label} className="flex max-w-[640px] flex-col items-start gap-3">
        <p role="status" className="text-base leading-[1.55]">
          Reading the maths of {started.pages} {started.pages === 1 ? "page" : "pages"},{" "}
          {duration(started.seconds)}. The text takes it in once the reading is done; the
          background work shows how far it has got.
        </p>
        <button type="button" onClick={() => setStarted(null)} className={button.link}>
          Choose other pages
        </button>
      </section>
    );
  }
  if (maths.isPending) {
    return (
      <section aria-label={label}>
        <Loading what="the pages with maths" />
      </section>
    );
  }
  if (maths.error) {
    return (
      <section aria-label={label}>
        <LoadError
          what="the pages with maths"
          error={maths.error}
          onRetry={() => void maths.refetch()}
          retrying={maths.isFetching}
        />
      </section>
    );
  }

  const { maths_pages, kept_text, seconds_per_page } = maths.data;
  const done = new Set([...maths.data.read, ...kept_text.map((k) => k.page)]);
  // Read before by a reading that was cancelled: to read, but in no time.
  const waiting = new Set(maths.data.waiting);
  const valid = 1 <= first && first <= last && last <= pages;
  const inRange = valid ? maths_pages.filter((p) => first <= p && p <= last) : [];
  const toRead = inRange.filter((p) => !done.has(p));

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!toRead.length) return;
    const estimate = {
      pages: toRead.length,
      seconds: toRead.filter((p) => !waiting.has(p)).length * seconds_per_page,
    };
    read.mutate({ first, last }, { onSuccess: () => setStarted(estimate) });
  }

  if (!maths_pages.length) {
    return (
      <section aria-label={label} className="max-w-[640px]">
        <p className="text-base leading-[1.55]">
          No page of “{document.filename}” sets maths in a maths font, so there is no
          maths to read.
        </p>
      </section>
    );
  }

  return (
    <section aria-label={label} className="flex max-w-[640px] flex-col gap-5">
      <div className="flex flex-col gap-2">
        <h3 className="display text-[28px] leading-[1.05] tracking-[-0.015em]">Read the maths</h3>
        <p className="text-[15px] leading-[1.55] text-ink-2">
          A PDF&apos;s text keeps the words but loses the maths: a matrix becomes a row of
          numbers. The local model reads each page&apos;s picture instead, and a page is used
          only if it agrees with the PDF&apos;s own text. {maths_pages.length} of {pages}{" "}
          {pages === 1 ? "page sets" : "pages set"} maths.
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
                ? "No page here sets maths."
                : !toRead.length
                  ? "Every page with maths here has been read."
                  : `${toRead.length} ${toRead.length === 1 ? "page" : "pages"} to read · ${duration(
                      toRead.filter((p) => !waiting.has(p)).length * seconds_per_page,
                    )}`}
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
            {read.isPending ? "Starting…" : "Read the maths"}
          </button>
        </div>
      </form>

      {(maths.data.read.length > 0 || kept_text.length > 0) && (
        <div className="flex flex-col gap-2 border-t border-rule pt-3">
          <p className="text-[13px] leading-[1.4] text-ink-2">
            Maths read on {maths.data.read.length}{" "}
            {maths.data.read.length === 1 ? "page" : "pages"}
            {kept_text.length > 0 && (
              <>
                {" · "}
                <button
                  type="button"
                  onClick={() => setShowingKept(!showingKept)}
                  aria-expanded={showingKept}
                  className="label hover:underline"
                >
                  {kept_text.length} {kept_text.length === 1 ? "keeps" : "keep"} the PDF&apos;s
                  own text <OpenSign open={showingKept} />
                </button>
              </>
            )}
          </p>
          {showingKept && (
            <ul aria-label="Pages that keep the PDF's own text" className="flex flex-col gap-1 text-[15px] leading-[1.55]">
              {kept_text.map(({ page, reason }) => (
                <li key={page} className="flex gap-3">
                  <span className="label w-16 shrink-0 pt-[3px] text-ink-3">Page {page}</span>
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

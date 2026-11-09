"use client";

// A citation opened in place: the pages a cited passage sits on, with the
// passage marked and scrolled into view, so it can be read in its context.
// Search results and summaries both open their citations with it.

import { useEffect, useRef, type Ref } from "react";

import { usePreview } from "@/hooks/use-sources";
import type { SourcePage } from "@/lib/types";

export function pagesLabel(start: number, end: number) {
  return start === end ? `Page ${start}` : `Pages ${start}–${end}`;
}

// The pages a cited passage sits on, with the passage marked and scrolled
// into view, so it can be read in its context.
export function SourcePanel({
  environmentId,
  chunkId,
}: {
  environmentId: string;
  chunkId: string;
}) {
  const preview = usePreview(environmentId, chunkId, true);
  const scroller = useRef<HTMLDivElement>(null);
  const marked = useRef<HTMLElement>(null);

  // Scroll only the panel, not the whole page, to the start of the passage.
  useEffect(() => {
    if (scroller.current && marked.current) {
      scroller.current.scrollTop = Math.max(0, marked.current.offsetTop - 24);
    }
  }, [preview.data]);

  if (preview.isPending) {
    return <p className="text-sm text-zinc-500">Loading the page…</p>;
  }
  if (preview.isError) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        {preview.error.message}
      </p>
    );
  }
  const { citation, pages } = preview.data;
  return (
    <section
      aria-label={`${citation.filename}, ${pagesLabel(citation.page_start, citation.page_end)}`}
      className="flex flex-col gap-2"
    >
      <p className="text-sm font-medium">
        {citation.filename} · {pagesLabel(citation.page_start, citation.page_end)}
      </p>
      <div
        ref={scroller}
        className="relative flex max-h-[28rem] flex-col gap-4 overflow-y-auto rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900"
      >
        {pages.map((page, index) => (
          <PageWithPassage
            key={page.page_number}
            page={page}
            markRef={index === 0 ? marked : undefined}
          />
        ))}
      </div>
    </section>
  );
}

function PageWithPassage({
  page,
  markRef,
}: {
  page: SourcePage;
  markRef?: Ref<HTMLElement>;
}) {
  const { content, highlight_start: start, highlight_end: end } = page;
  return (
    <section aria-label={`Page ${page.page_number}`}>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Page {page.page_number}
      </h4>
      <p className="whitespace-pre-wrap text-sm">
        {content.slice(0, start)}
        <mark
          ref={markRef}
          className="rounded-sm bg-amber-100 text-inherit dark:bg-amber-900/60"
        >
          {content.slice(start, end)}
        </mark>
        {content.slice(end)}
      </p>
    </section>
  );
}

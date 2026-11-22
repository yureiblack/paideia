"use client";

// A citation opened in place: the pages a cited passage sits on, with the
// passage marked and scrolled into view, so it can be read in its context.
// Search results and summaries both open their citations with it.

import { useEffect, useRef, type Ref } from "react";

import { MathsText } from "@/components/maths-text";
import { Loading, LoadError } from "@/components/query-states";
import { usePreview } from "@/hooks/use-sources";
import { widen } from "@/lib/maths";
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

  if (preview.isPending) return <Loading what="the page" lines={4} />;
  if (preview.isError) {
    return (
      <LoadError
        what="the page"
        error={preview.error}
        onRetry={() => void preview.refetch()}
        retrying={preview.isFetching}
      />
    );
  }
  const { citation, pages } = preview.data;
  return (
    <section
      aria-label={`${citation.filename}, ${pagesLabel(citation.page_start, citation.page_end)}`}
      className="flex flex-col gap-2"
    >
      <p className="label text-ink-3">
        {citation.filename} · {pagesLabel(citation.page_start, citation.page_end)}
      </p>
      <div
        ref={scroller}
        className="relative flex max-h-[28rem] flex-col gap-4 overflow-y-auto bg-paper-2 px-5 py-4"
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
  const { content } = page;
  // Widened so that a formula is highlighted whole or not at all: half a
  // formula cannot be typeset.
  const [start, end] = widen(content, page.highlight_start, page.highlight_end);
  return (
    <section aria-label={`Page ${page.page_number}`}>
      <h4 className="label mb-1.5 text-ink-3">
        Page {page.page_number}
      </h4>
      <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink-2">
        <MathsText text={content.slice(0, start)} />
        <mark
          ref={markRef}
          className="bg-paper py-0.5 pr-0.5 pl-1.5 text-ink shadow-[inset_3px_0_0_var(--accent)] box-decoration-clone"
        >
          <MathsText text={content.slice(start, end)} />
        </mark>
        <MathsText text={content.slice(end)} />
      </p>
    </section>
  );
}

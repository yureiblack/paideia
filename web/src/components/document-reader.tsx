"use client";

// A document's own page, made for reading (decision record 28). A bar on
// top leads back to the environment and to Materials, brings back the
// contents rail that a desktop hides while reading, and holds the
// document's ••• menu. Under the document's name, four tabs: its text, page
// by page, its summary, its maths and its figures. The tab is part of the
// address (?tab=summary), so the Materials menu can open one directly.
//
// The text sits in one column of at most 640 pixels, each page with its
// folio. A desktop lists the pages beside it, marking the one in view; a
// phone turns the pages from a bar at the bottom. The page in view is
// remembered for Home's Keep reading, and an address ending in #page-3
// opens at that page. A figure the model has read (decision record 29) is
// drawn in its place in the page: its picture, its caption, what is written
// in it, and the model's description, marked as the model's.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { DocumentSummaryPanel } from "@/components/document-summary";
import { useReading } from "@/components/environment-shell";
import { sectionNumber } from "@/components/environment-tabs";
import { FiguresPanel } from "@/components/figure-reading";
import {
  documentDetails,
  DocumentActionsOutcome,
  DocumentMenu,
  DocumentNotes,
  JobStatus,
  readFromPictures,
  readingStep,
  StepLine,
  useDocumentActions,
  useDocumentJobs,
} from "@/components/materials";
import { MathsPanel } from "@/components/maths-reading";
import { MathsText } from "@/components/maths-text";
import { Loading, LoadError } from "@/components/query-states";
import { button } from "@/components/ui";
import { useDocuments, usePages, useRequestSummary, useSummary } from "@/hooks/use-documents";
import { useEnvironment } from "@/hooks/use-environments";
import { useJobs } from "@/hooks/use-jobs";
import { figureImageUrl } from "@/lib/api";
import { rememberReading } from "@/lib/local";
import { split } from "@/lib/maths";
import type { Document, DocumentPage, FigureTable, PageFigure } from "@/lib/types";

const TABS = [
  { id: "text", label: "Text" },
  { id: "summary", label: "Summary" },
  { id: "maths", label: "Maths" },
  { id: "figures", label: "Figures" },
] as const;
type TabId = (typeof TABS)[number]["id"];

// The tabs that read the document's pages again, offered once it is read.
const ONCE_READ: readonly TabId[] = ["maths", "figures"];

const tabFrom = (value: string | null | undefined): TabId =>
  TABS.find((t) => t.id === value)?.id ?? "text";

export function DocumentReader({
  environmentId,
  documentId,
}: {
  environmentId: string;
  documentId: string;
}) {
  const router = useRouter();
  const documents = useDocuments(environmentId);
  const [leaving, setLeaving] = useState(false);
  const document = documents.data?.find((d) => d.id === documentId);
  const materials = `/environments/${environmentId}/materials`;
  const gone = leaving && documents.data !== undefined && !document;

  // Deleted from its own page: back to Materials once it is gone.
  useEffect(() => {
    if (gone) router.replace(materials);
  }, [gone, materials, router]);

  if (document) {
    return (
      <DocumentPage
        environmentId={environmentId}
        document={document}
        onDelete={() => setLeaving(true)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <ReaderBar environmentId={environmentId} />
      {documents.isPending ? (
        <Loading what="the document" lines={4} />
      ) : documents.isError ? (
        <LoadError
          what="the document"
          error={documents.error}
          onRetry={() => void documents.refetch()}
          retrying={documents.isFetching}
        />
      ) : gone ? (
        <p role="status" className="text-base leading-[1.55] text-ink-2">
          Deleted. Back to Materials…
        </p>
      ) : (
        <div className="flex max-w-[640px] flex-col items-start gap-4">
          <h2 className="display text-[44px] leading-[0.95] tracking-[-0.03em] tab:text-[60px]">
            Document not found.
          </h2>
          <p className="text-base leading-[1.55] text-ink-2">
            It may have been deleted, or the link is wrong.
          </p>
          <Link href={materials} className={button.link}>
            <span aria-hidden>← </span>Back to Materials
          </Link>
        </div>
      )}
    </div>
  );
}

// The bar across the top of the page: where the document sits, the
// contents rail on a desktop, and the document's menu. It reaches to the
// edges of the shell's column, over its padding.
function ReaderBar({
  environmentId,
  filename,
  menu,
}: {
  environmentId: string;
  filename?: string;
  menu?: ReactNode;
}) {
  const environment = useEnvironment(environmentId);
  const { reading, contentsShown, toggleContents } = useReading();
  const base = `/environments/${environmentId}`;
  return (
    <div className="-mx-5 -mt-6 flex min-h-14 items-center gap-4 border-b border-rule px-5 py-2 tab:-mx-8 tab:-mt-8 tab:px-8 desk:-mx-12 desk:-mt-9 desk:px-12">
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="label flex min-w-0 items-center gap-3 text-ink-2">
          <li className="hidden min-w-0 tab:block">
            <Link href={base} className="block truncate hover:text-ink">
              <span aria-hidden>← </span>
              {environment.data?.name ?? "Overview"}
            </Link>
          </li>
          <li className="flex shrink-0 items-center gap-3">
            <span aria-hidden className="hidden text-ink-3 tab:inline">
              /
            </span>
            <Link href={`${base}/materials`} className="hover:text-ink">
              <span aria-hidden className="tab:hidden">
                ←{" "}
              </span>
              <span aria-hidden className="max-tab:hidden">
                {sectionNumber("Materials")}{" "}
              </span>
              Materials
            </Link>
          </li>
          {filename && (
            <li className="flex min-w-0 items-center gap-3">
              <span aria-hidden className="text-ink-3">
                /
              </span>
              <span aria-current="page" className="truncate text-ink">
                {filename}
              </span>
            </li>
          )}
        </ol>
      </nav>
      {reading && (
        <button
          type="button"
          onClick={toggleContents}
          className="label hidden shrink-0 items-center gap-2 border border-ink px-2.5 py-1.5 hover:bg-ink hover:text-paper desk:inline-flex"
        >
          {contentsShown ? (
            "Hide contents"
          ) : (
            <>
              Show contents <span aria-hidden>≡</span>
            </>
          )}
        </button>
      )}
      {menu}
    </div>
  );
}

function DocumentPage({
  environmentId,
  document,
  onDelete,
}: {
  environmentId: string;
  document: Document;
  onDelete: () => void;
}) {
  const actions = useDocumentActions(environmentId, document, onDelete);
  const job = useDocumentJobs(environmentId).get(document.id);
  const { reading, contentsShown } = useReading();
  const params = useSearchParams();
  const asked = tabFrom(params?.get("tab"));
  // A tab chosen here holds until the address names another one, as going
  // back does.
  const [chosen, setChosen] = useState<{ tab: TabId; from: TabId } | null>(null);
  const wanted = chosen && chosen.from === asked ? chosen.tab : asked;
  const ready = document.status === "ready";
  const tabs = TABS.filter((t) => ready || !ONCE_READ.includes(t.id));
  const tab = tabs.some((t) => t.id === wanted) ? wanted : "text";
  const step = readingStep(document, job);

  function choose(next: TabId) {
    setChosen({ tab: next, from: asked });
    const path = window.location.pathname;
    window.history.replaceState(null, "", next === "text" ? path : `${path}?tab=${next}`);
  }

  // Arrow keys move between the tabs, as in any tab list.
  function handleKey(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((t) => t.id === tab);
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    const next = tabs[(moves[event.key] + tabs.length) % tabs.length];
    choose(next.id);
    event.currentTarget.querySelector<HTMLElement>(`#document-tab-${next.id}`)?.focus();
  }

  return (
    <div className="flex flex-col">
      <ReaderBar
        environmentId={environmentId}
        filename={document.filename}
        menu={<DocumentMenu actions={actions} />}
      />
      <div className="flex flex-col gap-6 pt-7 tab:pt-10 desk:grid desk:grid-cols-[minmax(160px,240px)_minmax(0,640px)_minmax(0,1fr)] desk:gap-x-10 desk:gap-y-7">
        <header className="flex min-w-0 flex-col gap-3 desk:col-start-2 desk:row-start-1">
          <p className="label max-tab:sr-only">
            <span aria-hidden>{sectionNumber("Materials")} / </span>Materials / Document
          </p>
          <h2 className="display text-[48px] leading-[0.95] tracking-[-0.03em] break-words tab:text-[64px]">
            {document.filename}
          </h2>
          <p className="text-[13px] leading-[1.4] text-ink-2">{documentMeta(document)}</p>
          {step !== null ? (
            <StepLine step={step} filename={document.filename} />
          ) : (
            job && (
              <div className="max-w-80">
                <JobStatus job={job} />
              </div>
            )
          )}
          <DocumentNotes document={document} />
          <DocumentActionsOutcome actions={actions} />
        </header>

        <div
          role="tablist"
          aria-label="Document"
          onKeyDown={handleKey}
          className="flex gap-7 border-b border-ink desk:col-start-2 desk:row-start-2"
        >
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`document-tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={tab === t.id ? `document-panel-${t.id}` : undefined}
              tabIndex={tab === t.id ? 0 : -1}
              onClick={() => choose(t.id)}
              className={`label -mb-px pb-2.5 ${
                tab === t.id
                  ? "text-ink shadow-[inset_0_-2px_0_var(--accent)]"
                  : "text-ink-2 hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "text" && <TextTab environmentId={environmentId} document={document} />}
        {tab === "summary" && <SummaryTab environmentId={environmentId} document={document} />}
        {tab === "maths" && (
          <Panel tab="maths">
            <MathsPanel document={document} environmentId={environmentId} />
          </Panel>
        )}
        {tab === "figures" && (
          <Panel tab="figures">
            <FiguresPanel document={document} environmentId={environmentId} />
          </Panel>
        )}

        {reading && !contentsShown && (
          <div className="hidden flex-col gap-2 min-[1280px]:flex desk:col-start-3 desk:row-start-3">
            <p aria-hidden className="label text-ink-3">
              Focus
            </p>
            <p className="max-w-56 text-[13px] leading-[1.4] text-ink-2">
              The rail is hidden while you read. Show contents brings it back.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// "4 pages · 478 KB · added 10 Nov 2026 · read in full", and for a scan
// "· 4 pages read from pictures".
function documentMeta(document: Document): string {
  const parts: string[] = [];
  const pages = document.page_count;
  if (pages !== null) parts.push(`${pages} ${pages === 1 ? "page" : "pages"}`);
  parts.push(documentDetails(document));
  switch (document.status) {
    case "uploaded":
      parts.push("waiting to be read");
      break;
    case "processing":
      parts.push("being read");
      break;
    case "failed":
      parts.push("could not be read");
      break;
    case "ready": {
      const withText = document.pages_with_text;
      if (withText === 0) parts.push("no text found");
      else if (withText !== null && pages !== null && withText < pages) {
        parts.push(`text on ${withText} of ${pages} pages`);
      } else parts.push("read in full");
      const pictures = readFromPictures(document);
      if (pictures) parts.push(pictures);
    }
  }
  return parts.join(" · ");
}

// One tab's content, in the reading column.
function Panel({ tab, children }: { tab: TabId; children: ReactNode }) {
  return (
    <div
      role="tabpanel"
      id={`document-panel-${tab}`}
      aria-labelledby={`document-tab-${tab}`}
      className="min-w-0 desk:col-start-2 desk:row-start-3"
    >
      {children}
    </div>
  );
}

function TextTab({ environmentId, document }: { environmentId: string; document: Document }) {
  if (document.status !== "ready") {
    return (
      <Panel tab="text">
        <p className="max-w-[640px] text-base leading-[1.55] text-ink-2">
          {document.status === "failed"
            ? "This document could not be read, so there is no text to show. Try again from its menu, or upload a new version."
            : "The text shows here once the document has been read."}
        </p>
      </Panel>
    );
  }
  // Read again (a new version, its maths or its figures), the document
  // changes: its pages are asked for afresh.
  return <Pages key={document.updated_at} environmentId={environmentId} document={document} />;
}

// The page an address ends with, as in #page-3.
function pageInAddress(): number | null {
  const match = /^#page-(\d+)$/.exec(window.location.hash);
  return match ? Number(match[1]) : null;
}

function Pages({ environmentId, document }: { environmentId: string; document: Document }) {
  const pages = usePages(document.id);
  const [current, setCurrent] = useState(1);
  const column = useRef<HTMLDivElement>(null);
  const ending = useRef<HTMLDivElement>(null);
  const opened = useRef(false);

  // Open at the page the address names, once the text is in.
  useEffect(() => {
    if (!pages.data || opened.current) return;
    opened.current = true;
    const page = pageInAddress();
    if (page) window.document.getElementById(`page-${page}`)?.scrollIntoView();
  }, [pages.data]);

  // The page in view: the first one crossing a band near the top of the
  // window; between two pages, the last one found stays. A last page too
  // short to reach the band is in view once the end of the text is.
  useEffect(() => {
    const root = column.current;
    const end = ending.current;
    if (!pages.data || !root || !end || typeof IntersectionObserver === "undefined") return;
    const sections = Array.from(root.querySelectorAll<HTMLElement>("section[data-page]"));
    const last = Number(sections.at(-1)?.dataset.page ?? 1);
    const inBand = new Set<number>();
    let found = Number(sections[0]?.dataset.page ?? 1);
    let atEnd = false;
    const show = () => setCurrent(atEnd ? last : found);

    const band = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const page = Number((entry.target as HTMLElement).dataset.page);
          if (entry.isIntersecting) inBand.add(page);
          else inBand.delete(page);
        }
        if (inBand.size > 0) found = Math.min(...inBand);
        show();
      },
      { rootMargin: "-15% 0px -75% 0px" },
    );
    // The end counts only once the reader has scrolled: a short document
    // seen whole opens at its first page.
    const ends = new IntersectionObserver(([entry]) => {
      atEnd = entry.isIntersecting && window.scrollY > 0;
      show();
    });
    sections.forEach((section) => band.observe(section));
    ends.observe(end);
    return () => {
      band.disconnect();
      ends.disconnect();
    };
  }, [pages.data]);

  // Where the reader is, for Home's Keep reading.
  const total = pages.data?.length ?? 0;
  useEffect(() => {
    if (total === 0) return;
    rememberReading({
      environmentId,
      documentId: document.id,
      filename: document.filename,
      page: current,
      pages: total,
    });
  }, [environmentId, document.id, document.filename, current, total]);

  if (pages.isPending) {
    return (
      <Panel tab="text">
        <Loading what="the text" lines={6} />
      </Panel>
    );
  }
  if (pages.isError) {
    return (
      <Panel tab="text">
        <LoadError
          what="the text"
          error={pages.error}
          onRetry={() => void pages.refetch()}
          retrying={pages.isFetching}
        />
      </Panel>
    );
  }

  return (
    <>
      <nav
        aria-label="Pages"
        className="hidden desk:sticky desk:top-6 desk:col-start-1 desk:row-start-3 desk:block desk:max-h-[calc(100vh-3rem)] desk:self-start desk:overflow-y-auto"
      >
        <p aria-hidden className="label pb-2 text-ink-3">
          Pages
        </p>
        <ol className="flex flex-col">
          {pages.data.map((page) => {
            const n = page.page_number;
            const here = n === current;
            return (
              <li key={n} className="border-b border-rule">
                <a
                  href={`#page-${n}`}
                  aria-current={here ? "location" : undefined}
                  className="group flex items-start gap-3 py-2.5"
                >
                  <span
                    className={`label flex h-[18px] min-w-[22px] shrink-0 items-center justify-center px-1 ${
                      here ? "bg-accent text-on-accent" : "text-ink-3 group-hover:text-ink"
                    }`}
                  >
                    <span className="sr-only">Page</span> {n}
                  </span>{" "}
                  <span
                    className={`line-clamp-2 text-[15px] leading-[1.3] ${
                      here ? "font-medium text-ink" : "text-ink-2 group-hover:text-ink"
                    }`}
                  >
                    {firstWords(indexText(page)) || "No text"}
                  </span>
                </a>
              </li>
            );
          })}
        </ol>
      </nav>

      <Panel tab="text">
        <div ref={column} className="flex max-w-[640px] flex-col gap-12">
          {pages.data.map((page) => (
            <PageText key={page.page_number} page={page} total={total} />
          ))}
        </div>
        <div ref={ending} aria-hidden />
        <PageTurner current={current} total={total} />
      </Panel>
    </>
  );
}

function PageText({ page, total }: { page: DocumentPage; total: number }) {
  const n = page.page_number;
  return (
    <section
      aria-label={`Page ${n}`}
      id={`page-${n}`}
      data-page={n}
      className="flex scroll-mt-6 flex-col gap-4"
    >
      <div className="flex items-center gap-4">
        <h3 className="label shrink-0 text-ink-3">
          Page {n} of {total}
        </h3>
        <span aria-hidden className="h-px flex-1 bg-rule" />
      </div>
      {page.content.trim() ? (
        piecesOf(page).map((piece) =>
          piece.kind === "text" ? (
            <div
              key={piece.at}
              className="text-[18px] leading-[1.7] break-words whitespace-pre-wrap"
            >
              <MathsText text={piece.text} />
            </div>
          ) : (
            <FigureInPage key={piece.figure.id} figure={piece.figure} page={n} />
          ),
        )
      ) : (
        <p className="text-base text-ink-3">No text on this page.</p>
      )}
    </section>
  );
}

// A page's content in the order it is read: ordinary text, and each figure
// read in it in place of its passage. A page without figures is one piece,
// its content as it is.
type Piece =
  | { kind: "text"; text: string; at: number }
  | { kind: "figure"; figure: PageFigure };

function piecesOf(page: DocumentPage): Piece[] {
  const { content } = page;
  const figures = [...(page.figures ?? [])].sort((a, b) => a.start - b.start);
  if (!figures.length) return [{ kind: "text", text: content, at: 0 }];
  const pieces: Piece[] = [];
  // The paragraph breaks around a figure's passage give way to the gap
  // around the figure.
  const text = (from: number, to: number) => {
    const body = content.slice(from, to).replace(/^\n+|\n+$/g, "");
    if (body.trim()) pieces.push({ kind: "text", text: body, at: from });
  };
  let at = 0;
  for (const figure of figures) {
    const start = Math.max(at, unitIndex(content, figure.start));
    const end = Math.max(start, unitIndex(content, figure.end));
    text(at, start);
    pieces.push({ kind: "figure", figure });
    at = end;
  }
  text(at, content.length);
  return pieces;
}

// The API counts a figure's place in its page by code point, as Python
// does, while a JavaScript string counts UTF-16 units: a character beyond
// the first 65,536, such as the mathematical italic 𝑥 that a PDF's maths
// fonts often give, is two of them. So a place is converted before slicing.
function unitIndex(text: string, points: number): number {
  let units = 0;
  for (let seen = 0; seen < points && units < text.length; seen += 1) {
    units += (text.codePointAt(units) ?? 0) > 0xffff ? 2 : 1;
  }
  return units;
}

// A page as the list of pages sums it up: each figure by its caption, not
// the passage the model wrote for it.
function indexText(page: DocumentPage): string {
  return piecesOf(page)
    .map((piece) => (piece.kind === "text" ? piece.text : (piece.figure.caption ?? "")))
    .filter(Boolean)
    .join("\n\n");
}

// A figure read by the model, in its place in the page. Everything read in
// it is its legend, so all of it is the figcaption, which HTML allows only
// as a figure's first or last element: the caption, what is written in it,
// its tables, and the model's description, marked as the model's, since
// nothing can check it against the picture but the reader.
function FigureInPage({ figure, page }: { figure: PageFigure; page: number }) {
  return (
    <figure aria-label={figure.caption ?? "A figure"} className="my-2 flex flex-col gap-4">
      {/* The picture is drawn by the API from the document's file, on another
          origin; Next's image optimiser would only fetch it again. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={figureImageUrl(figure.id)}
        alt={figure.caption ?? `A figure on page ${page}`}
        loading="lazy"
        className="block h-auto max-w-full self-start"
      />
      <figcaption className="flex flex-col gap-4 border-t border-rule pt-3">
        {figure.caption && <p className="text-[15px] leading-[1.55]">{figure.caption}</p>}
        {figure.text.length > 0 && (
          <p className="text-[13px] leading-[1.4] text-ink-2">
            <MathsText text={figure.text.join(" · ")} />
          </p>
        )}
        {figure.tables.map((table, index) => (
          <ReadTable key={index} table={table} />
        ))}
        <div className="flex flex-col gap-1.5">
          <p className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
            <span className="label text-ink-2">Described by the model</span>
            <span className="text-[13px] leading-[1.4] text-ink-2">
              Check it against the picture.
            </span>
          </p>
          <p className="text-[18px] leading-[1.7] break-words">
            <MathsText text={figure.description} />
          </p>
        </div>
      </figcaption>
    </figure>
  );
}

// A table read in a figure, its first row as the header. A wide one
// scrolls on its own on a phone instead of widening the page.
function ReadTable({ table }: { table: FigureTable }) {
  if (!table.rows.length) return null;
  const [header, ...rows] = table.rows;
  const cell = "px-2 py-1.5 align-top first:pl-0 last:pr-0";
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-[13px] leading-[1.4] tabular-nums">
        {table.title && (
          <caption className="pb-1.5 text-left text-ink-2">
            <MathsText text={table.title} />
          </caption>
        )}
        <thead className="border-b border-ink">
          <tr>
            {header.map((value, index) => (
              <th key={index} scope="col" className={`font-medium ${cell}`}>
                <MathsText text={value} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-rule">
              {row.map((value, index) => (
                <td key={index} className={cell}>
                  <MathsText text={value} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// The first words of a page, for the list of pages: its first paragraph,
// with any formula shown as an ellipsis, cut at a word.
export function firstWords(content: string, most = 80): string {
  const prose = split(content)
    .map((segment) => (segment.kind === "prose" ? segment.body : " … "))
    .join("");
  const first = (prose.trim().split("\n")[0] ?? "").replace(/\s+/g, " ").trim();
  if (first.length <= most) return first;
  const cut = first.slice(0, most);
  const space = cut.lastIndexOf(" ");
  return `${(space > most / 2 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

// A phone or tablet turns the pages from a bar at the bottom of the window.
function PageTurner({ current, total }: { current: number; total: number }) {
  if (total < 2) return null;
  const link = "label flex min-h-11 items-center gap-2 hover:underline hover:decoration-accent";
  return (
    <nav
      aria-label="Turn the page"
      className="sticky bottom-0 -mx-5 mt-12 flex items-center justify-between gap-4 border-t border-ink bg-paper px-5 tab:-mx-8 tab:px-8 desk:hidden"
    >
      <div className="flex items-center gap-2 text-ink-3">
        {current > 1 ? (
          <a href={`#page-${current - 1}`} aria-label="Previous page" className={`${link} pr-1 text-ink`}>
            ‹
          </a>
        ) : (
          <span aria-hidden className="label">
            ‹
          </span>
        )}
        <span className="label">
          Page {current} of {total}
        </span>
      </div>
      {current < total && (
        <a href={`#page-${current + 1}`} aria-label="Next page" className={link}>
          Page {current + 1} <span aria-hidden>›</span>
        </a>
      )}
    </nav>
  );
}

function SummaryTab({ environmentId, document }: { environmentId: string; document: Document }) {
  return (
    <Panel tab="summary">
      {document.status === "ready" ? (
        <Summary environmentId={environmentId} document={document} />
      ) : (
        <p className="max-w-[640px] text-base leading-[1.55] text-ink-2">
          The summary is written once the document has been read.
        </p>
      )}
    </Panel>
  );
}

// A document read before summaries were written by themselves has none
// until asked; opening this tab asks, once. While the environment has work
// in the background, that work may be about to write it, so the tab waits
// for it to finish before asking.
function Summary({ environmentId, document }: { environmentId: string; document: Document }) {
  const summary = useSummary(environmentId, document);
  const ask = useRequestSummary(environmentId, document.id);
  const jobs = useJobs(environmentId);
  const asked = useRef(false);
  const quiet =
    jobs.isSuccess && !jobs.data.some((j) => j.status === "queued" || j.status === "running");
  const missing = summary.data === null && quiet;
  const askForSummary = ask.mutate;

  useEffect(() => {
    if (!missing || asked.current) return;
    asked.current = true;
    askForSummary();
  }, [missing, askForSummary]);

  return (
    <DocumentSummaryPanel
      environmentId={environmentId}
      summary={summary.data}
      loadError={summary.error}
      onReload={() => void summary.refetch()}
      reloading={summary.isFetching}
      onTryAgain={() => ask.mutate()}
      retrying={ask.isPending}
      retryError={ask.error}
    />
  );
}

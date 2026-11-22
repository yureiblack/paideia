"use client";

// The Materials tab: add PDFs to an environment, see each document's state
// and the step its reading has got to, and open a document's own page to
// read it, its summary or its maths (decision record 28). Each row keeps a
// ••• menu for a new version, Try again and Delete, and shows the opening of
// the document's summary. The first upload is explained in a note beside the
// table while it is being read.
//
// The pieces a document's own page shares with its row are here too: its
// state, the step its background work is at, and its menu.

import Link from "next/link";
import { useCallback, useRef, useState, type ChangeEvent } from "react";

import { sectionNumber } from "@/components/environment-tabs";
import { MaterialUpdates } from "@/components/material-updates";
import { MathsText } from "@/components/maths-text";
import { Note } from "@/components/note";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { UploadZone } from "@/components/upload-zone";
import { button, Mark, Opening, useDismiss } from "@/components/ui";
import {
  useDeleteDocument,
  useDocuments,
  useReprocessDocument,
  useSummary,
} from "@/hooks/use-documents";
import { useJobs } from "@/hooks/use-jobs";
import { useNewVersion, useUpdates } from "@/hooks/use-updates";
import { formatBytes, formatDate } from "@/lib/format";
import { InWords } from "@/lib/words";
import {
  MAX_UPLOAD_MB,
  type CurrentSummary,
  type Document,
  type Job,
} from "@/lib/types";

export function Materials({ environmentId }: { environmentId: string }) {
  const documents = useDocuments(environmentId);
  const working = useDocumentJobs(environmentId);
  const kicker = (
    <>
      <span aria-hidden>{sectionNumber("Materials")} / </span>Materials
    </>
  );

  if (documents.data?.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <p className="label max-tab:sr-only">{kicker}</p>
        <Empty title="No documents yet.">
          Upload lecture notes, chapters or problem sheets as PDFs. Each is read as soon as it
          arrives.
        </Empty>
        <UploadZone environmentId={environmentId} variant="band" />
        <MaterialUpdates environmentId={environmentId} />
      </div>
    );
  }

  // Shown while a document is still being read, or its summary, concepts,
  // map and roadmap are still being made from it.
  const settling = (documents.data ?? []).some(
    (d) => isBusy(d) || readingStep(d, working.get(d.id)) !== null,
  );

  return (
    <div className="flex flex-col gap-9">
      <Opening
        kicker={kicker}
        headline={<MaterialsHeadline documents={documents.data} />}
        aside={
          <>
            <p className="text-[15px] leading-[1.55] text-ink-2">
              PDFs up to {MAX_UPLOAD_MB} MB, read page by page as soon as they arrive.
            </p>
            <UploadZone environmentId={environmentId} variant="button" />
          </>
        }
      />

      <MaterialUpdates environmentId={environmentId} />

      {documents.isPending ? (
        <Loading what="materials" lines={3} />
      ) : documents.isError ? (
        <LoadError
          what="materials"
          error={documents.error}
          onRetry={() => void documents.refetch()}
          retrying={documents.isFetching}
        />
      ) : (
        <div className="flex flex-col">
          <div aria-hidden className="label hidden gap-4 border-b border-ink pb-2 text-ink-3 tab:flex">
            <span className="flex-1">Document</span>
            <span className="w-16">Pages</span>
            <span className="w-48">Status</span>
            <span className="w-36" />
          </div>
          <ul aria-label="Documents">
            {documents.data.map((document) => (
              <li key={document.id} className="border-b border-rule">
                <DocumentRow
                  document={document}
                  environmentId={environmentId}
                  job={working.get(document.id)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {settling && (
        <Note id="first-upload" title="First upload — what happens now" guideStep={2}>
          Each PDF is read page by page and split into passages; search works from then on.
          Then its summary is written, its concepts are found, and the knowledge map and roadmap
          are updated. You can leave this page: the rail shows the progress.
        </Note>
      )}
    </div>
  );
}

// "Four documents. One is being read."
function MaterialsHeadline({ documents }: { documents: Document[] | undefined }) {
  if (!documents) return <span aria-hidden className="placeholder block h-[0.9em] w-2/3" />;
  if (documents.length === 0) return "No documents yet.";
  const n = documents.length;
  const busy = documents.filter(isBusy).length;
  const first = `${InWords(n)} ${n === 1 ? "document" : "documents"}.`;
  if (busy === 0) return first;
  return (
    <>
      {first}
      <br />
      {n === 1 ? "It is" : busy === 1 ? "One is" : `${InWords(busy)} are`} being read.
    </>
  );
}

function DocumentRow({
  document,
  environmentId,
  job,
}: {
  document: Document;
  environmentId: string;
  job: Job | undefined;
}) {
  const actions = useDocumentActions(environmentId, document);
  const summary = useSummary(environmentId, document);
  const [menuOpen, setMenuOpen] = useState(false);
  const ready = document.status === "ready";
  const href = documentHref(environmentId, document.id);
  const step = readingStep(document, job);

  return (
    <article className={`flex flex-col gap-3 py-4 ${menuOpen ? "bg-paper-2 tab:-mx-3 tab:px-3" : ""}`}>
      <div className="flex flex-col gap-2 tab:flex-row tab:items-start tab:gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="display truncate text-2xl leading-none tracking-[-0.015em]">{document.filename}</h3>
          <p className="text-[13px] leading-[1.4] text-ink-2">{documentDetails(document)}</p>
        </div>
        <p className="label hidden w-16 pt-1.5 tab:block">
          {document.page_count ?? "–"}
        </p>
        <div className="tab:w-48 tab:pt-1">
          {job ? <JobStatus job={job} /> : <StatusBadge document={document} pagesColumn />}
        </div>
        <div className="flex items-center gap-4 tab:w-36 tab:justify-end tab:pt-0.5">
          {ready && (
            <Link href={href} aria-label={`Read ${document.filename}`} className={button.link}>
              Read <span aria-hidden>→</span>
            </Link>
          )}
          <DocumentMenu
            actions={actions}
            onOpenChange={setMenuOpen}
            links={
              ready
                ? [
                    { label: summaryLabel(summary.data), href: `${href}?tab=summary` },
                    { label: "Read the maths", href: `${href}?tab=maths` },
                  ]
                : []
            }
          />
        </div>
      </div>

      {step !== null && <StepLine step={step} filename={document.filename} />}

      <DocumentNotes document={document} />

      {summary.data?.status === "ready" && summary.data.overview && (
        <p className="line-clamp-2 max-w-[640px] text-[15px] leading-[1.55] text-ink-2">
          <MathsText text={summary.data.overview} />
        </p>
      )}

      <DocumentActionsOutcome actions={actions} />
    </article>
  );
}

// A document's own page, where it is read.
export function documentHref(environmentId: string, documentId: string): string {
  return `/environments/${environmentId}/materials/${documentId}`;
}

export function isBusy(document: Document): boolean {
  return document.status === "uploaded" || document.status === "processing";
}

// "478 KB · added 10 Nov 2026"
export function documentDetails(document: Document): string {
  return `${formatBytes(document.size_bytes)} · added ${formatDate(document.created_at)}`;
}

// What the summary item says, by where the summary stands.
function summaryLabel(summary: CurrentSummary | null | undefined) {
  switch (summary?.status) {
    case "pending":
    case "generating":
      return "Writing summary…";
    case "ready":
      return "Show summary";
    case "failed":
      return "Summary failed";
    default:
      return "Summarize";
  }
}

// --- Background work --------------------------------------------------------

// Each document's queued or running job, if any. A job names the material
// update it carries out, and the update names its document. Of a document's
// jobs, the one running is shown, or else the first still waiting in its
// chain: its maths, then its reading, then what is made from it.
const CHAIN = ["maths", "read", "derive"];

function rank(job: Job): number {
  if (job.status === "running") return 0;
  const place = CHAIN.indexOf(job.kind);
  return 1 + (place < 0 ? CHAIN.length : place);
}

export function useDocumentJobs(environmentId: string): Map<string, Job> {
  const jobs = useJobs(environmentId);
  const updates = useUpdates(environmentId);
  const documentOf = new Map(
    (updates.data ?? []).map((u) => [u.id, u.document_id] as const),
  );
  const found = new Map<string, Job>();
  for (const job of jobs.data ?? []) {
    if (job.status !== "queued" && job.status !== "running") continue;
    const documentId = job.update_id ? documentOf.get(job.update_id) : null;
    if (!documentId) continue;
    const held = found.get(documentId);
    if (!held || rank(job) < rank(held)) found.set(documentId, job);
  }
  return found;
}

// The steps a document goes through once uploaded, as the step line shows
// them, and which of them each step of its jobs belongs to
// (api/app/services/jobs.py, document_steps).
export const READING_STEPS = ["Reading", "Summary", "Concepts", "Knowledge map", "Roadmap"];

const STEP_OF: Record<string, number> = {
  "Reading the document": 0,
  "Queuing its concepts": 1,
  "Writing its summary": 1,
  "Updating the environment summary": 1,
  "Extracting concepts": 2,
  "Updating the knowledge map": 3,
  "Updating the roadmap": 4,
  "Summing up what changed": 4,
};

// Which of READING_STEPS a document is at, or null when it is at none:
// settled, or busy with work outside them, such as reading its maths.
export function readingStep(document: Document, job: Job | undefined): number | null {
  if (job?.kind === "read") return 0;
  if (job?.kind === "derive") return job.step ? (STEP_OF[job.step] ?? 1) : 1;
  if (job) return null;
  return isBusy(document) ? 0 : null;
}

// READING → SUMMARY → CONCEPTS → KNOWLEDGE MAP → ROADMAP, the current step
// in ink with the mark.
export function StepLine({ step, filename }: { step: number; filename: string }) {
  return (
    <ol
      aria-label={`Steps for ${filename}`}
      className="label flex flex-wrap items-center gap-x-2.5 gap-y-1"
    >
      {READING_STEPS.map((name, index) => (
        <li
          key={name}
          aria-current={index === step ? "step" : undefined}
          className={`flex items-center gap-2.5 ${index === step ? "text-ink" : "text-ink-3"}`}
        >
          {index > 0 && (
            <span aria-hidden className="text-ink-3">
              →
            </span>
          )}
          {index === step && <Mark />}
          {name}
        </li>
      ))}
    </ol>
  );
}

// The step a document's job is at, in words, with how far it has got.
export function JobStatus({ job }: { job: Job }) {
  const running = job.status === "running";
  const state = job.cancel_requested
    ? "Stopping after this step…"
    : running
      ? (job.step ?? "Starting…")
      : job.attempts > 0
        ? "Waiting to try again"
        : "Queued";
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[15px] leading-[1.4]">{state}</p>
      <div
        role="progressbar"
        aria-label={job.title}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={job.progress}
        className="h-1 overflow-hidden bg-paper-2"
      >
        <div className="h-full bg-ink" style={{ width: `${running ? Math.max(job.progress, 3) : 0}%` }} />
      </div>
    </div>
  );
}

const BADGE = {
  uploaded: { label: "Waiting", style: "text-ink-2" },
  processing: { label: "Reading…", style: "text-ink" },
  ready: { label: "Ready", style: "text-ink-2" },
  failed: { label: "Failed", style: "text-ink" },
};

// "Ready · 3 pages". Where the pages have their own column (pagesColumn),
// the count shows here only on a phone, which has no columns.
export function StatusBadge({
  document,
  pagesColumn = false,
}: {
  document: Document;
  pagesColumn?: boolean;
}) {
  const { label, style } = BADGE[document.status];
  const pages =
    document.status === "ready" && document.page_count !== null
      ? ` · ${document.page_count} ${document.page_count === 1 ? "page" : "pages"}`
      : "";
  return (
    <span className={`label inline-flex shrink-0 items-center gap-1.5 ${style}`}>
      {document.status === "failed" && <Mark />}
      {label}
      {pages && (pagesColumn ? <span className="tab:hidden">{pages}</span> : pages)}
    </span>
  );
}

// Why a document has no text, or less than it should.
export function DocumentNotes({ document }: { document: Document }) {
  const notes: string[] = [];
  if (document.status === "failed" && document.error) notes.push(document.error);
  if (document.status === "ready" && document.pages_with_text === 0) {
    notes.push("No text was found. It may be a scanned PDF.");
  }
  if (document.repaired) {
    notes.push(
      "This file was damaged and has been repaired. Some content may be missing.",
    );
  }
  if (notes.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1 text-[15px] leading-[1.55] text-ink-2">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}

// --- A document's menu ------------------------------------------------------

// What a document's ••• menu does: a new version, Try again for one that
// failed, and Delete once confirmed. onDelete is told as the deletion is
// sent, so a page about the document can leave once it is gone.
export function useDocumentActions(
  environmentId: string,
  document: Document,
  onDelete?: () => void,
) {
  const reprocess = useReprocessDocument(environmentId);
  const newVersion = useNewVersion(environmentId);
  const remove = useDeleteDocument(environmentId);
  const versionInput = useRef<HTMLInputElement>(null);
  const [confirming, setConfirming] = useState(false);

  function handleVersion(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    newVersion.mutate({ documentId: document.id, file });
  }

  function confirmDelete() {
    setConfirming(false);
    onDelete?.();
    remove.mutate(document.id);
  }

  return {
    document,
    canVersion: !isBusy(document),
    versionInput,
    handleVersion,
    newVersion,
    reprocess,
    remove,
    confirming,
    setConfirming,
    confirmDelete,
  };
}

export type DocumentActions = ReturnType<typeof useDocumentActions>;

const menuItem =
  "label flex min-h-11 w-full items-center gap-2 border-b border-rule px-3.5 text-left last:border-b-0 hover:bg-ink hover:text-paper disabled:opacity-40 tab:min-h-10";

// The ••• button and its menu. links come first: places to go, such as the
// document's summary.
export function DocumentMenu({
  actions,
  links = [],
  onOpenChange,
}: {
  actions: DocumentActions;
  links?: { label: string; href: string }[];
  onOpenChange?: (open: boolean) => void;
}) {
  const { document, canVersion, versionInput, newVersion, reprocess, remove } = actions;
  const [open, setOpenState] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  const close = useCallback(() => setOpen(false), [setOpen]);
  useDismiss(menu, open, close, trigger);

  return (
    <div ref={menu} className="relative">
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={`More for ${document.filename}`}
        className={`label flex size-10 items-center justify-center border border-rule tracking-normal tab:size-8 ${
          open ? "border-ink bg-ink text-paper" : "hover:bg-ink hover:text-paper"
        }`}
      >
        •••
      </button>
      {open && (
        <div className="absolute top-full right-0 z-20 mt-1 flex w-64 flex-col border border-ink bg-paper">
          {links.map((link) => (
            <Link key={link.href} href={link.href} onClick={close} className={menuItem}>
              <span className="flex-1">{link.label}</span>
              <span aria-hidden>→</span>
            </Link>
          ))}
          {canVersion && (
            <button
              type="button"
              onClick={() => {
                close();
                versionInput.current?.click();
              }}
              disabled={newVersion.isPending}
              className={menuItem}
            >
              <span className="flex-1">{newVersion.isPending ? "Uploading…" : "Upload a new version"}</span>
              <span aria-hidden>→</span>
            </button>
          )}
          {document.status === "failed" && (
            <button
              type="button"
              onClick={() => {
                close();
                reprocess.mutate(document.id);
              }}
              disabled={reprocess.isPending}
              className={menuItem}
            >
              <span className="flex-1">Try again</span>
              <span aria-hidden>→</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              close();
              actions.setConfirming(true);
            }}
            disabled={remove.isPending}
            className={menuItem}
          >
            <Mark />
            <span className="flex-1">{remove.isPending ? "Deleting…" : "Delete"}</span>
            <span aria-hidden>→</span>
          </button>
        </div>
      )}
      {canVersion && (
        <input
          ref={versionInput}
          type="file"
          accept="application/pdf,.pdf"
          onChange={actions.handleVersion}
          className="hidden"
          aria-label={`Choose a new version of ${document.filename}`}
        />
      )}
    </div>
  );
}

// What the menu leads to, shown in the page: Delete's question, and why an
// action failed.
export function DocumentActionsOutcome({ actions }: { actions: DocumentActions }) {
  const { document, confirming, setConfirming, confirmDelete } = actions;
  const error = actions.reprocess.error ?? actions.remove.error ?? actions.newVersion.error;
  return (
    <>
      {confirming && (
        <div
          role="alertdialog"
          aria-label={`Delete ${document.filename}`}
          className="flex flex-col gap-3 border border-ink p-4 tab:flex-row tab:items-center tab:gap-5"
        >
          <p className="flex-1 text-base leading-[1.55]">
            Delete “{document.filename}”? This cannot be undone.
          </p>
          <div className="flex items-center gap-5">
            <button type="button" onClick={confirmDelete} className={button.danger}>
              Delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className={button.link}>
              Keep it
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="flex items-start gap-2 text-[15px] leading-[1.45]">
          <span className="pt-[7px]">
            <Mark />
          </span>
          {error.message}
        </p>
      )}
    </>
  );
}

"use client";

// The Materials tab: upload PDFs into an environment, or a new version of
// one, watch each change go through step by step and what it changed, retry
// failures, delete documents, read the extracted text page by page, and ask
// the local language model for a cited summary of any document. Each
// document shows the opening of its summary, and the step its background
// work is at while it runs.

import { useCallback, useRef, useState, type ChangeEvent } from "react";

import { DocumentSummaryPanel } from "@/components/document-summary";
import { MaterialUpdates } from "@/components/material-updates";
import { MathsPanel } from "@/components/maths-reading";
import { MathsText } from "@/components/maths-text";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, Mark, Opening, Standfirst, useDismiss } from "@/components/ui";
import {
  useDeleteDocument,
  useDocuments,
  usePages,
  useReprocessDocument,
  useRequestSummary,
  useSummary,
  useUploadDocument,
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
  const upload = useUploadDocument(environmentId);
  const input = useRef<HTMLInputElement>(null);
  const [tooLarge, setTooLarge] = useState<string | null>(null);
  const [reading, setReading] = useState<string | null>(null);
  const working = useActiveJobs(environmentId);

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Clear the picker so choosing the same file again still triggers this.
    event.target.value = "";
    if (!file) return;
    upload.reset();
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setTooLarge(
        `"${file.name}" is larger than the ${MAX_UPLOAD_MB} MB limit.`,
      );
      return;
    }
    setTooLarge(null);
    upload.mutate(file);
  }

  const problem = tooLarge ?? upload.error?.message;

  return (
    <div className="flex flex-col gap-9">
      <Opening
        kicker={
          <>
            <span aria-hidden>02 / </span>Materials
          </>
        }
        headline={<MaterialsHeadline documents={documents.data} />}
        aside={
          <>
            <Standfirst>
              PDFs up to {MAX_UPLOAD_MB} MB. Each is read page by page as soon as it arrives.
            </Standfirst>
            <input
              ref={input}
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleFile}
              className="hidden"
              aria-label="Choose a PDF to upload"
            />
            <button
              type="button"
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
              className={`${button.primary} w-full tab:w-fit`}
            >
              {upload.isPending ? "Uploading…" : "Upload PDF"} <span aria-hidden>[+]</span>
            </button>
          </>
        }
      />

      {problem && (
        <p role="alert" className="label flex items-center gap-2">
          <Mark />
          {problem}
        </p>
      )}

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
      ) : documents.data.length === 0 ? (
        <Empty>
          No materials yet. Upload lecture notes or readings as PDFs to get started.
        </Empty>
      ) : (
        <div className="flex flex-col">
          <div aria-hidden className="label hidden gap-4 border-b border-ink pb-2 text-[10px] text-ink-3 tab:flex">
            <span className="flex-1">Document</span>
            <span className="w-44">Status</span>
            <span className="w-32" />
          </div>
          <ul aria-label="Documents">
            {documents.data.map((document) => (
              <li key={document.id} className="border-b border-rule">
                <DocumentRow
                  document={document}
                  environmentId={environmentId}
                  job={working.get(document.id)}
                  isReading={reading === document.id}
                  onToggleReading={() =>
                    setReading(reading === document.id ? null : document.id)
                  }
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// "Four documents. One is being read."
function MaterialsHeadline({ documents }: { documents: Document[] | undefined }) {
  if (!documents) return <span aria-hidden className="placeholder block h-[0.9em] w-2/3" />;
  if (documents.length === 0) return "No materials yet.";
  const n = documents.length;
  const busy = documents.filter((d) => d.status === "uploaded" || d.status === "processing").length;
  const first = `${InWords(n)} ${n === 1 ? "document" : "documents"}.`;
  if (busy === 0) return first;
  return (
    <>
      {first}
      <br />
      {busy === 1 ? "One is" : `${InWords(busy)} are`} being read.
    </>
  );
}

// Each document's queued or running job, if any. A job names the material
// update it carries out, and the update names its document. Both lists are
// already fetched and followed by the strip above the tabs.
function useActiveJobs(environmentId: string): Map<string, Job> {
  const jobs = useJobs(environmentId);
  const updates = useUpdates(environmentId);
  const documentOf = new Map(
    (updates.data ?? []).map((u) => [u.id, u.document_id] as const),
  );
  const found = new Map<string, Job>();
  for (const job of jobs.data ?? []) {
    if (job.status !== "queued" && job.status !== "running") continue;
    const documentId = job.update_id ? documentOf.get(job.update_id) : null;
    // The list puts the newest first: keep the first job found for each.
    if (documentId && !found.has(documentId)) found.set(documentId, job);
  }
  return found;
}

function DocumentRow({
  document,
  environmentId,
  job,
  isReading,
  onToggleReading,
}: {
  document: Document;
  environmentId: string;
  job: Job | undefined;
  isReading: boolean;
  onToggleReading: () => void;
}) {
  const reprocess = useReprocessDocument(environmentId);
  const newVersion = useNewVersion(environmentId);
  const versionInput = useRef<HTMLInputElement>(null);

  function handleVersion(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    newVersion.mutate({ documentId: document.id, file });
  }
  const remove = useDeleteDocument(environmentId);
  const summary = useSummary(environmentId, document);
  const askForSummary = useRequestSummary(environmentId, document.id);
  const [showingSummary, setShowingSummary] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [offeringMaths, setOfferingMaths] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  useDismiss(menu, menuOpen, closeMenu, menuButton);

  // A document read before summaries were automatic has none until asked.
  // The click asks, never the panel appearing, so one click is one request.
  function handleSummary() {
    setMenuOpen(false);
    if (showingSummary) {
      setShowingSummary(false);
      return;
    }
    setShowingSummary(true);
    if (summary.data === null && !askForSummary.isPending) askForSummary.mutate();
  }

  const canVersion = document.status !== "uploaded" && document.status !== "processing";
  const item = "label flex w-full items-center gap-2 border-b border-rule px-3.5 py-3 text-left last:border-b-0 hover:bg-ink hover:text-paper disabled:opacity-40";

  return (
    <article className={`flex flex-col gap-3 py-4 ${menuOpen ? "bg-paper-2 tab:-mx-3 tab:px-3" : ""}`}>
      <div className="flex flex-col gap-2 tab:flex-row tab:items-start tab:gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="display truncate text-2xl leading-none tracking-[-0.015em]">{document.filename}</h3>
          <p className="label text-[10px] text-ink-3">
            {formatBytes(document.size_bytes)} · added {formatDate(document.created_at)}
          </p>
        </div>
        <div className="tab:w-44 tab:pt-1.5">
          <StatusBadge document={document} />
        </div>
        <div ref={menu} className="relative flex items-center gap-4 tab:w-32 tab:justify-end tab:pt-1">
          {document.status === "ready" && (
            <button
              type="button"
              onClick={onToggleReading}
              aria-expanded={isReading}
              className={`${button.link} text-[10px]`}
            >
              {isReading ? "Hide text" : "Read text"}
            </button>
          )}
          <button
            ref={menuButton}
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-expanded={menuOpen}
            aria-label={`More for ${document.filename}`}
            className={`label flex size-10 items-center justify-center border border-rule tracking-normal tab:size-7 tab:border-0 ${
              menuOpen ? "bg-ink text-paper" : "hover:bg-ink hover:text-paper"
            }`}
          >
            •••
          </button>
          {menuOpen && (
            <div className="absolute top-full right-0 z-20 mt-1 flex w-64 flex-col border border-ink bg-paper">
              {document.status === "ready" && (
                <button type="button" onClick={handleSummary} aria-expanded={showingSummary} className={item}>
                  <span className="flex-1">{showingSummary ? "Hide summary" : summaryLabel(summary.data)}</span>
                  <span aria-hidden>→</span>
                </button>
              )}
              {document.status === "ready" && (
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setOfferingMaths(!offeringMaths);
                  }}
                  aria-expanded={offeringMaths}
                  className={item}
                >
                  <span className="flex-1">Read the maths</span>
                  <span aria-hidden>→</span>
                </button>
              )}
              {canVersion && (
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    versionInput.current?.click();
                  }}
                  disabled={newVersion.isPending}
                  className={item}
                >
                  <span className="flex-1">{newVersion.isPending ? "Uploading…" : "Upload a new version"}</span>
                  <span aria-hidden>→</span>
                </button>
              )}
              {document.status === "failed" && (
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    reprocess.mutate(document.id);
                  }}
                  disabled={reprocess.isPending}
                  className={item}
                >
                  <span className="flex-1">Try again</span>
                  <span aria-hidden>→</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setConfirming(true);
                }}
                disabled={remove.isPending}
                className={item}
              >
                <Mark />
                <span className="flex-1">{remove.isPending ? "Deleting…" : "Delete"}</span>
                  <span aria-hidden>→</span>
              </button>
            </div>
          )}
        </div>
      </div>
      {canVersion && (
        <input
          ref={versionInput}
          type="file"
          accept="application/pdf,.pdf"
          onChange={handleVersion}
          className="hidden"
          aria-label={`Choose a new version of ${document.filename}`}
        />
      )}

      <Notes document={document} />

      {job && <JobLine job={job} />}

      {!showingSummary &&
        summary.data?.status === "ready" &&
        summary.data.overview && (
          <p className="line-clamp-2 max-w-3xl text-sm text-ink-2">
            <MathsText text={summary.data.overview} />
          </p>
        )}

      {confirming && (
        <div role="alertdialog" aria-label={`Delete ${document.filename}`} className="flex flex-col gap-3 border border-ink p-4 tab:flex-row tab:items-center tab:gap-5">
          <p className="display flex-1 text-xl leading-tight">
            Delete “{document.filename}”? This cannot be undone.
          </p>
          <div className="flex items-center gap-5">
            <button
              type="button"
              onClick={() => {
                setConfirming(false);
                remove.mutate(document.id);
              }}
              className={button.danger}
            >
              Delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className={button.link}>
              Keep it
            </button>
          </div>
        </div>
      )}

      {offeringMaths && document.status === "ready" && (
        <MathsPanel
          document={document}
          environmentId={environmentId}
          onClose={() => setOfferingMaths(false)}
        />
      )}

      {(reprocess.error ?? remove.error ?? newVersion.error) && (
        <p role="alert" className="label flex items-center gap-2">
          <Mark />
          {(reprocess.error ?? remove.error ?? newVersion.error)?.message}
        </p>
      )}

      {showingSummary && (
        <DocumentSummaryPanel
          environmentId={environmentId}
          summary={summary.data}
          loadError={summary.error}
          onReload={() => void summary.refetch()}
          reloading={summary.isFetching}
          onTryAgain={() => askForSummary.mutate()}
          retrying={askForSummary.isPending}
          retryError={askForSummary.error}
        />
      )}

      {isReading && <PageReader documentId={document.id} />}
    </article>
  );
}

// The step a document's background work is at, while it runs.
function JobLine({ job }: { job: Job }) {
  const running = job.status === "running";
  return (
    <div className="flex flex-col gap-1.5">
      <p className="label text-[10px] text-ink-2">
        {job.title}:{" "}
        {job.cancel_requested
          ? "stopping after this step…"
          : running
            ? `${job.step ?? "starting"} · ${job.progress}%`
            : "queued"}
      </p>
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

// What the summary button says while the summary is closed.
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

const BADGE = {
  uploaded: { label: "Waiting", style: "text-ink-2" },
  processing: { label: "Reading…", style: "text-ink" },
  ready: { label: "Ready", style: "text-ink-2" },
  failed: { label: "Failed", style: "text-ink" },
};

export function StatusBadge({ document }: { document: Document }) {
  const { label, style } = BADGE[document.status];
  const pages =
    document.status === "ready" && document.page_count !== null
      ? ` · ${document.page_count} ${document.page_count === 1 ? "page" : "pages"}`
      : "";
  return (
    <span className={`label inline-flex shrink-0 items-center gap-1.5 text-[10px] ${style}`}>
      {document.status === "failed" && <Mark />}
      {label}
      {pages}
    </span>
  );
}

function Notes({ document }: { document: Document }) {
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
    <ul className="flex flex-col gap-1 text-sm text-ink-2">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}

function PageReader({ documentId }: { documentId: string }) {
  const pages = usePages(documentId);

  if (pages.isPending) return <Loading what="the text" lines={4} />;
  if (pages.isError) {
    return (
      <LoadError
        what="the text"
        error={pages.error}
        onRetry={() => void pages.refetch()}
        retrying={pages.isFetching}
      />
    );
  }
  return (
    <div className="flex max-h-[32rem] flex-col gap-5 overflow-y-auto bg-paper-2 px-5 py-4">
      {pages.data.map((page) => (
        <section key={page.page_number} aria-label={`Page ${page.page_number}`}>
          <h4 className="label mb-1.5 text-[10px] text-ink-3">
            Page {page.page_number}
          </h4>
          {page.content.trim() ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              <MathsText text={page.content} />
            </p>
          ) : (
            <p className="display text-base text-ink-3 italic">No text on this page.</p>
          )}
        </section>
      ))}
    </div>
  );
}

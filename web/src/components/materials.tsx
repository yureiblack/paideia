"use client";

// The Materials tab: upload PDFs into an environment, watch them being read,
// retry failures, delete them, read the extracted text page by page, and ask
// the local language model for a cited summary of any document.

import { useRef, useState, type ChangeEvent } from "react";

import { DocumentSummaryPanel } from "@/components/document-summary";
import {
  useDeleteDocument,
  useDocuments,
  usePages,
  useReprocessDocument,
  useSummarizeDocument,
  useUploadDocument,
} from "@/hooks/use-documents";
import { formatBytes, formatDate } from "@/lib/format";
import { MAX_UPLOAD_MB, type Document } from "@/lib/types";

export function Materials({ environmentId }: { environmentId: string }) {
  const documents = useDocuments(environmentId);
  const upload = useUploadDocument(environmentId);
  const input = useRef<HTMLInputElement>(null);
  const [tooLarge, setTooLarge] = useState<string | null>(null);
  const [reading, setReading] = useState<string | null>(null);

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
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          PDFs up to {MAX_UPLOAD_MB} MB. Each is read page by page as soon as
          it arrives.
        </p>
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
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {upload.isPending ? "Uploading…" : "Upload PDF"}
        </button>
      </div>

      {problem && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {problem}
        </p>
      )}

      {documents.isPending ? (
        <p className="text-zinc-500">Loading materials…</p>
      ) : documents.isError ? (
        <p role="alert" className="text-red-600 dark:text-red-400">
          Could not load materials: {documents.error.message}
        </p>
      ) : documents.data.length === 0 ? (
        <p className="text-zinc-500">
          No materials yet. Upload a PDF to get started.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {documents.data.map((document) => (
            <li key={document.id}>
              <DocumentRow
                document={document}
                environmentId={environmentId}
                isReading={reading === document.id}
                onToggleReading={() =>
                  setReading(reading === document.id ? null : document.id)
                }
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DocumentRow({
  document,
  environmentId,
  isReading,
  onToggleReading,
}: {
  document: Document;
  environmentId: string;
  isReading: boolean;
  onToggleReading: () => void;
}) {
  const reprocess = useReprocessDocument(environmentId);
  const remove = useDeleteDocument(environmentId);
  const summarize = useSummarizeDocument();
  const [showingSummary, setShowingSummary] = useState(false);

  // Started by the click itself, never by the panel appearing, so one click
  // is always one request to the model.
  function handleSummarize() {
    if (showingSummary && !summarize.isPending) {
      setShowingSummary(false);
      return;
    }
    setShowingSummary(true);
    if (!summarize.data && !summarize.isPending) summarize.mutate(document.id);
  }

  function handleDelete() {
    if (window.confirm(`Delete "${document.filename}"? This cannot be undone.`)) {
      remove.mutate(document.id);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="truncate font-medium">{document.filename}</h3>
          <p className="text-xs text-zinc-500">
            {formatBytes(document.size_bytes)} · added{" "}
            {formatDate(document.created_at)}
          </p>
        </div>
        <StatusBadge document={document} />
      </div>

      <Notes document={document} />

      <div className="flex flex-wrap gap-2">
        {document.status === "ready" && (
          <button
            type="button"
            onClick={onToggleReading}
            aria-expanded={isReading}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium dark:border-zinc-700"
          >
            {isReading ? "Hide text" : "Read text"}
          </button>
        )}
        {document.status === "ready" && (
          <button
            type="button"
            onClick={handleSummarize}
            aria-expanded={showingSummary}
            disabled={summarize.isPending}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
          >
            {summarize.isPending
              ? "Summarizing…"
              : showingSummary
                ? "Hide summary"
                : "Summarize"}
          </button>
        )}
        {showingSummary && summarize.data && (
          <button
            type="button"
            onClick={() => summarize.mutate(document.id)}
            disabled={summarize.isPending}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
          >
            Summarize again
          </button>
        )}
        {document.status === "failed" && (
          <button
            type="button"
            onClick={() => reprocess.mutate(document.id)}
            disabled={reprocess.isPending}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
          >
            Try again
          </button>
        )}
        <button
          type="button"
          onClick={handleDelete}
          disabled={remove.isPending}
          className="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 disabled:opacity-50 dark:border-red-900 dark:text-red-400"
        >
          {remove.isPending ? "Deleting…" : "Delete"}
        </button>
      </div>

      {(reprocess.error ?? remove.error) && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {(reprocess.error ?? remove.error)?.message}
        </p>
      )}

      {showingSummary && (
        <DocumentSummaryPanel
          environmentId={environmentId}
          isPending={summarize.isPending}
          error={summarize.error}
          summary={summarize.data}
        />
      )}

      {isReading && <PageReader documentId={document.id} />}
    </article>
  );
}

const BADGE = {
  uploaded: { label: "Waiting", style: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" },
  processing: { label: "Reading…", style: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  ready: { label: "Ready", style: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" },
  failed: { label: "Failed", style: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
};

function StatusBadge({ document }: { document: Document }) {
  const { label, style } = BADGE[document.status];
  const pages =
    document.status === "ready" && document.page_count !== null
      ? ` · ${document.page_count} ${document.page_count === 1 ? "page" : "pages"}`
      : "";
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${style}`}
    >
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
    <ul className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-400">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );
}

function PageReader({ documentId }: { documentId: string }) {
  const pages = usePages(documentId);

  if (pages.isPending) {
    return <p className="text-sm text-zinc-500">Loading text…</p>;
  }
  if (pages.isError) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        Could not load the text: {pages.error.message}
      </p>
    );
  }
  return (
    <div className="flex max-h-[32rem] flex-col gap-4 overflow-y-auto rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900">
      {pages.data.map((page) => (
        <section key={page.page_number} aria-label={`Page ${page.page_number}`}>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Page {page.page_number}
          </h4>
          {page.content.trim() ? (
            <p className="whitespace-pre-wrap text-sm">{page.content}</p>
          ) : (
            <p className="text-sm text-zinc-500">No text on this page.</p>
          )}
        </section>
      ))}
    </div>
  );
}

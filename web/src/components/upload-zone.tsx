"use client";

// Adding PDFs to an environment: the Upload PDF button, and the band that
// also takes files dropped on it (decision record 28). Several files can be
// chosen or dropped at once; each is checked here (a PDF, within the size
// limit) only to spare a pointless upload, then sent one after another. The
// backend enforces its own limits either way, and says why it refused one.
//
// One page has one of these, so "Choose a PDF to upload" names exactly one
// file input.

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { button, Mark } from "@/components/ui";
import { useUploadDocument } from "@/hooks/use-documents";
import { MAX_UPLOAD_MB } from "@/lib/types";

const isPdf = (file: File) =>
  file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");

export function UploadZone({
  environmentId,
  variant,
}: {
  environmentId: string;
  variant: "button" | "band";
}) {
  const upload = useUploadDocument(environmentId);
  const input = useRef<HTMLInputElement>(null);
  // How many of the files sent are still on their way.
  const [sending, setSending] = useState(0);
  const [problems, setProblems] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);

  async function send(files: File[]) {
    if (files.length === 0) return;
    // A message names its file only when several were sent together.
    const named = (file: File, message: string) =>
      files.length > 1 ? `${file.name}: ${message}` : message;
    const found: string[] = [];
    const fit: File[] = [];
    for (const file of files) {
      if (!isPdf(file)) found.push(`“${file.name}” is not a PDF.`);
      else if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        found.push(`“${file.name}” is larger than the ${MAX_UPLOAD_MB} MB limit.`);
      } else fit.push(file);
    }
    setProblems(found);
    setSending(fit.length);
    for (const file of fit) {
      try {
        await upload.mutateAsync(file);
      } catch (error) {
        found.push(named(file, error instanceof Error ? error.message : String(error)));
        setProblems([...found]);
      }
      setSending((left) => left - 1);
    }
  }

  function handleChosen(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    // Clear the picker so choosing the same file again still triggers this.
    event.target.value = "";
    void send(files);
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragging(false);
    void send(Array.from(event.dataTransfer.files));
  }

  const busy = sending > 0;
  const chooser = (
    <>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        onChange={handleChosen}
        className="hidden"
        aria-label="Choose a PDF to upload"
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className={`${button.primary} w-full shrink-0 tab:w-fit`}
      >
        {busy ? "Uploading…" : "Upload PDF"} <span aria-hidden>[+]</span>
      </button>
    </>
  );
  const problemList = problems.length > 0 && (
    <div role="alert">
      <ul className="flex flex-col gap-1">
        {problems.map((problem) => (
          <li key={problem} className="flex items-start gap-2 text-[15px] leading-[1.45]">
            <span className="pt-[7px]">
              <Mark />
            </span>
            {problem}
          </li>
        ))}
      </ul>
    </div>
  );

  if (variant === "button") {
    return (
      <div className="flex flex-col gap-3">
        {chooser}
        {problemList}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(event) => {
          // Only when leaving the band itself, not one of its children.
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={handleDrop}
        className={`flex flex-col gap-5 bg-paper-2 px-5 py-6 outline-offset-[-2px] tab:flex-row tab:items-center tab:gap-8 tab:px-8 tab:py-8 ${
          dragging ? "outline-2 outline-ink outline-dashed" : ""
        }`}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="display text-[30px] leading-[1.05] tracking-[-0.02em] tab:text-[36px]">
            {dragging ? "Drop to upload" : "Drop PDFs here"}
          </p>
          <p className="max-w-[460px] text-[15px] leading-[1.55] text-ink-2">
            or choose them from this computer. Up to {MAX_UPLOAD_MB} MB each; several at once is
            fine.
          </p>
        </div>
        {chooser}
      </div>
      {problemList}
    </div>
  );
}

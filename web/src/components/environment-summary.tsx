"use client";

// The Summary tab, set as an article (decision record 28): the
// environment's master summary, written from its documents' summaries and
// kept up to date by itself as material is added or removed. The headline
// and what it is based on; the overview as the lead and the key points as
// reading text, each point with the numbers of the notes it cites; in the
// margin, the notes, each opening its passage in its page, and folded away,
// how it was written and the versions of its sources. Before there is a
// summary, the page says what comes and when.

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { NotedPoints, NoteList, numberNotes, type OpenNote } from "@/components/cited-points";
import { sectionNumber } from "@/components/environment-tabs";
import { MathsText } from "@/components/maths-text";
import { Note } from "@/components/note";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign, Opening } from "@/components/ui";
import { useDocuments } from "@/hooks/use-documents";
import {
  useEnvironmentSummary,
  useRequestEnvironmentSummary,
} from "@/hooks/use-environment-summary";
import { formatDateTime } from "@/lib/format";
import type { EnvironmentSummaryState, NotIncluded } from "@/lib/types";

// How each state of something derived, the summary or the knowledge graph,
// is shown.
export const STATE_BADGE: Record<
  EnvironmentSummaryState["state"],
  { label: string; style: string }
> = {
  up_to_date: { label: "Up to date", style: "text-ink-2" },
  updating: { label: "Updating…", style: "text-ink" },
  waiting: { label: "Waiting for documents", style: "text-ink" },
  stale: { label: "Out of date", style: "text-ink" },
  failed: { label: "Update failed", style: "text-ink" },
  none: { label: "Nothing yet", style: "text-ink-3" },
};

export function EnvironmentSummary({ environmentId }: { environmentId: string }) {
  const query = useEnvironmentSummary(environmentId);
  const documents = useDocuments(environmentId);
  const update = useRequestEnvironmentSummary(environmentId);
  const [open, setOpen] = useState<OpenNote>(null);
  const kicker = (
    <>
      <span aria-hidden>{sectionNumber("Summary")} / </span>Summary
    </>
  );

  if (query.isPending || query.isError) {
    return (
      <div className="flex flex-col gap-4">
        <p className="label max-tab:sr-only">{kicker}</p>
        {query.isPending ? (
          <Loading what="the summary" lines={4} />
        ) : (
          <LoadError
            what="the summary"
            error={query.error}
            onRetry={() => void query.refetch()}
            retrying={query.isFetching}
          />
        )}
      </div>
    );
  }
  const { state, waiting_for, error, summary, not_included, earlier_versions } =
    query.data;
  const badge = STATE_BADGE[state];
  const updateAction = (state === "stale" || state === "failed") && (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={() => update.mutate()}
        disabled={update.isPending}
        className={button.primary}
      >
        {state === "failed" ? "Try again" : "Update now"}
      </button>
      {update.error && (
        <p role="alert" className="flex items-center gap-2.5 text-[13px] leading-[1.4]">
          <Mark />
          {update.error.message}
        </p>
      )}
    </div>
  );

  if (!summary) {
    return (
      <div className="flex flex-col gap-6">
        <p className="label max-tab:sr-only">{kicker}</p>
        <NoSummary
          environmentId={environmentId}
          state={state}
          waitingFor={waiting_for}
          documents={documents.data?.length ?? null}
          error={error}
          action={updateAction}
        />
        {not_included.length > 0 && (
          <div className="max-w-[640px]">
            <LeftOut items={not_included} />
          </div>
        )}
      </div>
    );
  }

  const notes = numberNotes(summary.key_points);
  const documentCount = summary.based_on.length;
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        <Opening kicker={kicker} headline="What the material covers." />
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] leading-[1.4] text-ink-2">
          {state !== "up_to_date" && <span className={`label ${badge.style}`}>{badge.label}</span>}
          <span>
            Based on {documentCount} {documentCount === 1 ? "document" : "documents"} · updated{" "}
            {formatDateTime(summary.updated_at)}
          </span>
        </p>
      </div>

      <Note id="summary" title="The summary — where it comes from" guideStep={4}>
        Written by the local model from the summaries of your documents. Every point
        cites its page: open a note to read that page in its document.
      </Note>

      {state !== "up_to_date" && (
        <div className="flex flex-col items-start gap-3">
          <StateNote state={state} waitingFor={waiting_for} error={error} />
          {updateAction}
        </div>
      )}

      <section
        aria-label="Environment summary"
        className="grid gap-10 border-t border-ink pt-7 desk:grid-cols-[minmax(0,1fr)_220px] desk:gap-12"
      >
        <div className="flex min-w-0 flex-col gap-6">
          {summary.overview && (
            <p className="max-w-[640px] text-[20px] leading-[1.5] tab:text-[22px]">
              <MathsText text={summary.overview} />
            </p>
          )}
          <NotedPoints
            environmentId={environmentId}
            points={summary.key_points}
            notes={notes}
            open={open}
            onOpen={setOpen}
          />
        </div>
        <aside aria-label="Notes and sources" className="flex flex-col gap-5">
          {notes.length > 0 && <NoteList notes={notes} open={open} onOpen={setOpen} />}
          <Fold title="How this was written">
            <p className="text-[13px] leading-[1.5] text-ink-2">
              Written by {summary.model} from the documents&apos; summaries
              {summary.seconds !== null && `, in ${summary.seconds.toFixed(1)} s`}, with
              prompt {summary.prompt_versions.join(" and ")}.
              {earlier_versions > 0 &&
                ` ${earlier_versions} earlier ${
                  earlier_versions === 1 ? "summary is" : "summaries are"
                } kept.`}
            </p>
          </Fold>
          <Fold title="Sources and versions">
            <ul className="flex flex-col gap-1">
              {summary.based_on.map((source) => (
                <li key={source.document_id} className="flex items-baseline gap-2">
                  <span className="min-w-0 flex-1 truncate text-[13px] leading-[1.4]">
                    {source.filename}
                  </span>
                  <span className="label text-ink-3" title={`File version ${source.document_version}`}>
                    {source.document_version.slice(0, 8)}
                  </span>
                </li>
              ))}
            </ul>
          </Fold>
          {not_included.length > 0 && <LeftOut items={not_included} />}
        </aside>
      </section>
    </div>
  );
}

// A margin section folded away until asked for.
function Fold({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2.5 border-t border-rule pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="label w-fit text-left text-ink-2 hover:text-ink"
      >
        {title} <OpenSign open={open} />
      </button>
      {open && children}
    </div>
  );
}

// The documents the summary leaves out, and why.
function LeftOut({ items }: { items: NotIncluded[] }) {
  return (
    <section aria-labelledby="left-out-heading" className="flex flex-col gap-2 border-t border-rule pt-3">
      <h3 id="left-out-heading" className="label flex items-center gap-2">
        <Mark />
        Not included
      </h3>
      <ul className="flex flex-col gap-1.5">
        {items.map((item) => (
          <li key={item.document_id} className="text-[13px] leading-[1.4]">
            {item.filename}
            <span className="text-ink-2"> · {item.reason}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Before there is a summary: what comes, and when.
function NoSummary({
  environmentId,
  state,
  waitingFor,
  documents,
  error,
  action,
}: {
  environmentId: string;
  state: EnvironmentSummaryState["state"];
  waitingFor: number;
  documents: number | null;
  error: string | null;
  action: ReactNode;
}) {
  if (state === "failed") {
    return (
      <Empty title="The summary could not be written." action={action}>
        <span role="alert">
          {error ? `The local model stopped: ${error}` : "The local model stopped before it was done."}
        </span>
      </Empty>
    );
  }
  if (state === "updating") {
    return (
      <Empty title="The summary is being written.">
        <span role="status">
          The local model is writing it from the summaries of your documents. It appears
          here when it is done.
        </span>
      </Empty>
    );
  }
  // "1 of 3 documents is still being read."
  const of = documents !== null && documents > waitingFor ? documents : null;
  const still =
    waitingFor > 0
      ? ` ${of ? `${waitingFor} of ${of}` : waitingFor} ${
          (of ?? waitingFor) === 1 ? "document" : "documents"
        } ${waitingFor === 1 ? "is" : "are"} still being read.`
      : "";
  return (
    <Empty
      title="The summary comes after the reading."
      action={
        action || (
          <Link
            href={`/environments/${encodeURIComponent(environmentId)}/materials`}
            className={button.link}
          >
            See the materials <span aria-hidden>→</span>
          </Link>
        )
      }
    >
      <span role="status">
        It is written once a document has been read, and rewritten when one is added or
        changed.{still}
      </span>
    </Empty>
  );
}

// Where the summary stands, while the one shown is not up to date.
function StateNote({
  state,
  waitingFor,
  error,
}: {
  state: EnvironmentSummaryState["state"];
  waitingFor: number;
  error: string | null;
}) {
  const shown = " The summary below is from earlier material.";
  const note = {
    up_to_date: null,
    updating: `Writing a summary of the current material with the local model.${shown}`,
    waiting: `${waitingFor} ${
      waitingFor === 1 ? "document is" : "documents are"
    } still being read or summarized; the summary is updated once they are done.${shown}`,
    stale: `The material has changed since the last summary.${shown}`,
    failed: `The summary could not be updated: ${error}${shown}`,
    none: null,
  }[state];
  if (!note) return null;
  return (
    <p
      role={state === "failed" ? "alert" : "status"}
      className={`flex max-w-[640px] gap-2.5 text-[15px] leading-[1.55] ${state === "failed" ? "text-ink" : "text-ink-2"}`}
    >
      {state === "failed" && (
        <span className="pt-[7px]">
          <Mark />
        </span>
      )}
      <span>{note}</span>
    </p>
  );
}

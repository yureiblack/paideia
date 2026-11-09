"use client";

// The Summary tab: the environment's master summary, written from its
// documents' summaries and kept up to date by itself as material is added or
// removed. Shows where it stands, when it was last updated and what it is
// based on; then the overview and key points, each with chips that open the
// cited passage in its page; then its sources and any documents left out.

import { CitedPoints } from "@/components/cited-points";
import {
  useEnvironmentSummary,
  useRequestEnvironmentSummary,
} from "@/hooks/use-environment-summary";
import { formatDateTime } from "@/lib/format";
import type { EnvironmentSummaryState } from "@/lib/types";

const BADGE: Record<
  EnvironmentSummaryState["state"],
  { label: string; style: string }
> = {
  up_to_date: { label: "Up to date", style: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" },
  updating: { label: "Updating…", style: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  waiting: { label: "Waiting for documents", style: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  stale: { label: "Out of date", style: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" },
  failed: { label: "Update failed", style: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
  none: { label: "Nothing yet", style: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" },
};

export function EnvironmentSummary({ environmentId }: { environmentId: string }) {
  const query = useEnvironmentSummary(environmentId);
  const update = useRequestEnvironmentSummary(environmentId);

  if (query.isPending) {
    return <p className="text-zinc-500">Loading the summary…</p>;
  }
  if (query.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not load the summary: {query.error.message}
      </p>
    );
  }
  const { state, waiting_for, error, summary, not_included, earlier_versions } =
    query.data;
  const badge = BADGE[state];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.style}`}>
          {badge.label}
        </span>
        {summary && (
          <span className="text-zinc-600 dark:text-zinc-400">
            Last updated {formatDateTime(summary.updated_at)} · Based on{" "}
            {summary.based_on.length}{" "}
            {summary.based_on.length === 1 ? "document" : "documents"}
          </span>
        )}
      </div>

      <StateNote
        state={state}
        waitingFor={waiting_for}
        error={error}
        hasSummary={summary !== null}
      />
      {(state === "stale" || state === "failed") && (
        <div className="flex flex-col items-start gap-2">
          <button
            type="button"
            onClick={() => update.mutate()}
            disabled={update.isPending}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {state === "failed" ? "Try again" : "Update now"}
          </button>
          {update.error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {update.error.message}
            </p>
          )}
        </div>
      )}

      {summary && (
        <section aria-label="Environment summary" className="flex flex-col gap-4">
          <p>{summary.overview}</p>
          <CitedPoints
            environmentId={environmentId}
            points={summary.key_points}
            showFilename
          />
          <p className="text-xs text-zinc-500">
            Written by {summary.model} from the documents&apos; summaries
            {summary.seconds !== null && `, in ${summary.seconds.toFixed(1)} s`},
            with prompt {summary.prompt_versions.join(" and ")}.
            {earlier_versions > 0 &&
              ` ${earlier_versions} earlier ${
                earlier_versions === 1 ? "summary is" : "summaries are"
              } kept.`}
          </p>
        </section>
      )}

      {summary && (
        <section aria-labelledby="sources-heading" className="flex flex-col gap-2">
          <h3 id="sources-heading" className="font-medium">
            Sources
          </h3>
          <ul className="flex flex-col gap-1 text-sm">
            {summary.based_on.map((source) => (
              <li key={source.document_id} className="flex flex-wrap gap-x-2">
                <span>{source.filename}</span>
                <span
                  className="font-mono text-xs text-zinc-500"
                  title={`File version ${source.document_version}`}
                >
                  version {source.document_version.slice(0, 8)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {not_included.length > 0 && (
        <section aria-labelledby="left-out-heading" className="flex flex-col gap-2">
          <h3 id="left-out-heading" className="font-medium">
            Not included
          </h3>
          <ul className="flex flex-col gap-1 text-sm">
            {not_included.map((item) => (
              <li key={item.document_id}>
                <span>{item.filename}</span>
                <span className="text-zinc-500"> · {item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function StateNote({
  state,
  waitingFor,
  error,
  hasSummary,
}: {
  state: EnvironmentSummaryState["state"];
  waitingFor: number;
  error: string | null;
  hasSummary: boolean;
}) {
  const shown = hasSummary ? " The summary below is from earlier material." : "";
  const note = {
    up_to_date: null,
    updating: `Writing a summary of the current material with the local model.${shown}`,
    waiting: `${waitingFor} ${
      waitingFor === 1 ? "document is" : "documents are"
    } still being read or summarized; the summary is updated once they are done.${shown}`,
    stale: `The material has changed since the last summary.${shown}`,
    failed: `The summary could not be updated: ${error}${shown}`,
    none: "Nothing to summarize yet. Once materials have been read and summarized, a summary of all of them appears here and keeps itself up to date.",
  }[state];
  if (!note) return null;
  return (
    <p
      role={state === "failed" ? "alert" : "status"}
      className={`text-sm ${state === "failed" ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400"}`}
    >
      {note}
    </p>
  );
}

"use client";

// The Summary tab, set as an article (decision record 25): the
// environment's master summary, written from its documents' summaries and
// kept up to date by itself as material is added or removed. Where it
// stands, when it was last updated and what it is based on; the overview as
// the lede, then the key points, each with references that open the cited
// passage in its page; beside them its sources, any documents left out, and
// how it was written.

import { CitedPoints } from "@/components/cited-points";
import { MathsText } from "@/components/maths-text";
import { Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import {
  useEnvironmentSummary,
  useRequestEnvironmentSummary,
} from "@/hooks/use-environment-summary";
import { useState } from "react";

import { formatDateTime } from "@/lib/format";
import type { EnvironmentSummaryState } from "@/lib/types";

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
  const update = useRequestEnvironmentSummary(environmentId);
  const [showHow, setShowHow] = useState(false);
  const kicker = (
    <span aria-hidden>06 / </span>
  );

  if (query.isPending) return <Loading what="the summary" lines={4} />;
  if (query.isError) {
    return (
      <LoadError
        what="the summary"
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  const { state, waiting_for, error, summary, not_included, earlier_versions } =
    query.data;
  const badge = STATE_BADGE[state];

  return (
    <div className="flex flex-col gap-7">
      <p className="label flex flex-wrap items-center gap-x-2 gap-y-1">
        {kicker}Summary
        <span aria-hidden className="text-ink-3">—</span>
        <span className={badge.style}>{badge.label}</span>
        {summary && (
          <span className="text-ink-2">
            · Based on {summary.based_on.length}{" "}
            {summary.based_on.length === 1 ? "document" : "documents"} · updated{" "}
            {formatDateTime(summary.updated_at)}
          </span>
        )}
      </p>

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
            className={button.primary}
          >
            {state === "failed" ? "Try again" : "Update now"}
          </button>
          {update.error && (
            <p role="alert" className="label flex items-center gap-2">
              <Mark />
              {update.error.message}
            </p>
          )}
        </div>
      )}

      {summary && (
        <div className="flex flex-col gap-8">
          <section aria-label="Environment summary" className="flex flex-col gap-7">
            <p className="display max-w-4xl text-[28px] leading-[1.08] tracking-[-0.02em] tab:text-[36px] desk:text-[44px] desk:leading-[1.04]">
              <MathsText text={summary.overview} />
            </p>
            <div className="grid gap-8 desk:grid-cols-[minmax(0,1fr)_260px] desk:gap-10">
              <CitedPoints environmentId={environmentId} points={summary.key_points} showFilename />
              <aside className="flex flex-col gap-6">
                <section aria-labelledby="sources-heading" className="flex flex-col gap-2 border-t border-rule pt-3 desk:border-ink">
                  <h3 id="sources-heading" className="label text-[10px] text-ink-3">
                    Sources · version
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {summary.based_on.map((source) => (
                      <li key={source.document_id} className="flex items-baseline gap-2">
                        <span className="min-w-0 flex-1 truncate text-sm">{source.filename}</span>
                        <span className="label text-[9px] tracking-[0.04em] text-ink-3" title={`File version ${source.document_version}`}>
                          {source.document_version.slice(0, 8)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
                {not_included.length > 0 && (
                  <section aria-labelledby="left-out-heading" className="flex flex-col gap-2 border-t border-rule pt-3">
                    <h3 id="left-out-heading" className="label text-[10px] text-ink-3">
                      Not included
                    </h3>
                    <ul className="flex flex-col gap-1.5">
                      {not_included.map((item) => (
                        <li key={item.document_id} className="text-sm">
                          {item.filename}
                          <span className="text-ink-3"> · {item.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                <div className="flex flex-col gap-2 border-t border-rule pt-3">
                  <button
                    type="button"
                    onClick={() => setShowHow(!showHow)}
                    aria-expanded={showHow}
                    className="label w-fit text-[10px] text-ink-3 hover:text-ink"
                  >
                    How this was written <OpenSign open={showHow} />
                  </button>
                  {showHow && (
                    <p className="text-xs leading-normal text-ink-2">
                      Written by {summary.model} from the documents&apos; summaries
                      {summary.seconds !== null && `, in ${summary.seconds.toFixed(1)} s`},
                      with prompt {summary.prompt_versions.join(" and ")}.
                      {earlier_versions > 0 &&
                        ` ${earlier_versions} earlier ${
                          earlier_versions === 1 ? "summary is" : "summaries are"
                        } kept.`}
                    </p>
                  )}
                </div>
              </aside>
            </div>
          </section>
        </div>
      )}

      {!summary && not_included.length > 0 && (
        <section aria-labelledby="left-out-heading" className="flex flex-col gap-2 border-t border-ink pt-3">
          <h3 id="left-out-heading" className="label text-[10px] text-ink-3">
            Not included
          </h3>
          <ul className="flex flex-col gap-1.5">
            {not_included.map((item) => (
              <li key={item.document_id} className="text-sm">
                {item.filename}
                <span className="text-ink-3"> · {item.reason}</span>
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
      className={`display flex max-w-2xl gap-2.5 text-[19px] leading-[1.25] italic ${state === "failed" ? "text-ink" : "text-ink-2"}`}
    >
      {state === "failed" && (
        <span className="pt-2.5 not-italic">
          <Mark />
        </span>
      )}
      {note}
    </p>
  );
}

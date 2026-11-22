"use client";

// A document's summary, written by the local language model in the
// background once the document is read, and kept. Shows where it stands
// (waiting, being written, failed with the reason and Try again) and, once
// ready, the overview and key points, each with chips for the passages it
// cites. A chip opens that passage in its page, so every claim can be
// checked against the material itself. How it was written stays folded
// until asked for (decision record 28).

import { useState } from "react";

import { CitedPoints } from "@/components/cited-points";
import { MathsText } from "@/components/maths-text";
import { button, Mark, OpenSign } from "@/components/ui";
import { Loading, LoadError } from "@/components/query-states";
import { formatDateTime } from "@/lib/format";
import type { CurrentSummary } from "@/lib/types";

export function DocumentSummaryPanel({
  environmentId,
  summary,
  loadError,
  onReload,
  reloading,
  onTryAgain,
  retrying,
  retryError,
}: {
  environmentId: string;
  summary: CurrentSummary | null | undefined;
  loadError: Error | null;
  onReload: () => void;
  reloading: boolean;
  onTryAgain: () => void;
  retrying: boolean;
  retryError: Error | null;
}) {
  const [showingHow, setShowingHow] = useState(false);

  if (loadError) {
    return (
      <LoadError
        what="the summary"
        error={loadError}
        onRetry={onReload}
        retrying={reloading}
      />
    );
  }
  if (summary === undefined) return <Loading what="the summary" lines={3} />;
  if (summary === null || summary.status === "pending") {
    return (
      <p className="max-w-[640px] text-base leading-[1.55] text-ink-2" role="status">
        Waiting to be summarized. Summaries are written one at a time, as soon
        as the model is free.
      </p>
    );
  }
  if (summary.status === "generating") {
    return (
      <p className="max-w-[640px] text-base leading-[1.55] text-ink-2" role="status">
        Writing the summary with the local model… usually under a minute; a
        long document can take several.
      </p>
    );
  }
  if (summary.status === "failed") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="flex max-w-[640px] items-start gap-2 text-base leading-[1.55]">
          <span className="pt-2">
            <Mark />
          </span>
          The summary could not be written: {summary.error}
        </p>
        <button
          type="button"
          onClick={onTryAgain}
          disabled={retrying}
          className={button.outline}
        >
          {retrying ? "Asking…" : "Try again"}
        </button>
        {retryError && (
          <p role="alert" className="flex items-start gap-2 text-[15px] leading-[1.45]">
            <span className="pt-[7px]">
              <Mark />
            </span>
            {retryError.message}
          </p>
        )}
      </div>
    );
  }
  return (
    <section aria-label="Summary" className="flex max-w-[640px] flex-col gap-5">
      <p className="text-xl leading-[1.5] text-ink-2">
        <MathsText text={summary.overview} />
      </p>
      <CitedPoints environmentId={environmentId} points={summary.key_points} />
      <div className="flex flex-col items-start gap-2">
        <button
          type="button"
          onClick={() => setShowingHow(!showingHow)}
          aria-expanded={showingHow}
          className="label text-ink-2 hover:text-ink"
        >
          How this was written <OpenSign open={showingHow} />
        </button>
        {showingHow && (
          <p className="text-[13px] leading-[1.4] text-ink-2">
            Written by {summary.model} from this document&apos;s passages
            {summary.sections !== null &&
              summary.sections > 1 &&
              `, read in ${summary.sections} sections`}
            , {formatDateTime(summary.updated_at)}
            {summary.seconds !== null && `, in ${summary.seconds.toFixed(1)} s`}, with
            prompt {summary.prompt_versions.join(" and ")}.
            {summary.earlier_versions > 0 &&
              ` ${summary.earlier_versions} earlier ${
                summary.earlier_versions === 1 ? "summary is" : "summaries are"
              } kept.`}
          </p>
        )}
      </div>
    </section>
  );
}

"use client";

// Background work for an environment, on every one of its tabs: documents
// being read and the language model's work, run by the worker process
// (decision record 18). Each queued or running job shows its progress, the
// step it is at, and Cancel; a job being tried again says so, and jobs that
// failed in the hour before the list was fetched say why. Nothing shows
// when nothing is happening. If jobs wait and no worker is running, it says
// how to start one.

import { useCancelJob, useJobs, useWorker } from "@/hooks/use-jobs";
import { Mark } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { Job } from "@/lib/types";

const HOUR = 60 * 60 * 1000;

export function BackgroundWork({ environmentId }: { environmentId: string }) {
  const query = useJobs(environmentId);
  const cancel = useCancelJob(environmentId);
  const jobs = query.data ?? [];
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const failed = jobs.filter(
    (j) =>
      j.status === "failed" &&
      j.finished_at &&
      query.dataUpdatedAt - new Date(j.finished_at).getTime() < HOUR,
  );
  const waiting = active.length > 0 && active.every((j) => j.status === "queued");
  const worker = useWorker(waiting);
  if (active.length === 0 && failed.length === 0) return null;

  return (
    <section
      aria-labelledby="work-heading"
      className="my-3 flex flex-col gap-2.5 border-t border-rule pt-3 desk:my-0"
    >
      <h2 id="work-heading" className="label text-ink-3">
        Background work
      </h2>
      {waiting && worker.isError && (
        <p role="alert" className="flex gap-2 text-[13px] leading-snug">
          <span className="pt-1.5">
            <Mark />
          </span>
          <span>Waiting for the worker. {worker.error.message}</span>
        </p>
      )}
      <ul className="flex flex-col gap-3" aria-label="Jobs">
        {active.map((job) => (
          <li key={job.id}>
            <ActiveJob
              job={job}
              onCancel={() => cancel.mutate(job.id)}
              cancelling={cancel.isPending && cancel.variables === job.id}
            />
          </li>
        ))}
        {failed.map((job) => (
          <li key={job.id} className="flex gap-2 text-[13px] leading-snug">
            <span className="pt-1.5">
              <Mark />
            </span>
            <span>
              <span className="label">{job.title} failed:</span> {job.error}
            </span>
          </li>
        ))}
      </ul>
      {cancel.error && (
        <p role="alert" className="label flex items-center gap-2">
          <Mark />
          {cancel.error.message}
        </p>
      )}
    </section>
  );
}

function ActiveJob({
  job,
  onCancel,
  cancelling,
}: {
  job: Job;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const retrying = job.status === "queued" && job.attempts > 0;
  const status = job.cancel_requested
    ? "Stopping after this step…"
    : job.status === "running"
      ? (job.step ?? "Starting…")
      : retrying
        ? `${job.error} Next try ${job.not_before ? formatDateTime(job.not_before) : "soon"} (attempt ${job.attempts + 1} of ${job.max_attempts}).`
        : "Queued";
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="label">{job.title}</span>
        <span className="label flex items-center gap-3 text-ink-3">
          {job.status === "running" && <span className="tabular-nums">{job.progress}%</span>}
          {!job.cancel_requested && (
            <button
              type="button"
              onClick={onCancel}
              disabled={cancelling}
              className="border-b border-ink text-ink hover:border-accent disabled:opacity-40"
            >
              Cancel
            </button>
          )}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={job.title}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={job.progress}
        className="h-1 overflow-hidden bg-paper-2"
      >
        <div
          className="h-full bg-ink"
          style={{ width: `${job.status === "running" ? Math.max(job.progress, 3) : 0}%` }}
        />
      </div>
      <p className="text-[13px] leading-[1.4] text-ink-2">{status}</p>
    </div>
  );
}

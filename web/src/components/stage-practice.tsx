"use client";

// Where one roadmap stage's practice stands, with Prepare practice: shared by
// the Practice tab and the Roadmap tab's stage cards. Preparing asks the
// local model for four items per concept, written in the background one
// concept at a time; this follows along, and names any concept whose items
// could not be written, or whose material changed since.

import Link from "next/link";

import { usePractice, usePreparePractice } from "@/hooks/use-practice";
import type { PracticeConcept } from "@/lib/types";

export function StagePractice({
  environmentId,
  conceptIds,
  onPractise,
  stageNumber,
}: {
  environmentId: string;
  conceptIds: string[];
  // On the Practice tab, start a session here; elsewhere, link to it.
  onPractise?: () => void;
  stageNumber: number;
}) {
  const query = usePractice(environmentId);
  const prepare = usePreparePractice(environmentId);
  if (!query.data) return null;

  const wanted = new Set(conceptIds);
  const concepts = query.data.concepts.filter((c) => wanted.has(c.concept_id));
  const busy = concepts.filter((c) => c.state === "pending" || c.state === "generating");
  const missing = concepts.filter(
    (c) => c.state === "none" || c.state === "failed" || c.state === "outdated",
  );
  const items = concepts.reduce((n, c) => n + c.items, 0);
  const due = concepts.reduce((n, c) => n + c.due, 0);

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-zinc-600 dark:text-zinc-400">
          {busy.length > 0
            ? `Writing practice items… ${concepts.length - busy.length - missing.length} of ${concepts.length} concepts ready`
            : items > 0
              ? `${items} practice ${items === 1 ? "item" : "items"}${due ? `, ${due} due now` : ""}`
              : "No practice items yet"}
        </span>
        {missing.length > 0 && busy.length === 0 && (
          <button
            type="button"
            onClick={() => prepare.mutate(missing.map((c) => c.concept_id))}
            disabled={prepare.isPending}
            className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium disabled:opacity-50 dark:border-zinc-700"
          >
            {items > 0 ? "Prepare the rest" : "Prepare practice"}
          </button>
        )}
        {items > 0 &&
          (onPractise ? (
            <button
              type="button"
              onClick={onPractise}
              className="rounded-lg bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              Practise this stage
            </button>
          ) : (
            <Link
              href={`/environments/${encodeURIComponent(environmentId)}/practice?stage=${stageNumber}`}
              className="rounded-lg bg-zinc-900 px-2.5 py-1 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              Practise this stage
            </Link>
          ))}
      </div>
      <Problems concepts={concepts} />
      {prepare.error && (
        <p role="alert" className="text-red-600 dark:text-red-400">
          {prepare.error.message}
        </p>
      )}
    </div>
  );
}

function Problems({ concepts }: { concepts: PracticeConcept[] }) {
  const failed = concepts.filter((c) => c.state === "failed");
  const outdated = concepts.filter((c) => c.state === "outdated");
  if (!failed.length && !outdated.length) return null;
  return (
    <ul className="flex flex-col gap-1 text-xs text-zinc-600 dark:text-zinc-400">
      {failed.map((c) => (
        <li key={c.concept_id} className="text-red-600 dark:text-red-400">
          {c.name}: {c.error}
        </li>
      ))}
      {outdated.length > 0 && (
        <li>
          The material changed for {outdated.map((c) => c.name).join(", ")}; their
          earlier items are no longer practised until prepared again.
        </li>
      )}
    </ul>
  );
}

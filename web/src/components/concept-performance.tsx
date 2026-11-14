"use client";

// How each practised concept is going, on the Practice tab (decision record
// 19): its answers and how many were recalled, the current gap between
// reviews and when it comes back, weakest first. Concepts needing attention
// lead, then the lowest share recalled. From the practice overview the tab
// already has; nothing new is asked of the backend.

import Link from "next/link";

import { Empty } from "@/components/query-states";
import { formatDate } from "@/lib/format";
import type { PracticeConcept } from "@/lib/types";

export function weakestFirst(concepts: PracticeConcept[]): PracticeConcept[] {
  const share = (c: PracticeConcept) => c.recalled / c.exposures;
  return concepts
    .filter((c) => c.exposures > 0)
    .sort(
      (a, b) =>
        Number(b.attention !== null) - Number(a.attention !== null) ||
        share(a) - share(b) ||
        b.exposures - a.exposures ||
        a.name.localeCompare(b.name),
    );
}

export function ConceptPerformance({
  environmentId,
  concepts,
}: {
  environmentId: string;
  concepts: PracticeConcept[];
}) {
  const practised = weakestFirst(concepts);
  return (
    <section aria-labelledby="performance-heading" className="flex flex-col gap-3">
      <h2 id="performance-heading" className="font-medium">
        Concept performance
      </h2>
      {practised.length === 0 ? (
        <Empty>
          No answers yet. Once you practise, each concept shows how often it was
          recalled and when it comes back, weakest first.
        </Empty>
      ) : (
        <ul className="flex flex-col gap-3" aria-label="Concepts, weakest first">
          {practised.map((c) => (
            <li key={c.concept_id} className="flex flex-col gap-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                <Link
                  href={`/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(c.concept_id)}`}
                  className="min-w-0 font-medium underline decoration-zinc-400 underline-offset-2 hover:decoration-current dark:decoration-zinc-500"
                >
                  {c.name}
                </Link>
                <span className="text-xs tabular-nums text-zinc-600 dark:text-zinc-400">
                  {c.recalled} of {c.exposures} recalled
                  {c.gap_days !== null &&
                    ` · every ${c.gap_days} ${c.gap_days === 1 ? "day" : "days"}`}
                  {c.next_review_at && ` · next ${formatDate(c.next_review_at)}`}
                </span>
              </div>
              <div
                role="meter"
                aria-label={`${c.name}: share recalled`}
                aria-valuemin={0}
                aria-valuemax={c.exposures}
                aria-valuenow={c.recalled}
                aria-valuetext={`${c.recalled} of ${c.exposures} recalled`}
                className="h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
              >
                <div
                  className={`h-full rounded-full ${
                    c.attention ? "bg-amber-500" : "bg-emerald-600 dark:bg-emerald-400"
                  }`}
                  style={{ width: `${(100 * c.recalled) / c.exposures}%` }}
                />
              </div>
              {(c.attention || c.strong) && (
                <p
                  className={`text-xs ${
                    c.attention
                      ? "text-amber-700 dark:text-amber-400"
                      : "text-emerald-700 dark:text-emerald-400"
                  }`}
                >
                  {c.attention ?? "Strong: recalled after a long gap."}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

"use client";

// How each practised concept is going, on the Practice tab (decision record
// 19): its answers and how many were recalled, the current gap between
// reviews and when it comes back, weakest first. Concepts needing attention
// lead, then the lowest share recalled. From the practice overview the tab
// already has; nothing new is asked of the backend.

import Link from "next/link";

import { Empty } from "@/components/query-states";
import { Mark, SectionHead } from "@/components/ui";
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
    <section aria-labelledby="performance-heading" className="flex min-w-0 flex-col">
      <SectionHead id="performance-heading" right={practised.length ? `${practised.length} practised` : undefined}>
        Concept performance
      </SectionHead>
      {practised.length === 0 ? (
        <Empty>
          No answers yet. Once you practise, each concept shows how often it was
          recalled and when it comes back, weakest first.
        </Empty>
      ) : (
        <ul aria-label="Concepts, weakest first">
          {practised.map((c) => (
            <li key={c.concept_id} className="flex flex-col gap-1.5 border-b border-rule py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <Link
                  href={`/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(c.concept_id)}`}
                  className="min-w-0 font-semibold hover:underline hover:decoration-accent hover:underline-offset-4"
                >
                  {c.name}
                </Link>
                <span className="label text-[10px] tabular-nums text-ink-2">
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
                className="label text-xs tracking-[0.12em]"
              >
                <span aria-hidden>{recallBlocks(c.recalled, c.exposures)}</span>
              </div>
              {(c.attention || c.strong) && (
                <p className="label flex items-center gap-1.5 text-[10px]">
                  {c.attention ? <Mark /> : <span aria-hidden>●</span>}
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

// Recalled answers as filled squares out of all answers, at most ten
// squares however many answers there were.
function recallBlocks(recalled: number, exposures: number) {
  const width = Math.min(exposures, 10);
  const filled = exposures ? Math.round((width * recalled) / exposures) : 0;
  return "■".repeat(filled) + "□".repeat(width - filled);
}

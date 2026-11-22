"use client";

// How each practised concept is going, on the Practice tab (decision record
// 19): its answers and how many were recalled, the current gap between
// reviews and when it comes back, weakest first. Concepts needing attention
// lead, then the lowest share recalled. Each says in a status word why it
// needs attention or where it stands, and in a line of detail in the sans
// how it was answered and when it comes back (decision record 28). From
// the practice overview the tab already has; nothing new is asked of the
// backend.

import Link from "next/link";

import { ConceptMark, conceptStatus } from "@/components/concept-progress";
import { Empty } from "@/components/query-states";
import { SectionHead } from "@/components/ui";
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
            <li key={c.concept_id} className="flex flex-col gap-1.5 border-b border-rule py-3.5">
              <div className="flex items-baseline justify-between gap-4">
                <Link
                  href={`/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(c.concept_id)}`}
                  className="min-w-0 text-[15px] leading-[1.4] font-semibold hover:underline hover:decoration-accent hover:underline-offset-4"
                >
                  {c.name}
                </Link>
                <div
                  role="meter"
                  aria-label={`${c.name}: share recalled`}
                  aria-valuemin={0}
                  aria-valuemax={c.exposures}
                  aria-valuenow={c.recalled}
                  aria-valuetext={`${c.recalled} of ${c.exposures} recalled`}
                  className="label shrink-0 tracking-[0.12em]"
                >
                  <span aria-hidden>{recallBlocks(c.recalled, c.exposures)}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <p className={`label flex items-center gap-1.5 ${c.attention ? "text-ink" : "text-ink-2"}`}>
                  <ConceptMark concept={c} />
                  {conceptStatus(c)}
                </p>
                <p className="text-[13px] leading-[1.4] text-ink-2 tabular-nums">
                  {c.recalled} of {c.exposures} recalled
                  {c.gap_days !== null &&
                    ` · every ${c.gap_days} ${c.gap_days === 1 ? "day" : "days"}`}
                  {c.next_review_at && ` · next ${formatDate(c.next_review_at)}`}
                </p>
              </div>
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

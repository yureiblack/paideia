"use client";

// Where one roadmap stage's practice stands, with Prepare practice: shared by
// the Practice tab and the Roadmap tab's stage cards. Preparing asks the
// local model for four items per concept, written in the background one
// concept at a time; this follows along, and names any concept whose items
// could not be written, or whose material changed since.

import Link from "next/link";

import { button, Mark } from "@/components/ui";
import { usePractice, usePreparePractice } from "@/hooks/use-practice";
import type { PracticeConcept } from "@/lib/types";

export function StagePractice({
  environmentId,
  conceptIds,
  onPractise,
  stageNumber,
  compact = false,
}: {
  environmentId: string;
  conceptIds: string[];
  // On the Practice tab, start a session here; elsewhere, link to it.
  onPractise?: () => void;
  stageNumber: number;
  // A row of a table: practising is a link-style button, not an ink block.
  compact?: boolean;
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
  const due = concepts.filter((c) => c.review === "due" || c.review === "new").length;

  return (
    <div className="flex flex-col gap-2">
      <div className={`flex flex-wrap items-center gap-x-5 gap-y-2 ${compact ? "tab:flex-row-reverse tab:justify-start" : ""}`}>
        {items > 0 &&
          (onPractise ? (
            <button type="button" onClick={onPractise} className={compact ? `${button.link} text-[10px]` : button.primary}>
              Practise this stage
            </button>
          ) : (
            <Link
              href={`/environments/${encodeURIComponent(environmentId)}/practice?stage=${stageNumber}`}
              className={button.primary}
            >
              Practise this stage <span aria-hidden>→</span>
            </Link>
          ))}
        <span className="label text-[10px] text-ink-2">
          {busy.length > 0
            ? `Writing practice items… ${concepts.length - busy.length - missing.length} of ${concepts.length} concepts ready`
            : items > 0
              ? `${items} practice ${items === 1 ? "item" : "items"}${due ? `, ${due} of ${concepts.length} concepts due today` : ""}`
              : "No practice items yet"}
        </span>
        {missing.length > 0 && busy.length === 0 && (
          <button
            type="button"
            onClick={() => prepare.mutate(missing.map((c) => c.concept_id))}
            disabled={prepare.isPending}
            className={`${button.link} text-[10px]`}
          >
            {items > 0 ? "Prepare the rest" : "Prepare practice"}
          </button>
        )}
      </div>
      <Problems concepts={concepts} />
      {prepare.error && (
        <p role="alert" className="label flex items-center gap-2">
          <Mark />
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
    <ul className="flex flex-col gap-1 text-xs text-ink-2">
      {failed.map((c) => (
        <li key={c.concept_id} className="flex items-center gap-2 text-ink">
          <Mark />
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

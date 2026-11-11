"use client";

// One concept's learner state in a line, wherever the concept is shown (the
// Knowledge map explorer, the Roadmap): how often it was answered and
// recalled, when it comes back, and why it needs attention if it does. All
// of it is worked out from the learner's answers; nothing when the concept
// has never had practice items.

import { usePractice } from "@/hooks/use-practice";
import { formatDate } from "@/lib/format";

export function ConceptProgress({
  environmentId,
  conceptId,
}: {
  environmentId: string;
  conceptId: string;
}) {
  const query = usePractice(environmentId);
  const concept = query.data?.concepts.find((c) => c.concept_id === conceptId);
  if (!concept || (concept.exposures === 0 && concept.items === 0)) return null;

  let text: string;
  if (concept.exposures === 0) {
    text = "Practice ready, not practised yet.";
  } else {
    const when =
      concept.review === "due"
        ? "due for review today"
        : concept.next_review_at
          ? `next review ${formatDate(concept.next_review_at)}`
          : null;
    text = `Answered ${concept.exposures} ${concept.exposures === 1 ? "time" : "times"}, recalled ${concept.recalled}${when ? ` · ${when}` : ""}.`;
  }
  return (
    <p className="text-xs text-zinc-600 dark:text-zinc-400">
      {text}
      {concept.attention && (
        <span className="text-amber-700 dark:text-amber-400"> {concept.attention}</span>
      )}
    </p>
  );
}

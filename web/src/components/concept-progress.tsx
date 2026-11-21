"use client";

// One concept's learner state, wherever the concept is shown (the Knowledge
// map, the Roadmap): a mark for its state, and a line saying how often it
// was answered and recalled, when it comes back, and why it needs attention
// if it does. All of it is worked out from the learner's answers; nothing
// when the concept has never had practice items.

import { Mark } from "@/components/ui";
import { usePractice } from "@/hooks/use-practice";
import { formatDate } from "@/lib/format";
import type { PracticeConcept } from "@/lib/types";

// The typographic marks for a concept's state (decision record 25):
// ○ new, ◐ learning, ◷ due, ● strong, the orange square when it needs
// attention, a dash before it has practice items.
export function ConceptMark({ concept }: { concept: PracticeConcept | undefined }) {
  if (concept?.attention) return <Mark />;
  const [glyph, meaning] = !concept || (concept.items === 0 && concept.exposures === 0)
    ? ["–", "no practice yet"]
    : concept.strong
      ? ["●", "strong"]
      : concept.review === "due"
        ? ["◷", "due"]
        : concept.exposures === 0
          ? ["○", "new"]
          : ["◐", "learning"];
  return (
    <span aria-hidden title={meaning} className="label w-[7px] text-center text-[10px] text-ink-3">
      {glyph}
    </span>
  );
}

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
    <p className="label flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-2">
      <span>{text}</span>
      {concept.attention && (
        <span className="flex items-center gap-1.5 text-ink">
          <Mark />
          {concept.attention}
        </span>
      )}
    </p>
  );
}

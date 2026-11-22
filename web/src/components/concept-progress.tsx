"use client";

// One concept's learner state, wherever the concept is shown (the Knowledge
// map, the Roadmap, Practice): a mark for its state, a status word for it,
// and a line saying how often it was answered and recalled and when it
// comes back. The status word is a label; the line is detail, in the sans
// (decision record 28). All of it is worked out from the learner's answers;
// nothing when the concept has never had practice items.

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
    <span aria-hidden title={meaning} className="label w-[7px] text-center text-ink-3">
      {glyph}
    </span>
  );
}

// The status word beside the mark: why the concept needs attention, or
// where it stands. The backend writes the reason as a sentence; as a label
// it loses the full stop.
export function conceptStatus(concept: PracticeConcept): string {
  if (concept.attention) return concept.attention.replace(/\.$/, "");
  if (concept.exposures === 0) return "New — practice ready";
  if (concept.strong) return "Strong";
  if (concept.review === "due") return "Due today";
  return "On track";
}

// "5 answers · 2 recalled".
export function answersLine(concept: PracticeConcept): string {
  const answers = `${concept.exposures} ${concept.exposures === 1 ? "answer" : "answers"}`;
  return `${answers} · ${concept.recalled} recalled`;
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

  const when =
    concept.exposures === 0
      ? null
      : concept.review === "due"
        ? "due for review today"
        : concept.next_review_at
          ? `next review ${formatDate(concept.next_review_at)}`
          : null;
  return (
    <div className="flex flex-col gap-1">
      <p className={`label flex items-center gap-2 ${concept.attention ? "text-ink" : "text-ink-2"}`}>
        <ConceptMark concept={concept} />
        {conceptStatus(concept)}
      </p>
      {concept.exposures > 0 && (
        <p className="text-[13px] leading-[1.4] text-ink-2">
          {answersLine(concept)}
          {when && ` · ${when}`}
        </p>
      )}
    </div>
  );
}

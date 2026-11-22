"use client";

// An environment's status in two lines, for its row on the home screen:
// today's plan (with the orange mark when something was missed), then its
// documents, or how many are still being read.

import { Mark } from "@/components/ui";
import { useDocuments } from "@/hooks/use-documents";
import { useBudget, usePlan } from "@/hooks/use-plan";

export function PlanLine({ environmentId }: { environmentId: string }) {
  const [budget] = useBudget();
  const plan = usePlan(environmentId, budget);
  const documents = useDocuments(environmentId);

  let today: string | null = null;
  let missed = false;
  if (plan.data) {
    const { sessions, minutes } = plan.data;
    missed = sessions.some((s) => s.kind === "strengthen");
    today =
      sessions.length === 0
        ? "Nothing planned today"
        : `${sessions.length} ${sessions.length === 1 ? "session" : "sessions"} today · about ${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  }

  let material: string | null = null;
  if (documents.data) {
    const all = documents.data.length;
    const reading = documents.data.filter((d) => d.status === "uploaded" || d.status === "processing").length;
    material =
      all === 0
        ? "No documents yet"
        : reading > 0
          ? `Reading ${reading} of ${all} ${all === 1 ? "document" : "documents"}`
          : `${all} ${all === 1 ? "document" : "documents"}`;
  }

  return (
    <>
      {today && (
        <p className="flex items-center gap-2 text-[15px] leading-[1.4]">
          {missed && <Mark />}
          {today}
        </p>
      )}
      {material && <p className="text-[13px] leading-[1.4] text-ink-2">{material}</p>}
    </>
  );
}

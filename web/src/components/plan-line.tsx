"use client";

// Today's plan in a line, for an environment's card on the dashboard.

import { useBudget, usePlan } from "@/hooks/use-plan";

export function PlanLine({ environmentId }: { environmentId: string }) {
  const [budget] = useBudget();
  const query = usePlan(environmentId, budget);
  if (!query.data) return null;
  const { sessions, minutes } = query.data;
  return (
    <p className="text-sm text-zinc-700 dark:text-zinc-300">
      {sessions.length === 0
        ? "Nothing planned today"
        : `Today: ${sessions.length} ${sessions.length === 1 ? "session" : "sessions"} · ${minutes} min`}
    </p>
  );
}

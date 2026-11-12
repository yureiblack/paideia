"use client";

// The Overview tab: today's recommended study plan, then the environment's
// details, read from the cache the shell already filled.

import { TodayPlan } from "@/components/today-plan";
import { useEnvironment } from "@/hooks/use-environments";
import { formatDateTime } from "@/lib/format";

export function EnvironmentOverview({ id }: { id: string }) {
  const { data: environment } = useEnvironment(id);
  // The shell renders this tab only once the environment has loaded.
  if (!environment) return null;

  return (
    <div className="flex flex-col gap-8">
      <TodayPlan environmentId={id} />
      <dl className="grid gap-4 sm:grid-cols-[10rem_1fr]">
      <dt className="text-sm text-zinc-500">Description</dt>
      <dd>
        {environment.description ?? (
          <span className="text-zinc-500">No description yet.</span>
        )}
      </dd>
      <dt className="text-sm text-zinc-500">Created</dt>
      <dd>{formatDateTime(environment.created_at)}</dd>
      <dt className="text-sm text-zinc-500">Last updated</dt>
      <dd>{formatDateTime(environment.updated_at)}</dd>
      </dl>
    </div>
  );
}

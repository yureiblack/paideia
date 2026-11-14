"use client";

// The Overview tab, the environment's dashboard (decision record 19): the
// numbers at a glance first, then today's study plan, each roadmap stage's
// progress, the opening of the summary, the knowledge map in words, recent
// material and how recent background work ended. Every section reads data
// its own tab fetches too, and loads, fails and tries again on its own. One
// column on a phone; two below the plan on a wide screen.

import {
  AtAGlance,
  MapPreview,
  ProcessingActivity,
  RecentMaterial,
  RoadmapProgress,
  SummaryPreview,
} from "@/components/overview-sections";
import { TodayPlan } from "@/components/today-plan";
import { useEnvironment } from "@/hooks/use-environments";
import { formatDateTime } from "@/lib/format";

export function EnvironmentOverview({ id }: { id: string }) {
  const { data: environment } = useEnvironment(id);
  // The shell renders this tab only once the environment has loaded.
  if (!environment) return null;

  return (
    <div className="flex flex-col gap-10">
      <AtAGlance environmentId={id} />
      <TodayPlan environmentId={id} />
      <div className="grid gap-10 lg:grid-cols-2">
        <RoadmapProgress environmentId={id} />
        <SummaryPreview environmentId={id} />
        <MapPreview environmentId={id} />
        <RecentMaterial environmentId={id} />
        <ProcessingActivity environmentId={id} />
      </div>
      <p className="text-xs text-zinc-500">
        Created {formatDateTime(environment.created_at)} · last changed{" "}
        {formatDateTime(environment.updated_at)}
      </p>
    </div>
  );
}

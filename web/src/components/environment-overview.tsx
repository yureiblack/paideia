"use client";

// The Overview tab, the environment's front page (decision records 19 and
// 25): a headline saying what today holds, the figures at a glance, today's
// study plan, then the roadmap, recent material and background work beside
// a margin column with the summary and the map. Every section reads data
// its own tab fetches too, and loads, fails and tries again on its own.
// One column on a phone.

import {
  AtAGlance,
  MapPreview,
  OverviewHeadline,
  ProcessingActivity,
  RecentMaterial,
  RoadmapProgress,
  SummaryPreview,
} from "@/components/overview-sections";
import { TodayPlan } from "@/components/today-plan";
import { Opening, Standfirst } from "@/components/ui";
import { useEnvironment } from "@/hooks/use-environments";
import { formatDate } from "@/lib/format";

export function EnvironmentOverview({ id }: { id: string }) {
  const { data: environment } = useEnvironment(id);
  // The shell renders this tab only once the environment has loaded.
  if (!environment) return null;

  return (
    <div className="flex flex-col gap-10">
      <Opening
        kicker={
          <>
            <span aria-hidden>01 / </span>Overview
          </>
        }
        headline={<OverviewHeadline environmentId={id} />}
        aside={
          <>
            {environment.description && <Standfirst>{environment.description}</Standfirst>}
            <p className="label text-[10px] text-ink-3">
              Created {formatDate(environment.created_at)} · changed{" "}
              {formatDate(environment.updated_at)}
            </p>
          </>
        }
      />
      <AtAGlance environmentId={id} />
      <TodayPlan environmentId={id} />
      <div className="grid gap-10 tab:grid-cols-[minmax(0,1fr)_260px] desk:grid-cols-[minmax(0,1fr)_300px]">
        <div className="flex min-w-0 flex-col gap-10">
          <RoadmapProgress environmentId={id} />
          <RecentMaterial environmentId={id} />
          <ProcessingActivity environmentId={id} />
        </div>
        <div className="flex min-w-0 flex-col gap-10">
          <SummaryPreview environmentId={id} />
          <MapPreview environmentId={id} />
        </div>
      </div>
    </div>
  );
}

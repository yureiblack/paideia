"use client";

// The Overview tab, the environment's front page (decision records 19, 25
// and 28). It shows one thing first: what today holds, as a headline and
// as today's plan. The figures follow the headline in one line, every other
// section is one line of an index, and background work is folded at the
// foot. An environment with no documents yet opens instead on adding its
// first PDF, with a note on what an environment holds.

import { Note } from "@/components/note";
import {
  EnvironmentIndex,
  Figures,
  OverviewHeadline,
  ProcessingActivity,
  StartWithAPdf,
} from "@/components/overview-sections";
import { Loading } from "@/components/query-states";
import { TodayPlan } from "@/components/today-plan";
import { Opening, Standfirst } from "@/components/ui";
import { UploadZone } from "@/components/upload-zone";
import { useDocuments } from "@/hooks/use-documents";
import { useEnvironment } from "@/hooks/use-environments";
import { formatDate } from "@/lib/format";

export function EnvironmentOverview({ id }: { id: string }) {
  const { data: environment } = useEnvironment(id);
  const documents = useDocuments(id);
  // The shell renders this tab only once the environment has loaded.
  if (!environment) return null;
  if (documents.isPending) return <Loading what="the overview" lines={4} />;

  if (documents.data?.length === 0) {
    return (
      <div className="flex flex-col gap-10 desk:flex-row desk:gap-12">
        <div className="min-w-0 flex-1">
          <StartWithAPdf
            name={environment.name}
            upload={<UploadZone environmentId={id} variant="band" />}
          />
        </div>
        <Note
          id="new-environment"
          title="A new environment — what it holds"
          guideStep={1}
          className="desk:w-[300px] desk:shrink-0 desk:self-start desk:pt-8"
        >
          An environment keeps one subject together: its PDFs, their summaries, the concepts found
          in them, a roadmap and your practice. Nothing is shared with your other environments.
        </Note>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-12">
      <Opening
        kicker={
          <>
            <span aria-hidden>01 / </span>Overview
          </>
        }
        headline={<OverviewHeadline environmentId={id} />}
        below={<Figures environmentId={id} />}
        aside={
          <>
            {environment.description && <Standfirst>{environment.description}</Standfirst>}
            <p className="text-[13px] leading-[1.4] text-ink-2">
              Created {formatDate(environment.created_at)} · changed {formatDate(environment.updated_at)}
            </p>
          </>
        }
      />
      <TodayPlan environmentId={id} />
      <EnvironmentIndex environmentId={id} />
      <ProcessingActivity environmentId={id} />
    </div>
  );
}

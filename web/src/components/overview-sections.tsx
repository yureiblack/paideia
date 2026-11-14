"use client";

// The sections of the Overview tab below today's plan (decision record 19).
// Each reads data its own tab already fetches, so they share one cached copy,
// and each loads, fails and tries again on its own: one section that cannot
// load leaves the others as they are.

import Link from "next/link";
import type { ReactNode } from "react";

import { STATE_BADGE } from "@/components/environment-summary";
import { StatusBadge } from "@/components/materials";
import { Empty, QueryState } from "@/components/query-states";
import { useDocuments } from "@/hooks/use-documents";
import { useEnvironmentSummary } from "@/hooks/use-environment-summary";
import { useGraph } from "@/hooks/use-graph";
import { useJobs } from "@/hooks/use-jobs";
import { usePractice } from "@/hooks/use-practice";
import { useRoadmap } from "@/hooks/use-roadmap";
import { formatDate, formatDateTime } from "@/lib/format";
import { mapHighlights, stageProgress } from "@/lib/overview";
import type { Job, RoadmapState } from "@/lib/types";

const LINK =
  "underline decoration-zinc-400 underline-offset-2 hover:decoration-current dark:decoration-zinc-500";

const tab = (environmentId: string, segment = "") =>
  `/environments/${encodeURIComponent(environmentId)}${segment ? `/${segment}` : ""}`;

export function Section({
  id,
  title,
  href,
  more,
  children,
  wide = false,
}: {
  id: string;
  title: string;
  href?: string;
  more?: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <section
      aria-labelledby={id}
      className={`flex min-w-0 flex-col gap-3 ${wide ? "lg:col-span-2" : ""}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id={id} className="font-medium">
          {title}
        </h2>
        {href && (
          <Link href={href} className={`text-sm ${LINK}`}>
            {more}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

// The numbers at a glance: reviews due today, concepts, documents and how
// much of the roadmap is strong. A number that cannot load says so in its
// own tile.
export function AtAGlance({ environmentId }: { environmentId: string }) {
  const practice = usePractice(environmentId);
  const documents = useDocuments(environmentId);
  const roadmap = useRoadmap(environmentId);

  return (
    <section aria-label="At a glance">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Due for review today" query={practice}>
          {(p) => ({
            value: p.due_concepts,
            note:
              p.new_concepts > 0
                ? `${p.new_concepts} new to start`
                : p.next_review_at && p.due_concepts === 0
                  ? `Next ${formatDate(p.next_review_at)}`
                  : p.items === 0
                    ? "No practice yet"
                    : "concepts",
          })}
        </Stat>
        <Stat label="Concepts" query={practice}>
          {(p) => ({
            value: p.concepts.length,
            note: `${p.concepts.filter((c) => c.exposures > 0).length} practised`,
          })}
        </Stat>
        <Stat label="Documents" query={documents}>
          {(d) => ({
            value: d.length,
            note: `${d.filter((x) => x.status === "ready").length} read`,
          })}
        </Stat>
        <Stat label="Roadmap strong" query={roadmap} also={practice}>
          {(r) => {
            const stages = stageProgress(r.stages, practice.data?.concepts ?? []);
            const total = stages.reduce((n, s) => n + s.total, 0);
            const strong = stages.reduce((n, s) => n + s.strong, 0);
            return {
              value: total ? `${Math.round((100 * strong) / total)}%` : "—",
              note: total ? `${strong} of ${total} concepts` : "No roadmap yet",
            };
          }}
        </Stat>
      </dl>
    </section>
  );
}

type Tile = { value: number | string; note: string };

function Stat<T>({
  label,
  query,
  also,
  children,
}: {
  label: string;
  query: {
    data: T | undefined;
    isPending: boolean;
    isError: boolean;
    isFetching: boolean;
    refetch: () => unknown;
  };
  also?: { isPending: boolean; isError: boolean; isFetching: boolean; refetch: () => unknown };
  children: (data: T) => Tile;
}) {
  const failed = [query, also].filter((q) => q?.isError);
  const pending = query.isPending || also?.isPending;
  let body: ReactNode;
  if (failed.length > 0) {
    body = (
      <dd className="flex flex-col items-start gap-1">
        <span className="text-sm text-red-600 dark:text-red-400">Could not load.</span>
        <button
          type="button"
          onClick={() => failed.forEach((q) => q?.refetch())}
          disabled={failed.some((q) => q?.isFetching)}
          className="rounded-lg border border-zinc-300 px-2 py-0.5 text-xs font-medium disabled:opacity-50 dark:border-zinc-700"
        >
          Try again
        </button>
      </dd>
    );
  } else if (pending || query.data === undefined) {
    body = (
      <dd role="status">
        <span className="sr-only">Loading…</span>
        <span
          aria-hidden="true"
          className="block h-7 w-12 rounded bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800"
        />
      </dd>
    );
  } else {
    const { value, note } = children(query.data);
    body = (
      <dd className="flex flex-col">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        <span className="text-xs text-zinc-600 dark:text-zinc-400">{note}</span>
      </dd>
    );
  }
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
      <dt className="text-xs font-medium text-zinc-500">{label}</dt>
      {body}
    </div>
  );
}

// Each roadmap stage: how many of its concepts are strong, and practised.
export function RoadmapProgress({ environmentId }: { environmentId: string }) {
  const roadmap = useRoadmap(environmentId);
  const practice = usePractice(environmentId);
  return (
    <Section
      id="progress-heading"
      title="Roadmap progress"
      href={tab(environmentId, "roadmap")}
      more="Open the roadmap"
    >
      <QueryState query={roadmap} what="the roadmap" lines={3}>
        {(r) =>
          r.stages.length === 0 ? (
            <Empty>{roadmapEmpty(r)}</Empty>
          ) : (
            <QueryState query={practice} what="practice" lines={3}>
              {(p) => (
                <>
                  <ol className="flex flex-col gap-3" aria-label="Stages">
                    {stageProgress(r.stages, p.concepts).map((s) => (
                      <li key={s.number} className="flex flex-col gap-1">
                        <div className="flex flex-col gap-x-3 text-sm sm:flex-row sm:items-baseline sm:justify-between">
                          <Link
                            href={`${tab(environmentId, "roadmap")}#stage-${s.number}`}
                            className={`min-w-0 font-medium ${LINK}`}
                          >
                            {s.number}. {s.title}
                          </Link>
                          <span className="text-xs tabular-nums text-zinc-600 dark:text-zinc-400">
                            {s.strong} of {s.total} strong · {s.practised} practised
                          </span>
                        </div>
                        <Bar
                          label={`Stage ${s.number}`}
                          strong={s.strong}
                          practised={s.practised}
                          total={s.total}
                        />
                      </li>
                    ))}
                  </ol>
                  <p className="text-xs text-zinc-500">
                    Strong: recalled on its last answer after a gap of four days or
                    more. Practised: answered at least once.
                  </p>
                </>
              )}
            </QueryState>
          )
        }
      </QueryState>
    </Section>
  );
}

function roadmapEmpty(r: RoadmapState): ReactNode {
  if (r.state === "updating" || r.state === "waiting") {
    return "The roadmap is being worked out; its stages appear here when it is ready.";
  }
  return "The roadmap appears once concepts are extracted from the materials and the knowledge map is built.";
}

// Strong in full colour, practised but not strong lighter, the rest empty.
function Bar({
  label,
  strong,
  practised,
  total,
}: {
  label: string;
  strong: number;
  practised: number;
  total: number;
}) {
  const pct = (n: number) => (total ? (100 * n) / total : 0);
  const between = Math.max(practised - strong, 0);
  return (
    <div
      role="progressbar"
      aria-label={`${label}: strong concepts`}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={strong}
      aria-valuetext={`${strong} of ${total} strong, ${practised} practised`}
      className="flex h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
    >
      <div className="h-full bg-emerald-600 dark:bg-emerald-400" style={{ width: `${pct(strong)}%` }} />
      <div className="h-full bg-emerald-300 dark:bg-emerald-800" style={{ width: `${pct(between)}%` }} />
    </div>
  );
}

// The opening of the environment's summary.
export function SummaryPreview({ environmentId }: { environmentId: string }) {
  const query = useEnvironmentSummary(environmentId);
  return (
    <Section
      id="summary-heading"
      title="Summary"
      href={tab(environmentId, "summary")}
      more="Read the summary"
    >
      <QueryState query={query} what="the summary" lines={4}>
        {(s) => {
          const badge = STATE_BADGE[s.state];
          const overview = s.summary?.status === "ready" ? s.summary.overview : null;
          return (
            <div className="flex flex-col items-start gap-2">
              <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.style}`}>
                {badge.label}
              </span>
              {overview ? (
                <p className="line-clamp-5 text-sm leading-6">{overview}</p>
              ) : (
                <Empty>
                  {s.state === "failed" && s.error
                    ? `The summary could not be written: ${s.error}`
                    : s.state === "updating" || s.state === "waiting"
                      ? "The summary is being written from the documents' summaries."
                      : "No summary yet. It is written from the documents' summaries once they are ready."}
                </Empty>
              )}
            </div>
          );
        }}
      </QueryState>
    </Section>
  );
}

// The knowledge map in words: its size, the most connected concepts and
// where to start, each a link into the map.
export function MapPreview({ environmentId }: { environmentId: string }) {
  const query = useGraph(environmentId);
  const conceptLink = (id: string) =>
    `${tab(environmentId, "knowledge-map")}?concept=${encodeURIComponent(id)}`;
  return (
    <Section
      id="map-heading"
      title="Knowledge map"
      href={tab(environmentId, "knowledge-map")}
      more="Open the map"
    >
      <QueryState query={query} what="the knowledge map" lines={3}>
        {(g) => {
          const h = mapHighlights(g);
          if (h.concepts === 0) {
            return <Empty>No concepts yet. They are extracted from the materials once they are read.</Empty>;
          }
          return (
            <div className="flex flex-col gap-3 text-sm">
              <p>
                {h.concepts} {h.concepts === 1 ? "concept" : "concepts"},{" "}
                {h.relationships} {h.relationships === 1 ? "relationship" : "relationships"}.
                {g.state !== "up_to_date" && ` ${STATE_BADGE[g.state].label}.`}
              </p>
              {h.foundations.length > 0 && (
                <Names
                  title="Start with"
                  names={h.foundations.map((c) => ({
                    id: c.id,
                    name: c.name,
                    note: `${c.leadsTo} ${c.leadsTo === 1 ? "builds" : "build"} on it`,
                  }))}
                  href={conceptLink}
                />
              )}
              {h.connected.length > 0 ? (
                <Names
                  title="Most connected"
                  names={h.connected.map((c) => ({
                    id: c.id,
                    name: c.name,
                    note: `${c.links} ${c.links === 1 ? "link" : "links"}`,
                  }))}
                  href={conceptLink}
                />
              ) : (
                <p className="text-zinc-600 dark:text-zinc-400">
                  No relationships between the concepts yet.
                </p>
              )}
            </div>
          );
        }}
      </QueryState>
    </Section>
  );
}

function Names({
  title,
  names,
  href,
}: {
  title: string;
  names: { id: string; name: string; note: string }[];
  href: (id: string) => string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-medium text-zinc-500">{title}</h3>
      <ul className="flex flex-wrap gap-x-4 gap-y-1" aria-label={title}>
        {names.map((n) => (
          <li key={n.id}>
            <Link href={href(n.id)} className={LINK}>
              {n.name}
            </Link>{" "}
            <span className="text-xs text-zinc-500">{n.note}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// The documents most recently added or changed.
export function RecentMaterial({ environmentId }: { environmentId: string }) {
  const query = useDocuments(environmentId);
  return (
    <Section
      id="material-heading"
      title="Recent material"
      href={tab(environmentId, "materials")}
      more="All materials"
    >
      <QueryState query={query} what="the materials" lines={3}>
        {(documents) =>
          documents.length === 0 ? (
            <Empty
              action={
                <Link
                  href={tab(environmentId, "materials")}
                  className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
                >
                  Upload a PDF
                </Link>
              }
            >
              No materials yet. Upload lecture notes or readings to begin.
            </Empty>
          ) : (
            <ul className="flex flex-col gap-2" aria-label="Recent documents">
              {[...documents]
                .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
                .slice(0, 5)
                .map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="min-w-0 truncate" title={d.filename}>
                      {d.filename}
                      <span className="ml-2 text-xs text-zinc-500">{formatDate(d.updated_at)}</span>
                    </span>
                    <StatusBadge document={d} />
                  </li>
                ))}
            </ul>
          )
        }
      </QueryState>
    </Section>
  );
}

const OUTCOME: Record<Job["status"], { label: string; style: string }> = {
  queued: { label: "Queued", style: "text-zinc-600 dark:text-zinc-400" },
  running: { label: "Running", style: "text-amber-700 dark:text-amber-400" },
  succeeded: { label: "Done", style: "text-emerald-700 dark:text-emerald-400" },
  failed: { label: "Failed", style: "text-red-600 dark:text-red-400" },
  cancelled: { label: "Cancelled", style: "text-zinc-600 dark:text-zinc-400" },
};

// The background work of late, newest first. Work in progress is followed
// live in the strip above the tabs; this lists how recent work ended.
export function ProcessingActivity({ environmentId }: { environmentId: string }) {
  const query = useJobs(environmentId);
  return (
    <Section id="activity-heading" title="Processing activity" wide>
      <QueryState query={query} what="the background work" lines={3}>
        {(jobs) =>
          jobs.length === 0 ? (
            <Empty>
              No background work yet. Reading documents and everything the model writes
              shows here.
            </Empty>
          ) : (
            <ul className="flex flex-col gap-1.5 text-sm" aria-label="Recent background work">
              {jobs.slice(0, 6).map((job) => (
                <li key={job.id} className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
                  <span className={`w-20 shrink-0 text-xs font-medium ${OUTCOME[job.status].style}`}>
                    {OUTCOME[job.status].label}
                    {job.status === "running" && ` ${job.progress}%`}
                  </span>
                  <span className="min-w-0 flex-1">
                    {job.title}
                    {job.status === "failed" && job.error && (
                      <span className="text-red-600 dark:text-red-400"> · {job.error}</span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {formatDateTime(job.finished_at ?? job.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )
        }
      </QueryState>
    </Section>
  );
}

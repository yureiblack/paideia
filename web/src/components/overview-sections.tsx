"use client";

// The sections of the Overview tab (decision records 19 and 25): the
// headline, the figures at a glance, and below today's plan the roadmap,
// recent material, background work, the summary and the map. Each reads
// data its own tab already fetches, so they share one cached copy, and each
// loads, fails and tries again on its own: one section that cannot load
// leaves the others as they are.

import Link from "next/link";
import type { ReactNode } from "react";

import { STATE_BADGE } from "@/components/environment-summary";
import { StatusBadge } from "@/components/materials";
import { MathsText } from "@/components/maths-text";
import { Empty, QueryState } from "@/components/query-states";
import { button, Mark, SectionHead } from "@/components/ui";
import { useDocuments } from "@/hooks/use-documents";
import { useEnvironmentSummary } from "@/hooks/use-environment-summary";
import { useGraph } from "@/hooks/use-graph";
import { useJobs } from "@/hooks/use-jobs";
import { usePractice } from "@/hooks/use-practice";
import { useRoadmap } from "@/hooks/use-roadmap";
import { formatDate, formatDateTime } from "@/lib/format";
import { mapHighlights, stageProgress } from "@/lib/overview";
import { InWords, inWords } from "@/lib/words";
import type { Job, RoadmapState } from "@/lib/types";

const tab = (environmentId: string, segment = "") =>
  `/environments/${encodeURIComponent(environmentId)}${segment ? `/${segment}` : ""}`;

// The Overview's headline: what today holds, in one sentence.
export function OverviewHeadline({ environmentId }: { environmentId: string }) {
  const { data: p, isError } = usePractice(environmentId);
  // Today's plan below says why, with Try again.
  if (isError) return "Today, at a glance.";
  if (!p) return <span aria-hidden className="placeholder block h-[0.9em] w-3/4" />;
  const due = p.due_concepts;
  const fresh = p.new_concepts;
  const concepts = (n: number) => (n === 1 ? "concept" : "concepts");
  if (p.items === 0 && p.concepts.length === 0) return "Nothing to practise yet.";
  if (due > 0 && fresh > 0) {
    return `${InWords(due)} ${concepts(due)} due today, ${inWords(fresh)} new to start.`;
  }
  if (due > 0) return `${InWords(due)} ${concepts(due)} due today.`;
  if (fresh > 0) return `Nothing due today; ${inWords(fresh)} new to start.`;
  if (p.next_review_at) return `Nothing due today. Next review ${formatDate(p.next_review_at)}.`;
  return "Nothing due today.";
}

export function Section({
  id,
  number,
  title,
  href,
  more,
  right,
  children,
}: {
  id: string;
  number: string;
  title: string;
  href?: string;
  more?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col">
      <SectionHead
        id={id}
        right={
          href ? (
            <Link href={href} className="text-ink hover:underline hover:decoration-accent">
              {more} <span aria-hidden>→</span>
            </Link>
          ) : (
            right
          )
        }
      >
        <span aria-hidden>{number} / </span>
        {title}
      </SectionHead>
      {children}
    </section>
  );
}

// The figures at a glance: concepts, documents, how much of the roadmap is
// strong and where you are on it. A figure that cannot load says so in its
// own cell.
export function AtAGlance({ environmentId }: { environmentId: string }) {
  const practice = usePractice(environmentId);
  const documents = useDocuments(environmentId);
  const roadmap = useRoadmap(environmentId);

  return (
    <section aria-label="At a glance">
      <dl className="grid grid-cols-2 border-y border-ink tab:grid-cols-4">
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
        <Stat label="Current stage" query={roadmap} also={practice}>
          {(r) => {
            const stages = stageProgress(r.stages, practice.data?.concepts ?? []);
            const current = stages.find((s) => s.practised < s.total);
            return current
              ? { value: `${current.number}/${stages.length}`, note: current.title }
              : { value: "—", note: stages.length ? "All practised" : "No roadmap yet" };
          }}
        </Stat>
      </dl>
    </section>
  );
}

type Figure = { value: number | string; note: string };

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
  children: (data: T) => Figure;
}) {
  const failed = [query, also].filter((q) => q?.isError);
  const pending = query.isPending || also?.isPending;
  let body: ReactNode;
  if (failed.length > 0) {
    body = (
      <dd className="flex flex-col items-start gap-2">
        <span className="label flex items-center gap-2">
          <Mark />
          Could not load.
        </span>
        <button
          type="button"
          onClick={() => failed.forEach((q) => q?.refetch())}
          disabled={failed.some((q) => q?.isFetching)}
          className={button.link}
        >
          Try again
        </button>
      </dd>
    );
  } else if (pending || query.data === undefined) {
    body = (
      <dd role="status">
        <span className="sr-only">Loading…</span>
        <span aria-hidden="true" className="placeholder block h-10 w-14" />
      </dd>
    );
  } else {
    const { value, note } = children(query.data);
    body = (
      <dd className="flex flex-col gap-1.5">
        <span className="display order-first text-[38px] tabular-nums tab:text-5xl">{value}</span>
        <span className="label truncate text-ink-3">{note}</span>
      </dd>
    );
  }
  return (
    <div className="flex min-w-0 flex-col gap-1.5 border-rule py-4 pr-4 not-first:border-l not-first:pl-4 max-tab:nth-3:border-l-0 max-tab:nth-3:pl-0 max-tab:nth-[n+3]:border-t tab:not-first:pl-5">
      <dt className="label">{label}</dt>
      {body}
    </div>
  );
}

// The stages around where you are: the one before, the current one and the
// next, as lines of a table of contents.
export function RoadmapProgress({ environmentId }: { environmentId: string }) {
  const roadmap = useRoadmap(environmentId);
  const practice = usePractice(environmentId);
  return (
    <Section
      id="progress-heading"
      number="03"
      title="Roadmap"
      href={tab(environmentId, "roadmap")}
      more="Open the roadmap"
    >
      <QueryState query={roadmap} what="the roadmap" lines={3}>
        {(r) =>
          r.stages.length === 0 ? (
            <Empty>{roadmapEmpty(r)}</Empty>
          ) : (
            <QueryState query={practice} what="practice" lines={3}>
              {(p) => {
                const stages = stageProgress(r.stages, p.concepts);
                const at = Math.max(stages.findIndex((s) => s.practised < s.total), 0);
                const from = Math.max(0, Math.min(at - 1, stages.length - 3));
                const shown = stages.slice(from, from + 3);
                const rest = stages.length - shown.length;
                return (
                  <>
                    <ol aria-label="Stages near you">
                      {shown.map((s) => {
                        const current = s.number === stages[at]?.number && s.practised < s.total;
                        const done = s.total > 0 && s.practised === s.total;
                        return (
                          <li
                            key={s.number}
                            className={`flex items-center gap-3.5 border-b border-rule ${current ? "bg-paper-2 px-2.5" : ""} min-h-9 py-1.5`}
                          >
                            <span
                              aria-hidden
                              className={`label flex h-[18px] w-6 shrink-0 items-center justify-center text-[10px] ${
                                current ? "bg-accent text-on-accent" : "text-ink-3"
                              }`}
                            >
                              {String(s.number).padStart(2, "0")}
                            </span>
                            <Link
                              href={`${tab(environmentId, "roadmap")}#stage-${s.number}`}
                              className={`min-w-0 flex-1 text-sm hover:underline hover:decoration-accent ${
                                current ? "font-semibold" : done ? "" : "text-ink-2"
                              }`}
                            >
                              <span className="sr-only">Stage {s.number}: </span>
                              {s.title}
                            </Link>
                            <span className="label shrink-0 text-[10px]">
                              {done && "✓ "}
                              {s.practised} of {s.total} practised
                              <span className="hidden tab:inline"> · {s.strong} strong</span>
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                    {rest > 0 && (
                      <p className="label flex min-h-11 items-center text-ink-3">
                        {rest} more {rest === 1 ? "stage" : "stages"} in the roadmap
                      </p>
                    )}
                    <p className="label text-[10px] text-ink-3">
                      Strong: recalled on its last answer after a gap of four days or more.
                      Practised: answered at least once.
                    </p>
                  </>
                );
              }}
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

// The opening of the environment's summary, set as a quotation.
export function SummaryPreview({ environmentId }: { environmentId: string }) {
  const query = useEnvironmentSummary(environmentId);
  return (
    <Section
      id="summary-heading"
      number="06"
      title="Summary"
      href={tab(environmentId, "summary")}
      more="Read"
    >
      <QueryState query={query} what="the summary" lines={4}>
        {(s) => {
          const badge = STATE_BADGE[s.state];
          const overview = s.summary?.status === "ready" ? s.summary.overview : null;
          return (
            <div className="flex flex-col items-start gap-3">
              <span className={`label ${badge.style}`}>{badge.label}</span>
              {overview ? (
                <p className="display line-clamp-6 text-[22px] leading-[1.2] tracking-[-0.01em] italic">
                  <MathsText text={overview} />
                </p>
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

// The knowledge map in words: its size, where to start and the most
// connected concepts, each a link into the map.
export function MapPreview({ environmentId }: { environmentId: string }) {
  const query = useGraph(environmentId);
  const conceptLink = (id: string) =>
    `${tab(environmentId, "knowledge-map")}?concept=${encodeURIComponent(id)}`;
  return (
    <Section
      id="map-heading"
      number="07"
      title="Knowledge map"
      href={tab(environmentId, "knowledge-map")}
      more="Open"
    >
      <QueryState query={query} what="the knowledge map" lines={3}>
        {(g) => {
          const h = mapHighlights(g);
          if (h.concepts === 0) {
            return <Empty>No concepts yet. They are extracted from the materials once they are read.</Empty>;
          }
          return (
            <div className="flex flex-col gap-4">
              <p className="label text-ink-2">
                {h.concepts} {h.concepts === 1 ? "concept" : "concepts"},{" "}
                {h.relationships} {h.relationships === 1 ? "relationship" : "relationships"}
                {g.state !== "up_to_date" && ` · ${STATE_BADGE[g.state].label}`}
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
                <p className="text-sm text-ink-2">No relationships between the concepts yet.</p>
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
    <div className="flex flex-col gap-1.5">
      <h3 className="label text-[10px] text-ink-3">{title}</h3>
      <ul className="flex flex-col gap-1" aria-label={title}>
        {names.map((n) => (
          <li key={n.id} className="flex items-baseline gap-2">
            <Link href={href(n.id)} className="min-w-0 flex-1 text-sm hover:underline hover:decoration-accent">
              {n.name}
            </Link>
            <span className="label shrink-0 text-[10px] text-ink-3">{n.note}</span>
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
      number="04"
      title="Recent material"
      href={tab(environmentId, "materials")}
      more="All"
    >
      <QueryState query={query} what="the materials" lines={3}>
        {(documents) =>
          documents.length === 0 ? (
            <Empty
              action={
                <Link href={tab(environmentId, "materials")} className={button.primary}>
                  Upload a PDF
                </Link>
              }
            >
              No materials yet. Upload lecture notes or readings to begin.
            </Empty>
          ) : (
            <ul aria-label="Recent documents">
              {[...documents]
                .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
                .slice(0, 5)
                .map((d) => (
                  <li key={d.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-rule py-2">
                    <span className="min-w-0 flex-1 truncate text-sm" title={d.filename}>
                      {d.filename}
                    </span>
                    <span className="label text-[10px] text-ink-3">{formatDate(d.updated_at)}</span>
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

const OUTCOME: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

// The background work of late, newest first. Work in progress is followed
// live beside the contents; this lists how recent work ended.
export function ProcessingActivity({ environmentId }: { environmentId: string }) {
  const query = useJobs(environmentId);
  return (
    <Section id="activity-heading" number="05" title="Activity">
      <QueryState query={query} what="the background work" lines={3}>
        {(jobs) =>
          jobs.length === 0 ? (
            <Empty>
              No background work yet. Reading documents and everything the model writes
              shows here.
            </Empty>
          ) : (
            <ul aria-label="Recent background work">
              {jobs.slice(0, 6).map((job) => (
                <li key={job.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-rule py-2">
                  <span className="label flex w-24 shrink-0 items-center gap-1.5 text-[10px]">
                    {job.status === "failed" ? <Mark /> : <span aria-hidden>{job.status === "succeeded" ? "✓" : "—"}</span>}
                    {OUTCOME[job.status]}
                    {job.status === "running" && ` ${job.progress}%`}
                  </span>
                  <span className="min-w-0 flex-1 text-sm text-ink-2">
                    {job.title}
                    {job.status === "failed" && job.error && <span className="text-ink"> · {job.error}</span>}
                  </span>
                  <span className="label shrink-0 text-[10px] text-ink-3">
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

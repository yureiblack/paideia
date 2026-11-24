"use client";

// The sections of the Overview tab (decision records 19, 25 and 28): the
// headline, the figures in one line, and after today's plan an index of
// where to go next, grouped as the contents are, with background work
// folded at the foot. Each reads data its own tab already fetches, so they
// share one cached copy, and each loads, fails and tries again on its own:
// one line that cannot load leaves the others as they are.

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { sectionNumber } from "@/components/environment-tabs";
import { MathsText } from "@/components/maths-text";
import { Empty, QueryState } from "@/components/query-states";
import { Mark, OpenSign, SectionHead } from "@/components/ui";
import { useDocuments } from "@/hooks/use-documents";
import { useEnvironmentSummary } from "@/hooks/use-environment-summary";
import { useGraph } from "@/hooks/use-graph";
import { useJobs } from "@/hooks/use-jobs";
import { usePractice, usePracticeHistory } from "@/hooks/use-practice";
import { useRoadmap } from "@/hooks/use-roadmap";
import { formatDate, formatDateTime } from "@/lib/format";
import { mapHighlights, stageProgress } from "@/lib/overview";
import { InWords, inWords } from "@/lib/words";
import type { Job } from "@/lib/types";

const tab = (environmentId: string, segment = "") =>
  `/environments/${encodeURIComponent(environmentId)}${segment ? `/${segment}` : ""}`;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

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

// The figures in one line, where four tiles used to be: concepts and how
// many were practised, documents and how many are read, where you are on
// the roadmap and how much of it is strong. A part not loaded yet is left
// out until it is.
export function Figures({ environmentId }: { environmentId: string }) {
  const practice = usePractice(environmentId);
  const documents = useDocuments(environmentId);
  const roadmap = useRoadmap(environmentId);
  const parts: string[] = [];
  if (practice.data && practice.data.concepts.length > 0) {
    const all = practice.data.concepts;
    parts.push(`${plural(all.length, "concept")}, ${all.filter((c) => c.exposures > 0).length} practised`);
  }
  if (documents.data && documents.data.length > 0) {
    const all = documents.data.length;
    const read = documents.data.filter((d) => d.status === "ready").length;
    parts.push(`${plural(all, "document")}, ${read === all ? "all read" : `${read} read`}`);
  }
  if (roadmap.data && practice.data && roadmap.data.stages.length > 0) {
    const stages = stageProgress(roadmap.data.stages, practice.data.concepts);
    const current = stages.find((s) => s.practised < s.total);
    parts.push(current ? `stage ${current.number} of ${stages.length}` : "every stage practised");
    const strong = stages.reduce((n, s) => n + s.strong, 0);
    parts.push(strong === 0 ? "none strong yet" : `${strong} strong`);
  }
  if (parts.length === 0) return null;
  return (
    <p className="text-[14px] leading-[1.45] text-ink-2">
      {parts.join(" · ")}
    </p>
  );
}

// Where to go next: every section of the environment, as in the contents,
// with what it holds now in one sentence.
export function EnvironmentIndex({ environmentId }: { environmentId: string }) {
  return (
    <section aria-labelledby="index-heading" className="flex min-w-0 flex-col">
      <SectionHead id="index-heading">
        <span aria-hidden>03 / </span>In this environment
      </SectionHead>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 tab:grid-cols-2">
        <div role="group" aria-label="Library" className="flex flex-col">
          <p aria-hidden className="label pt-1 pb-1.5 text-ink-3">
            Library
          </p>
          <ul>
            <MaterialsLine environmentId={environmentId} />
            <SummaryLine environmentId={environmentId} />
            <MapLine environmentId={environmentId} />
            <SearchLine environmentId={environmentId} />
          </ul>
        </div>
        <div role="group" aria-label="Learn" className="flex flex-col max-tab:pt-5">
          <p aria-hidden className="label pt-1 pb-1.5 text-ink-3">
            Learn
          </p>
          <ul>
            <RoadmapLine environmentId={environmentId} />
            <PracticeLine environmentId={environmentId} />
          </ul>
        </div>
      </div>
    </section>
  );
}

type Query = { isPending: boolean; isError: boolean };

// One line of the index: the section's number and name as a link, and what
// it holds, or that it could not load.
function Line({
  environmentId,
  label,
  segment,
  query,
  children,
}: {
  environmentId: string;
  label: string;
  segment: string;
  query: Query;
  children: () => ReactNode;
}) {
  return (
    <li className="border-b border-rule">
      <Link
        href={tab(environmentId, segment)}
        className="group flex items-start gap-3.5 py-3 hover:bg-paper-2 tab:-mx-2.5 tab:px-2.5"
      >
        <span aria-hidden className="label w-6 shrink-0 pt-1.5 text-ink-3">
          {sectionNumber(label)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="display text-[24px] leading-[1.05] tracking-[-0.015em] group-hover:underline group-hover:decoration-accent group-hover:decoration-2 group-hover:underline-offset-4">
            {label}
          </span>
          <span className="text-[14px] leading-[1.45] text-ink-2">
            {query.isPending ? (
              <span aria-hidden className="placeholder block h-3.5 w-2/3" />
            ) : query.isError ? (
              <span className="flex items-center gap-2">
                <Mark />
                Could not load; open it to try again.
              </span>
            ) : (
              children()
            )}
          </span>
        </span>
        <span aria-hidden className="label pt-1.5">
          →
        </span>
      </Link>
    </li>
  );
}

function MaterialsLine({ environmentId }: { environmentId: string }) {
  const query = useDocuments(environmentId);
  return (
    <Line environmentId={environmentId} label="Materials" segment="materials" query={query}>
      {() => {
        const docs = query.data ?? [];
        if (docs.length === 0) return "No documents yet. Upload a PDF to begin.";
        const reading = docs.filter((d) => d.status === "uploaded" || d.status === "processing").length;
        const latest = [...docs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
        if (reading > 0) return `Reading ${reading} of ${plural(docs.length, "document")}.`;
        return `${plural(docs.length, "document")}, all read. The latest, ${latest.filename}, came on ${formatDate(latest.created_at)}.`;
      }}
    </Line>
  );
}

function SummaryLine({ environmentId }: { environmentId: string }) {
  const query = useEnvironmentSummary(environmentId);
  return (
    <Line environmentId={environmentId} label="Summary" segment="summary" query={query}>
      {() => {
        const s = query.data;
        const overview = s?.summary?.status === "ready" ? s.summary.overview : null;
        if (overview) {
          return (
            <span className="line-clamp-2">
              <MathsText text={overview} />
            </span>
          );
        }
        if (s?.state === "failed") return "The summary could not be written; open it to see why.";
        if (s?.state === "updating" || s?.state === "waiting") return "Being written from the documents' summaries.";
        return "Written once the documents have been read.";
      }}
    </Line>
  );
}

function MapLine({ environmentId }: { environmentId: string }) {
  const query = useGraph(environmentId);
  return (
    <Line environmentId={environmentId} label="Knowledge map" segment="knowledge-map" query={query}>
      {() => {
        if (!query.data) return null;
        const h = mapHighlights(query.data);
        if (h.concepts === 0) return "No concepts yet. They are found in the passages once a document is read.";
        const start = h.foundations[0] ?? h.connected[0];
        return `${plural(h.concepts, "concept")}, ${plural(h.relationships, "link")}.${start ? ` Start with ${start.name}.` : ""}`;
      }}
    </Line>
  );
}

function SearchLine({ environmentId }: { environmentId: string }) {
  const query = useDocuments(environmentId);
  return (
    <Line environmentId={environmentId} label="Search" segment="search" query={query}>
      {() => {
        const read = (query.data ?? []).filter((d) => d.status === "ready").length;
        if (read === 0) return "Search works once a document has been read.";
        return read === 1
          ? "Ask a question of the document."
          : `Ask a question of all ${inWords(read)} documents.`;
      }}
    </Line>
  );
}

function RoadmapLine({ environmentId }: { environmentId: string }) {
  const roadmap = useRoadmap(environmentId);
  const practice = usePractice(environmentId);
  const query = {
    isPending: roadmap.isPending || practice.isPending,
    isError: roadmap.isError || practice.isError,
  };
  return (
    <Line environmentId={environmentId} label="Roadmap" segment="roadmap" query={query}>
      {() => {
        const r = roadmap.data;
        if (!r || r.stages.length === 0) {
          return r?.state === "updating" || r?.state === "waiting"
            ? "Being worked out from the knowledge map."
            : "Made once the concepts have been found.";
        }
        const stages = stageProgress(r.stages, practice.data?.concepts ?? []);
        const current = stages.find((s) => s.practised < s.total);
        if (!current) return `${plural(stages.length, "stage")}, every one practised.`;
        return `Stage ${current.number} of ${stages.length}, ${current.title}: ${current.practised} of ${current.total} practised.`;
      }}
    </Line>
  );
}

function PracticeLine({ environmentId }: { environmentId: string }) {
  const practice = usePractice(environmentId);
  const history = usePracticeHistory(environmentId);
  return (
    <Line environmentId={environmentId} label="Practice" segment="practice" query={practice}>
      {() => {
        const p = practice.data;
        if (!p || (p.items === 0 && p.concepts.length === 0)) return "Prepared stage by stage, when you ask.";
        const now = [
          p.due_concepts > 0 ? `${p.due_concepts} to review` : null,
          p.new_concepts > 0 ? `${p.new_concepts} to start` : null,
        ].filter(Boolean);
        const last = history.data?.[0];
        const lastText = last
          ? ` Last session ${formatDate(last.ended_at)}, ${last.recalled} of ${last.answers} recalled.`
          : "";
        return `${now.length ? now.join(", ") : "Nothing due"}.${lastText}`.replace(/^./, (c) => c.toUpperCase());
      }}
    </Line>
  );
}

const OUTCOME: Record<Job["status"], string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

// The background work of late, folded to its last line. Work in progress
// is followed live beside the contents; this lists how recent work ended.
export function ProcessingActivity({ environmentId }: { environmentId: string }) {
  const query = useJobs(environmentId);
  const [open, setOpen] = useState(false);
  const jobs = query.data ?? [];
  const last = jobs[0];
  return (
    <section aria-labelledby="activity-heading" className="flex min-w-0 flex-col border-y border-rule">
      <div className="flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 py-2">
        <h2 id="activity-heading" className="label">
          Activity
        </h2>
        <p className="min-w-0 flex-1 text-[13px] leading-[1.4] text-ink-2">
          {query.isPending
            ? "Loading…"
            : query.isError
              ? "Could not load the background work."
              : last
                ? `Last: ${last.title}, ${OUTCOME[last.status].toLowerCase()} ${formatDateTime(last.finished_at ?? last.created_at)}`
                : "Nothing yet. Reading documents and everything the model writes shows here."}
        </p>
        {jobs.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-controls="activity-list"
            className="label hover:underline hover:decoration-accent"
          >
            All {Math.min(jobs.length, 6)} <OpenSign open={open} />
          </button>
        )}
      </div>
      {open && (
        <QueryState query={query} what="the background work" lines={3}>
          {(list) =>
            list.length === 0 ? (
              <Empty>No background work yet.</Empty>
            ) : (
              <ul id="activity-list" aria-label="Recent background work" className="border-t border-rule">
                {list.slice(0, 6).map((job) => (
                  <li key={job.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-rule py-2 last:border-b-0">
                    <span className="label flex w-28 shrink-0 items-center gap-1.5">
                      {job.status === "failed" ? <Mark /> : <span aria-hidden>{job.status === "succeeded" ? "✓" : "—"}</span>}
                      {OUTCOME[job.status]}
                      {job.status === "running" && ` ${job.progress}%`}
                    </span>
                    <span className="min-w-0 flex-1 text-sm text-ink-2">
                      {job.title}
                      {job.status === "failed" && job.error && <span className="text-ink"> · {job.error}</span>}
                    </span>
                    <span className="text-[13px] leading-[1.4] text-ink-2">
                      {formatDateTime(job.finished_at ?? job.created_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )
          }
        </QueryState>
      )}
    </section>
  );
}

// An environment with nothing in it yet opens on what to do first.
export function StartWithAPdf({ name, upload }: { name: string; upload: ReactNode }) {
  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-3.5">
        <p className="label max-tab:sr-only">
          <span aria-hidden>01 / </span>Overview
        </p>
        <p className="display text-[44px] leading-[0.92] tracking-[-0.03em] tab:text-[60px] desk:text-[76px]">
          Start with a PDF.
        </p>
        <p className="max-w-[600px] text-[18px] leading-[1.5] text-ink-2 tab:text-[20px]">
          Add the lecture notes, chapters or problem sheets for {name}. Everything else here is made
          from them: the summary, the knowledge map, the roadmap and practice.
        </p>
      </div>
      {upload}
      <section aria-labelledby="follows-heading" className="flex flex-col">
        <h2 id="follows-heading" className="label border-t border-ink pt-2.5">
          What follows, on its own
        </h2>
        <ol className="grid pt-4 tab:grid-cols-2 desk:grid-cols-4">
          {[
            ["Reading", "Each page as soon as it arrives. Search works from then on."],
            ["Summary and concepts", "A summary of each document that cites its pages, and the concepts in its passages."],
            ["Map and roadmap", "How the concepts build on one another, and the order to learn them in."],
            ["Practice, when you ask", "Prepared stage by stage from the roadmap. Then today's plan appears on this page."],
          ].map(([title, text], i) => (
            <li
              key={title}
              className="flex flex-col gap-1.5 border-b border-rule py-3.5 tab:border-b-0 desk:border-l desk:px-5 desk:py-0 desk:first:border-l-0 desk:first:pl-0"
            >
              <span className="label text-ink-3">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="display text-[24px] leading-[1.05] tracking-[-0.015em]">{title}</h3>
              <p className="text-[14px] leading-[1.5] text-ink-2">{text}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

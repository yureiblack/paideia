"use client";

// The Practice tab: evidence-informed study support. Items are written by the
// local model from each concept's own passages and checked before they are
// kept. Practising means answering from memory (retrieval practice), items
// coming back at growing intervals (spaced review) and concepts mixed within
// a session (interleaving). Low stakes: nothing here is a grade.
//
// At the top, what is due today (in the learner's own day) with Start
// practice; then how each practised concept is going, weakest first, with
// why one needs attention or is strong, beside the past sessions; then each
// roadmap stage with Prepare practice and Practise this stage. A session
// replaces the page until it is done.
// ?stage= (from the Roadmap tab) starts that stage's session at once, and
// ?concepts= (from today's plan) a session for those concepts.

import Link from "next/link";
import { useState } from "react";

import { ConceptPerformance } from "@/components/concept-performance";
import { PracticeHistory } from "@/components/practice-history";
import { PracticeSession } from "@/components/practice-session";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, OpenSign, SectionHead } from "@/components/ui";
import { StagePractice } from "@/components/stage-practice";
import { usePractice } from "@/hooks/use-practice";
import { useRoadmap } from "@/hooks/use-roadmap";
import { formatDateTime } from "@/lib/format";

type Session = { conceptIds: string[] | null; title: string; started: number };

export function Practice({
  environmentId,
  stage,
  focus = null,
}: {
  environmentId: string;
  stage: number | null;
  // From today's plan: a session for these concepts at once.
  focus?: { conceptIds: string[]; title: string } | null;
}) {
  const practice = usePractice(environmentId);
  const roadmap = useRoadmap(environmentId);
  const [session, setSession] = useState<Session | null>(null);
  const [fromLink, setFromLink] = useState(stage);
  const [planned, setPlanned] = useState(focus);
  const [showHow, setShowHow] = useState(false);

  if (practice.isError || roadmap.isError) {
    const failed = [practice, roadmap].filter((q) => q.isError);
    return (
      <LoadError
        what="practice"
        error={(practice.error ?? roadmap.error) as Error}
        onRetry={() => failed.forEach((q) => void q.refetch())}
        retrying={failed.some((q) => q.isFetching)}
      />
    );
  }
  if (practice.isPending || roadmap.isPending) {
    return <Loading what="practice" lines={4} />;
  }
  const stages = roadmap.data.stages;
  const linked = fromLink !== null ? stages.find((s) => s.number === fromLink) : undefined;
  const active =
    session ??
    (planned ? { ...planned, started: 0 } : null) ??
    (linked
      ? {
          conceptIds: linked.concepts.map((c) => c.id),
          title: `Stage ${linked.number}: ${linked.title}`,
          started: 0,
        }
      : null);
  if (active) {
    return (
      <PracticeSession
        environmentId={environmentId}
        conceptIds={active.conceptIds}
        started={active.started}
        title={active.title}
        onDone={() => {
          setSession(null);
          setFromLink(null);
          setPlanned(null);
        }}
      />
    );
  }

  const { items, due_concepts, new_concepts, next_review_at } = practice.data;
  const exploreHref = (id: string) =>
    `/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(id)}`;
  const today = due_concepts + new_concepts;
  const dueNow = practice.data.concepts.filter(
    (c) => c.review === "due" || c.review === "new",
  );
  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="practice-heading" className="flex flex-col gap-5">
        <div className="flex flex-col gap-4 desk:flex-row desk:items-end desk:gap-10">
          <div className="flex min-w-0 flex-1 flex-col gap-3.5">
            <h2 id="practice-heading" className="label max-tab:sr-only">
              <span aria-hidden>07 / </span>Practice
            </h2>
            <p className="display text-[44px] leading-[0.92] tracking-[-0.03em] text-balance tab:text-[60px] desk:text-[68px]">
              {items === 0
                ? "No practice items yet: prepare a stage below."
                : today > 0
                  ? `Due today: ${dueText(due_concepts, new_concepts)}.`
                  : `Nothing due today.${next_review_at ? ` Next review ${formatDateTime(next_review_at)}.` : ""}`}
            </p>
          </div>
          <div className="flex flex-col gap-3 desk:w-60 desk:shrink-0 desk:pb-1.5">
            {today > 0 && (
              <button
                type="button"
                onClick={() =>
                  setSession({ conceptIds: null, title: "Due today", started: Date.now() })
                }
                className={`${button.primary} w-full tab:w-fit`}
              >
                Start practice <span aria-hidden>→</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowHow(!showHow)}
              aria-expanded={showHow}
              className="label w-fit text-[10px] text-ink-3 hover:text-ink"
            >
              How practice works <OpenSign open={showHow} />
            </button>
          </div>
        </div>
        {showHow && (
          <p className="display max-w-3xl border-l border-ink pl-3.5 text-[17px] leading-[1.3] text-ink-2 italic">
            Study support built on well-studied techniques: answering from memory,
            coming back to concepts at growing intervals, and mixing concepts. Items are
            written by the local model from your material and checked before they are
            kept; each answer shows the passages it comes from. Nothing here is a
            grade: answers only decide when concepts come back. Each time you recall a
            concept its next review moves further away (1, 2, 4, 8, 16, then 32 days);
            a miss brings it back the next day.
          </p>
        )}
        {dueNow.length > 0 && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1.5" aria-label="Due today">
            {dueNow.map((c) => (
              <li key={c.concept_id} className="label text-[10px]">
                <Link href={exploreHref(c.concept_id)} className="border-b border-rule hover:border-accent">
                  {c.name}
                </Link>
                {c.review === "new" && <span className="text-ink-3"> (new)</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="grid gap-10 desk:grid-cols-[minmax(0,1fr)_300px]">
        <ConceptPerformance environmentId={environmentId} concepts={practice.data.concepts} />
        <PracticeHistory environmentId={environmentId} />
      </div>

      <section aria-labelledby="by-stage-heading" className="flex flex-col">
        <SectionHead id="by-stage-heading" right={`${stages.length} ${stages.length === 1 ? "stage" : "stages"}`}>
          By stage
        </SectionHead>
        {stages.length === 0 ? (
          <Empty>
            Practice is prepared stage by stage, from the roadmap, once materials have
            been read and their concepts found.
          </Empty>
        ) : (
          <ol aria-label="Stages to practise">
            {stages.map((stage) => (
              <li
                key={stage.number}
                className="flex flex-col gap-2 border-b border-rule py-3 tab:flex-row tab:items-center tab:gap-5"
              >
                <span className="label w-7 shrink-0 text-[10px] text-ink-3">
                  <span className="sr-only">Stage </span>
                  {String(stage.number).padStart(2, "0")}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <h3 className="display text-xl leading-tight">{stage.title}</h3>
                  <p className="truncate text-xs text-ink-3">
                    {stage.concepts.map((c) => c.name).join(", ")}
                  </p>
                </div>
                <div className="tab:max-w-[50%] tab:shrink-0">
                  <StagePractice
                    compact
                    environmentId={environmentId}
                    conceptIds={stage.concepts.map((c) => c.id)}
                    stageNumber={stage.number}
                    onPractise={() =>
                      setSession({
                        conceptIds: stage.concepts.map((c) => c.id),
                        title: `Stage ${stage.number}: ${stage.title}`,
                        started: Date.now(),
                      })
                    }
                  />
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function dueText(due: number, fresh: number): string {
  const concepts = (n: number) => (n === 1 ? "concept" : "concepts");
  if (due === 0) return `${fresh} new ${concepts(fresh)}`;
  if (fresh === 0) return `${due} ${concepts(due)}`;
  return `${due} ${concepts(due)}, and ${fresh} new`;
}

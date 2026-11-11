"use client";

// The Practice tab: evidence-informed study support. Items are written by the
// local model from each concept's own passages and checked before they are
// kept. Practising means answering from memory (retrieval practice), items
// coming back at growing intervals (spaced review) and concepts mixed within
// a session (interleaving). Low stakes: nothing here is a grade.
//
// At the top, what is due; below, each roadmap stage with Prepare practice
// and Practise this stage. A session replaces the page until it is done.
// ?stage= (from the Roadmap tab) starts that stage's session at once.

import { useState } from "react";

import { PracticeSession } from "@/components/practice-session";
import { StagePractice } from "@/components/stage-practice";
import { usePractice } from "@/hooks/use-practice";
import { useRoadmap } from "@/hooks/use-roadmap";
import { formatDateTime } from "@/lib/format";

type Session = { conceptIds: string[] | null; title: string; started: number };

export function Practice({
  environmentId,
  stage,
}: {
  environmentId: string;
  stage: number | null;
}) {
  const practice = usePractice(environmentId);
  const roadmap = useRoadmap(environmentId);
  const [session, setSession] = useState<Session | null>(null);
  const [fromLink, setFromLink] = useState(stage);

  if (practice.isPending || roadmap.isPending) {
    return <p className="text-zinc-500">Loading practice…</p>;
  }
  if (practice.isError || roadmap.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not load practice: {(practice.error ?? roadmap.error)?.message}
      </p>
    );
  }
  const stages = roadmap.data.stages;
  const linked = fromLink !== null ? stages.find((s) => s.number === fromLink) : undefined;
  const active =
    session ??
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
        }}
      />
    );
  }

  const { due, items, next_due_at } = practice.data;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="practice-heading" className="flex flex-col gap-3">
        <h2 id="practice-heading" className="font-medium">
          Practice
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Study support built on well-studied techniques: answering from memory,
          coming back to items at growing intervals, and mixing concepts. Items are
          written by the local model from your material and checked before they are
          kept; each answer shows the passages it comes from. Nothing here is a
          grade: answers only decide when items come back.
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
          <p className="text-sm">
            {items === 0
              ? "No practice items yet: prepare a stage below."
              : due > 0
                ? `${due} ${due === 1 ? "item is" : "items are"} due now, of ${items}.`
                : `Nothing due now. ${next_due_at ? `Next item due ${formatDateTime(next_due_at)}.` : ""}`}
          </p>
          {due > 0 && (
            <button
              type="button"
              onClick={() =>
                setSession({ conceptIds: null, title: "Due items", started: Date.now() })
              }
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              Start practice
            </button>
          )}
        </div>
      </section>

      {stages.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Practice is prepared stage by stage, from the roadmap, once materials have
          been read and their concepts found.
        </p>
      ) : (
        <ol className="flex flex-col gap-3" aria-label="Stages to practise">
          {stages.map((stage) => (
            <li
              key={stage.number}
              className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                Stage {stage.number}
              </p>
              <h3 className="font-semibold">{stage.title}</h3>
              <p className="text-xs text-zinc-500">
                {stage.concepts.map((c) => c.name).join(", ")}
              </p>
              <StagePractice
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
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

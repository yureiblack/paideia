"use client";

// The Roadmap tab: the environment's concepts as an ordered path, in stages.
// The order comes from the knowledge graph by fixed rules: what a concept
// builds on comes before it, and otherwise the material's own order. Only
// each stage's title and one-sentence description are written by the local
// model, and they are marked as such; until one is written, a stage shows a
// plain title. Every concept shows what it builds on, links to the Knowledge
// map, and opens the passages explaining it. Concepts whose prerequisites
// loop are named above, to be learned together.

import Link from "next/link";

import { CitationChips } from "@/components/cited-points";
import { STATE_BADGE } from "@/components/environment-summary";
import { StagePractice } from "@/components/stage-practice";
import { useRequestRoadmap, useRoadmap } from "@/hooks/use-roadmap";
import type { RoadmapConcept, RoadmapStage, RoadmapState } from "@/lib/types";

export function LearningRoadmap({ environmentId }: { environmentId: string }) {
  const query = useRoadmap(environmentId);
  const update = useRequestRoadmap(environmentId);

  if (query.isPending) {
    return <p className="text-zinc-500">Loading the roadmap…</p>;
  }
  if (query.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not load the roadmap: {query.error.message}
      </p>
    );
  }
  const { state, stages, cycles } = query.data;
  const badge = STATE_BADGE[state];
  const count = stages.reduce((n, s) => n + s.concepts.length, 0);
  const explore = (id: string) =>
    `/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(id)}`;

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="roadmap-heading" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
          <h2 id="roadmap-heading" className="font-medium">
            Learning roadmap
          </h2>
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.style}`}>
            {badge.label}
          </span>
          {stages.length > 0 && (
            <span className="text-zinc-600 dark:text-zinc-400">
              {stages.length} {stages.length === 1 ? "stage" : "stages"} · {count}{" "}
              {count === 1 ? "concept" : "concepts"}
            </span>
          )}
        </div>
        <RoadmapNote roadmap={query.data} />
        {(state === "stale" || state === "failed") && (
          <div className="flex flex-col items-start gap-2">
            <button
              type="button"
              onClick={() => update.mutate()}
              disabled={update.isPending}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {state === "failed" ? "Try again" : "Update now"}
            </button>
            {update.error && (
              <p role="alert" className="text-sm text-red-600 dark:text-red-400">
                {update.error.message}
              </p>
            )}
          </div>
        )}
      </section>

      {cycles.length > 0 && (
        <div
          role="note"
          className="flex flex-col gap-1 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950"
        >
          <p className="font-medium">Learn these together</p>
          {cycles.map((cycle) => (
            <p key={cycle.concepts.map((c) => c.id).join()}>
              {cycle.concepts.map((c) => c.name).join(", ")}: the material makes
              each a prerequisite of another, so no order comes first.
            </p>
          ))}
        </div>
      )}

      {stages.length > 0 && (
        <ol className="flex flex-col gap-4" aria-label="Stages">
          {stages.map((stage) => (
            <li key={stage.number}>
              <StageCard environmentId={environmentId} stage={stage} explore={explore} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function RoadmapNote({ roadmap }: { roadmap: RoadmapState }) {
  const { state, error } = roadmap;
  const note = {
    up_to_date:
      "The order comes from the knowledge graph: what a concept builds on comes before it, and otherwise the order of your material. Stage titles and descriptions are written by the local model.",
    updating: "The local model is writing the titles of new stages…",
    waiting:
      "The knowledge graph is still being built; the roadmap's titles are written once it is done.",
    stale: "The stages have changed since their titles were written.",
    failed: `The stage titles could not be written: ${error} The stages and their order are shown regardless.`,
    none: "No roadmap yet. Once materials have been read and their concepts found, they appear here as an ordered path.",
  }[state];
  return (
    <p
      role={state === "failed" ? "alert" : "status"}
      className={`text-sm ${state === "failed" ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400"}`}
    >
      {note}
    </p>
  );
}

function StageCard({
  environmentId,
  stage,
  explore,
}: {
  environmentId: string;
  stage: RoadmapStage;
  explore: (id: string) => string;
}) {
  return (
    <article
      aria-labelledby={`stage-${stage.number}`}
      className="flex flex-col gap-4 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
    >
      <header className="flex flex-col gap-1">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Stage {stage.number}
        </p>
        <h3 id={`stage-${stage.number}`} className="text-lg font-semibold">
          {stage.title}
        </h3>
        {stage.description && <p className="text-sm">{stage.description}</p>}
        <p className="text-xs text-zinc-500">
          {stage.written
            ? "Title and description written by the local model."
            : "Plain title, until the local model writes one."}{" "}
          From {stage.documents.map((d) => d.filename).join(", ")}.
        </p>
        <StagePractice
          environmentId={environmentId}
          conceptIds={stage.concepts.map((c) => c.id)}
          stageNumber={stage.number}
        />
      </header>
      <ol className="flex flex-col gap-3" aria-label={`Concepts in stage ${stage.number}`}>
        {stage.concepts.map((concept) => (
          <li key={concept.id}>
            <ConceptStep
              environmentId={environmentId}
              concept={concept}
              explore={explore}
            />
          </li>
        ))}
      </ol>
    </article>
  );
}

function ConceptStep({
  environmentId,
  concept,
  explore,
}: {
  environmentId: string;
  concept: RoadmapConcept;
  explore: (id: string) => string;
}) {
  return (
    <div className="flex flex-col gap-1.5 border-l-2 border-zinc-200 pl-3 dark:border-zinc-800">
      <Link
        href={explore(concept.id)}
        className="w-fit font-medium underline decoration-zinc-400 underline-offset-4 hover:decoration-current dark:decoration-zinc-500"
      >
        {concept.name}
      </Link>
      <p className="text-sm">{concept.definition}</p>
      {concept.builds_on.length > 0 && (
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          Builds on{" "}
          {concept.builds_on.map((c, n) => (
            <span key={c.id}>
              {n > 0 && ", "}
              <Link
                href={explore(c.id)}
                className="underline decoration-zinc-400 underline-offset-2 hover:decoration-current dark:decoration-zinc-500"
              >
                {c.name}
              </Link>
            </span>
          ))}
          {concept.in_cycle && " (learned together)"}
        </p>
      )}
      <CitationChips
        environmentId={environmentId}
        citations={concept.evidence}
        showFilename
      />
    </div>
  );
}

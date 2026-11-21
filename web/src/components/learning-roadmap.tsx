"use client";

// The Roadmap tab, set as a table of contents (decision record 25): the
// environment's concepts as an ordered path, in stages. The order comes
// from the knowledge graph by fixed rules: what a concept builds on comes
// before it, and otherwise the material's own order. Only each stage's
// title and one-sentence description are written by the local model, and
// they are marked as such; until one is written, a stage shows a plain
// title. The stage you are on is open; any other opens in place, or by its
// link (#stage-N). Every concept shows what it builds on, links to the
// Knowledge map, and opens the passages explaining it. Concepts whose
// prerequisites loop are named above, to be learned together.

import Link from "next/link";
import { useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { ConceptMark, ConceptProgress } from "@/components/concept-progress";
import { STATE_BADGE } from "@/components/environment-summary";
import { MathsText } from "@/components/maths-text";
import { StagePractice } from "@/components/stage-practice";
import { Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import { usePractice } from "@/hooks/use-practice";
import { useRequestRoadmap, useRoadmap } from "@/hooks/use-roadmap";
import { stageProgress, type StageProgress } from "@/lib/overview";
import type { RoadmapConcept, RoadmapStage, RoadmapState } from "@/lib/types";
import { InWords } from "@/lib/words";

const ORDINALS = [
  "", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
  "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
  "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
];

export function LearningRoadmap({ environmentId }: { environmentId: string }) {
  const query = useRoadmap(environmentId);
  const practice = usePractice(environmentId);
  const update = useRequestRoadmap(environmentId);
  const kicker = (
    <p className="label max-tab:sr-only">
      <span aria-hidden>05 / </span>Roadmap
    </p>
  );

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-4">
        {kicker}
        <Loading what="the roadmap" lines={4} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="flex flex-col gap-4">
        {kicker}
        <LoadError
          what="the roadmap"
          error={query.error}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      </div>
    );
  }
  const { state, stages, cycles } = query.data;
  const badge = STATE_BADGE[state];
  const count = stages.reduce((n, s) => n + s.concepts.length, 0);
  const explore = (id: string) =>
    `/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(id)}`;
  const progress = stageProgress(stages, practice.data?.concepts ?? []);
  const current = progress.find((s) => s.practised < s.total)?.number ?? null;
  const headline =
    stages.length === 0
      ? "No roadmap yet."
      : current === null
        ? `${InWords(stages.length)} ${stages.length === 1 ? "stage" : "stages"}, all practised.`
        : `${InWords(stages.length)} ${stages.length === 1 ? "stage" : "stages"}.\nYou are on the ${ORDINALS[current] ?? `stage ${current}`}.`;

  return (
    <div className="flex flex-col gap-9">
      <section aria-labelledby="roadmap-heading" className="flex flex-col gap-4 desk:flex-row desk:items-end desk:gap-10">
        <h2 id="roadmap-heading" className="sr-only">
          Learning roadmap
        </h2>
        <div className="flex min-w-0 flex-1 flex-col gap-3.5">
          {kicker}
          <p className="display text-[44px] leading-[0.92] tracking-[-0.03em] whitespace-pre-line tab:text-[60px] desk:text-[64px]">
            {headline}
          </p>
        </div>
        <div className="flex flex-col gap-2 desk:w-60 desk:shrink-0 desk:pb-1.5">
          <p className={`label text-[10px] ${badge.style}`}>{badge.label}</p>
          {stages.length > 0 && (
            <p className="label text-[10px] text-ink-2">
              {stages.length} {stages.length === 1 ? "stage" : "stages"} · {count}{" "}
              {count === 1 ? "concept" : "concepts"}
            </p>
          )}
          <RoadmapNote roadmap={query.data} />
          {(state === "stale" || state === "failed") && (
            <div className="flex flex-col items-start gap-2 pt-1">
              <button
                type="button"
                onClick={() => update.mutate()}
                disabled={update.isPending}
                className={button.primary}
              >
                {state === "failed" ? "Try again" : "Update now"}
              </button>
              {update.error && (
                <p role="alert" className="label flex items-center gap-2">
                  <Mark />
                  {update.error.message}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {cycles.length > 0 && (
        <div role="note" className="flex flex-col gap-1.5 border border-ink p-4">
          <p className="label flex items-center gap-2">
            <Mark />
            Learn these together
          </p>
          {cycles.map((cycle) => (
            <p key={cycle.concepts.map((c) => c.id).join()} className="text-sm text-ink-2">
              {cycle.concepts.map((c) => c.name).join(", ")}: the material makes
              each a prerequisite of another, so no order comes first.
            </p>
          ))}
        </div>
      )}

      {stages.length > 0 && (
        <StageList
          environmentId={environmentId}
          stages={stages}
          progress={progress}
          current={current}
          explore={explore}
        />
      )}
    </div>
  );
}

function StageList({
  environmentId,
  stages,
  progress,
  current,
  explore,
}: {
  environmentId: string;
  stages: RoadmapStage[];
  progress: StageProgress[];
  current: number | null;
  explore: (id: string) => string;
}) {
  // The stage a link points at (#stage-3) opens as well as the current one.
  const [opened, setOpened] = useState<Set<number>>(() => {
    const hash = typeof window === "undefined" ? "" : window.location.hash;
    const linked = Number(/^#stage-(\d+)$/.exec(hash)?.[1]);
    return new Set(linked ? [linked] : []);
  });
  const toggle = (n: number) => {
    const next = new Set(opened);
    if (next.has(n)) next.delete(n);
    else next.add(n);
    setOpened(next);
  };
  return (
    <ol className="border-t border-ink" aria-label="Stages">
      {stages.map((stage, index) => {
        const isCurrent = stage.number === current;
        // The current stage starts open; toggling it closes it.
        const open = isCurrent ? !opened.has(stage.number) : opened.has(stage.number);
        return (
          <li key={stage.number} id={`stage-${stage.number}`} className="scroll-mt-6">
            <StageCard
              environmentId={environmentId}
              stage={stage}
              progress={progress[index]}
              isCurrent={isCurrent}
              open={open}
              onToggle={() => toggle(stage.number)}
              explore={explore}
            />
          </li>
        );
      })}
    </ol>
  );
}

function RoadmapNote({ roadmap }: { roadmap: RoadmapState }) {
  const [open, setOpen] = useState(false);
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
  const quiet = state === "up_to_date";
  return (
    <div className="flex flex-col gap-2">
      {quiet && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="label w-fit text-[10px] text-ink-3 hover:text-ink"
        >
          How the order is made <OpenSign open={open} />
        </button>
      )}
      {(!quiet || open) && (
        <p
          role={state === "failed" ? "alert" : "status"}
          className={`text-sm leading-snug ${state === "failed" ? "text-ink" : "text-ink-2"}`}
        >
          {note}
        </p>
      )}
    </div>
  );
}

function StageCard({
  environmentId,
  stage,
  progress,
  isCurrent,
  open,
  onToggle,
  explore,
}: {
  environmentId: string;
  stage: RoadmapStage;
  progress: StageProgress | undefined;
  isCurrent: boolean;
  open: boolean;
  onToggle: () => void;
  explore: (id: string) => string;
}) {
  const total = progress?.total ?? stage.concepts.length;
  const practised = progress?.practised ?? 0;
  const done = total > 0 && practised === total;
  return (
    <article
      aria-labelledby={`stage-title-${stage.number}`}
      className={`flex flex-col ${isCurrent ? "border-b border-ink bg-paper-2 px-4 tab:px-6" : "border-b border-rule"}`}
    >
      <header className={`flex items-center gap-4 tab:gap-6 ${isCurrent ? "py-5" : "py-3.5"}`}>
        <span
          aria-hidden
          className={`display w-11 shrink-0 tab:w-16 ${isCurrent ? "text-[40px] tab:text-[52px]" : "text-[26px] tab:text-[30px]"} ${
            practised || isCurrent ? "" : "text-ink-3"
          }`}
        >
          {String(stage.number).padStart(2, "0")}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className={isCurrent ? "label flex items-center gap-1.5 text-[10px]" : "sr-only"}>
            {isCurrent && <Mark />}
            Stage {stage.number}
            {isCurrent && " · you are here"}
          </p>
          <h3
            id={`stage-title-${stage.number}`}
            className={`display leading-[1.05] ${isCurrent ? "text-[26px] tracking-[-0.02em] tab:text-[34px]" : "text-[19px] tab:text-[22px]"} ${
              practised || isCurrent ? "" : "text-ink-2"
            }`}
          >
            {stage.title}
          </h3>
        </div>
        <span aria-hidden className="label hidden tracking-[0.15em] tab:block">
          {"■".repeat(practised)}
          {"□".repeat(Math.max(total - practised, 0))}
        </span>
        <span className="label w-14 shrink-0 text-right text-[10px]">
          {done && <span aria-hidden>✓ </span>}
          {practised}/{total}
          <span className="sr-only"> practised</span>
        </span>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={`${open ? "Close" : "Open"} stage ${stage.number}`}
          className="label flex size-10 shrink-0 items-center justify-center text-ink-3 hover:text-ink tab:size-auto"
        >
          <OpenSign open={open} />
        </button>
      </header>
      {open && (
        <div className="flex flex-col gap-4 pb-5 tab:pl-[88px]">
          {stage.description && (
            <p className="display max-w-3xl text-[19px] leading-[1.25] text-ink-2 italic tab:text-[21px]">
              <MathsText text={stage.description} />
            </p>
          )}
          <StagePractice
            environmentId={environmentId}
            conceptIds={stage.concepts.map((c) => c.id)}
            stageNumber={stage.number}
          />
          <p className="text-xs text-ink-3">
            {stage.written
              ? "Title and description written by the local model."
              : "Plain title, until the local model writes one."}{" "}
            From {stage.documents.map((d) => d.filename).join(", ")}.
          </p>
          <ol className="border-t border-ink" aria-label={`Concepts in stage ${stage.number}`}>
            {stage.concepts.map((concept) => (
              <li key={concept.id} className="border-b border-rule">
                <ConceptStep environmentId={environmentId} concept={concept} explore={explore} />
              </li>
            ))}
          </ol>
        </div>
      )}
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
  const practice = usePractice(environmentId);
  const state = practice.data?.concepts.find((c) => c.concept_id === concept.id);
  return (
    <div className="flex gap-3.5 py-3">
      <span className="flex w-3 shrink-0 justify-center pt-1.5">
        <ConceptMark concept={state} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Link
          href={explore(concept.id)}
          className="w-fit font-semibold hover:underline hover:decoration-accent hover:underline-offset-4"
        >
          {concept.name}
        </Link>
        <p className="max-w-3xl text-sm leading-normal text-ink-2">
          <MathsText text={concept.definition} />
        </p>
        <ConceptProgress environmentId={environmentId} conceptId={concept.id} />
        {concept.builds_on.length > 0 && (
          <p className="label text-[10px] text-ink-2">
            <span aria-hidden>← </span>Builds on{" "}
            {concept.builds_on.map((c, n) => (
              <span key={c.id}>
                {n > 0 && ", "}
                <Link href={explore(c.id)} className="border-b border-rule hover:border-accent">
                  {c.name}
                </Link>
              </span>
            ))}
            {concept.in_cycle && " (learned together)"}
          </p>
        )}
        <CitationChips environmentId={environmentId} citations={concept.evidence} showFilename />
      </div>
    </div>
  );
}

"use client";

// The Roadmap tab, set as a table of contents (decision record 25): the
// environment's concepts as an ordered path, in stages. The order comes
// from the knowledge graph by fixed rules: what a concept builds on comes
// before it, and otherwise the material's own order. Only each stage's
// title and one-sentence description are written by the local model, and
// they are marked as such; until one is written, a stage shows a plain
// title. The stage you are on is open; any other opens in place, or by its
// link (#stage-N). Every concept shows what it builds on, how its practice
// is going, links to the Knowledge map, and opens the passages explaining
// it, its sources written out in full. Concepts whose prerequisites loop
// are named above, to be learned together. Sentences and details are in
// the sans; the mono is kept for counts and status words (decision
// record 28).

import Link from "next/link";
import { useState } from "react";

import { sourceLabel } from "@/components/cited-points";
import { answersLine, ConceptMark } from "@/components/concept-progress";
import { STATE_BADGE } from "@/components/environment-summary";
import { sectionNumber } from "@/components/environment-tabs";
import { MathsText } from "@/components/maths-text";
import { Note } from "@/components/note";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { SourcePanel } from "@/components/source-panel";
import { StagePractice } from "@/components/stage-practice";
import { button, Mark, OpenSign, Opening } from "@/components/ui";
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
    <>
      <span aria-hidden>{sectionNumber("Roadmap")} / </span>Roadmap
    </>
  );

  if (query.isPending || query.isError) {
    return (
      <div className="flex flex-col gap-4">
        <p className="label max-tab:sr-only">{kicker}</p>
        {query.isPending ? (
          <Loading what="the roadmap" lines={4} />
        ) : (
          <LoadError
            what="the roadmap"
            error={query.error}
            onRetry={() => void query.refetch()}
            retrying={query.isFetching}
          />
        )}
      </div>
    );
  }
  const { state, stages, cycles } = query.data;
  const badge = STATE_BADGE[state];
  const explore = (id: string) =>
    `/environments/${encodeURIComponent(environmentId)}/knowledge-map?concept=${encodeURIComponent(id)}`;
  const progress = stageProgress(stages, practice.data?.concepts ?? []);
  const current = progress.find((s) => s.practised < s.total)?.number ?? null;
  const updateAction = (state === "stale" || state === "failed") && (
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
        <p role="alert" className="flex items-center gap-2.5 text-[13px] leading-[1.4]">
          <Mark />
          {update.error.message}
        </p>
      )}
    </div>
  );

  if (stages.length === 0) {
    return (
      <section aria-labelledby="roadmap-heading" className="flex flex-col gap-6">
        <h2 id="roadmap-heading" className="sr-only">
          Learning roadmap
        </h2>
        <p className="label max-tab:sr-only">{kicker}</p>
        <Empty
          title="No roadmap yet."
          action={
            updateAction || (
              <Link
                href={`/environments/${encodeURIComponent(environmentId)}/materials`}
                className={button.link}
              >
                See what is being read <span aria-hidden>→</span>
              </Link>
            )
          }
        >
          The roadmap puts the concepts in stages once they have been found: what a concept
          builds on comes first. It appears here on its own.
        </Empty>
        {(state === "updating" || state === "waiting" || state === "failed") && (
          <div className="max-w-[640px]">
            <RoadmapNote roadmap={query.data} />
          </div>
        )}
      </section>
    );
  }

  const headline =
    current === null ? (
      `${InWords(stages.length)} ${stages.length === 1 ? "stage" : "stages"}, all practised.`
    ) : (
      <>
        {InWords(stages.length)} {stages.length === 1 ? "stage" : "stages"}.
        <br />
        You are on the {ORDINALS[current] ?? `stage ${current}`}.
      </>
    );

  return (
    <div className="flex flex-col gap-9">
      <section aria-labelledby="roadmap-heading" className="flex flex-col">
        <h2 id="roadmap-heading" className="sr-only">
          Learning roadmap
        </h2>
        <Opening
          kicker={kicker}
          headline={headline}
          aside={
            <>
              {state !== "up_to_date" && <p className={`label ${badge.style}`}>{badge.label}</p>}
              <p className="text-[15px] leading-[1.55] text-ink-2">
                What a concept builds on comes before it; otherwise the order of your material.
              </p>
              <RoadmapNote roadmap={query.data} />
              {updateAction}
            </>
          }
        />
      </section>

      <Note id="roadmap" title="The roadmap — how the order is made" guideStep={4}>
        What a concept builds on comes before it; otherwise the order of your material.
        Nothing is locked: practise any stage you like.
      </Note>

      {cycles.length > 0 && (
        <div role="note" className="flex flex-col gap-1.5 border border-ink p-4">
          <p className="label flex items-center gap-2">
            <Mark />
            Learn these together
          </p>
          {cycles.map((cycle) => (
            <p key={cycle.concepts.map((c) => c.id).join()} className="text-[15px] leading-[1.55] text-ink-2">
              {cycle.concepts.map((c) => c.name).join(", ")}: the material makes
              each a prerequisite of another, so no order comes first.
            </p>
          ))}
        </div>
      )}

      <StageList
        environmentId={environmentId}
        stages={stages}
        progress={progress}
        current={current}
        explore={explore}
      />
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

// How the order is made: folded away while all is well, said at once when
// the roadmap is being made or something went wrong.
function RoadmapNote({ roadmap }: { roadmap: RoadmapState }) {
  const [open, setOpen] = useState(false);
  const { state, error } = roadmap;
  const note = {
    up_to_date:
      "The order comes from the knowledge graph, by fixed rules. Only each stage's title and description are written by the local model.",
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
          className="label w-fit text-left text-ink-2 hover:text-ink"
        >
          How the order is made <OpenSign open={open} />
        </button>
      )}
      {(!quiet || open) && (
        <p
          role={state === "failed" ? "alert" : "status"}
          className={`text-[13px] leading-[1.5] ${state === "failed" ? "text-ink" : "text-ink-2"}`}
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
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {isCurrent ? (
            <p className="label flex items-center gap-1.5">
              <Mark />
              <span className="sr-only">Stage {stage.number} · </span>
              You are here
            </p>
          ) : (
            <p className="sr-only">Stage {stage.number}</p>
          )}
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
        <span className="label w-14 shrink-0 text-right">
          {done && <span aria-hidden>✓ </span>}
          {practised}/{total}
          <span className="sr-only"> practised</span>
        </span>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-label={`${open ? "Close" : "Open"} stage ${stage.number}`}
          className="label flex size-10 shrink-0 items-center justify-center text-ink-2 hover:text-ink tab:size-auto"
        >
          <OpenSign open={open} />
        </button>
      </header>
      {open && (
        <div className="flex flex-col gap-5 pb-6 tab:pl-[88px]">
          {stage.description && (
            <p className="max-w-[640px] text-[17px] leading-[1.55] text-ink-2">
              <MathsText text={stage.description} />
            </p>
          )}
          <StagePractice
            environmentId={environmentId}
            conceptIds={stage.concepts.map((c) => c.id)}
            stageNumber={stage.number}
          />
          <ol className="border-t border-ink" aria-label={`Concepts in stage ${stage.number}`}>
            {stage.concepts.map((concept) => (
              <li key={concept.id} className="border-b border-rule">
                <ConceptStep environmentId={environmentId} concept={concept} explore={explore} />
              </li>
            ))}
          </ol>
          <p className="text-[13px] leading-[1.4] text-ink-2">
            {stage.written
              ? "Title and description written by the local model."
              : "Plain title, until the local model writes one."}{" "}
            From {stage.documents.map((d) => d.filename).join(", ")}.
          </p>
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
  // The source whose passage is open under the row, by chunk id.
  const [open, setOpen] = useState<string | null>(null);
  const sources = concept.evidence.filter(
    (c, index) => concept.evidence.findIndex((d) => d.chunk_id === c.chunk_id) === index,
  );
  return (
    <div className="flex flex-col gap-3 py-3">
      <div className="flex gap-3.5">
        <span className="flex w-3 shrink-0 justify-center pt-1">
          <ConceptMark concept={state} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-2 tab:flex-row tab:gap-6">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <Link
              href={explore(concept.id)}
              className="w-fit text-[15px] leading-[1.4] font-semibold hover:underline hover:decoration-accent hover:underline-offset-4"
            >
              {concept.name}
            </Link>
            <p className="max-w-[640px] text-[13px] leading-[1.45] text-ink-2">
              <MathsText text={concept.definition} />
              {concept.builds_on.length > 0 && (
                <>
                  {" "}
                  <span aria-hidden>← </span>
                  <span className="sr-only">Builds on </span>
                  {concept.builds_on.map((c, n) => (
                    <span key={c.id}>
                      {n > 0 && ", "}
                      <Link href={explore(c.id)} className="border-b border-rule hover:border-accent">
                        {c.name}
                      </Link>
                    </span>
                  ))}
                  {concept.in_cycle && " (learned together)"}
                </>
              )}
            </p>
          </div>
          {state && (
            <div className="tab:w-36 tab:shrink-0 tab:text-right">
              {state.exposures > 0 ? (
                <p className="text-[13px] leading-[1.4] text-ink-2">
                  {answersLine(state)}
                  {state.attention && <span className="sr-only"> · {state.attention}</span>}
                </p>
              ) : (
                <p className="label pt-px text-ink-2">Not practised</p>
              )}
            </div>
          )}
          {sources.length > 0 && (
            <ul aria-label={`Sources for ${concept.name}`} className="flex flex-col gap-0.5 tab:w-40 tab:shrink-0 tab:items-end">
              {sources.map((citation) => {
                const isOpen = open === citation.chunk_id;
                return (
                  <li key={citation.chunk_id}>
                    <button
                      type="button"
                      onClick={() => setOpen(isOpen ? null : citation.chunk_id)}
                      aria-expanded={isOpen}
                      title="Show this passage in its page"
                      className={`text-left text-[13px] leading-[1.4] tab:text-right ${
                        isOpen
                          ? "underline decoration-accent decoration-2 underline-offset-[3px]"
                          : "text-ink-2 hover:text-ink hover:underline hover:decoration-accent"
                      }`}
                    >
                      {sourceLabel(citation)}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
      {open && (
        <div className="max-w-[684px] pl-[26px]">
          <SourcePanel environmentId={environmentId} chunkId={open} />
        </div>
      )}
    </div>
  );
}

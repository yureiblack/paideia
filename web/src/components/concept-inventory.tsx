"use client";

// The concept inventory, on the Knowledge map tab, set as the index of a
// book (decision record 25): every concept the environment's material
// teaches, as the language model proposed and the backend validated it,
// grouped by first letter, each with its learner state and how many
// relationships it has. A concept's name opens its entry beside the index.
// Documents whose concepts are still coming, or could not be extracted,
// wait behind one notice, with Extract or Try again for each; before there
// are any concepts, that notice is all the page shows of it (statesOnly).

import Link from "next/link";
import { useState } from "react";

import { ConceptMark } from "@/components/concept-progress";
import { Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import { useConcepts, useRequestConcepts } from "@/hooks/use-concepts";
import { usePractice } from "@/hooks/use-practice";
import type { Concept, ExtractionState, PracticeConcept } from "@/lib/types";

export function ConceptInventory({
  environmentId,
  selectedId = null,
  relationships,
  exploreHref,
  statesOnly = false,
}: {
  environmentId: string;
  selectedId?: string | null;
  // Relationships per concept id, once the graph has loaded.
  relationships?: Record<string, number>;
  exploreHref?: (id: string) => string;
  // Only the documents still to extract, for a page with no concepts yet.
  statesOnly?: boolean;
}) {
  const query = useConcepts(environmentId);
  const practice = usePractice(environmentId);
  const [filter, setFilter] = useState("");

  if (query.isPending) return <Loading what="concepts" lines={4} />;
  if (query.isError) {
    return (
      <LoadError
        what="concepts"
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  const { concepts, documents } = query.data;
  const wanted = filter.trim().toLowerCase();
  const shown = wanted
    ? concepts.filter((c) =>
        [c.name, ...c.aliases].some((n) => n.toLowerCase().includes(wanted)),
      )
    : concepts;
  const unsettled = documents.filter((d) => d.status !== "ready");
  const readyCount = documents.length - unsettled.length;
  const states = new Map((practice.data?.concepts ?? []).map((c) => [c.concept_id, c]));

  if (statesOnly) {
    return unsettled.length > 0 ? (
      <ExtractionStates environmentId={environmentId} documents={unsettled} />
    ) : null;
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] leading-[1.4] text-ink-2">
        {concepts.length} {concepts.length === 1 ? "concept" : "concepts"} from {readyCount}{" "}
        {readyCount === 1 ? "document" : "documents"}, proposed by the local model and
        checked before being kept.
      </p>

      {unsettled.length > 0 && (
        <ExtractionStates environmentId={environmentId} documents={unsettled} />
      )}

      {concepts.length === 0 ? (
        <p className="text-[15px] leading-[1.55] text-ink-2">
          No concepts yet. They appear here once materials have been read.
        </p>
      ) : (
        <>
          <label className="flex items-baseline gap-3 border-b-2 border-ink pb-2 focus-within:border-accent">
            <span className="label text-ink-2">Filter</span>
            <input
              type="search"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label="Filter concepts by name"
              className="min-w-0 flex-1 bg-transparent text-[15px] focus:outline-none"
            />
          </label>
          <ul aria-label="Concepts">
            {shown.map((concept, index) => {
              const letter = concept.name.charAt(0).toUpperCase();
              const first = index === 0 || shown[index - 1].name.charAt(0).toUpperCase() !== letter;
              return (
                <li key={concept.id}>
                  {first && (
                    <p aria-hidden className="display pt-3.5 pb-1 text-3xl">
                      {letter}
                    </p>
                  )}
                  <ConceptRow
                    concept={concept}
                    state={states.get(concept.id)}
                    selected={concept.id === selectedId}
                    relationships={relationships && (relationships[concept.id] ?? 0)}
                    href={exploreHref?.(concept.id)}
                  />
                </li>
              );
            })}
          </ul>
          <p className="label flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 text-ink-3">
            <span>○ New</span>
            <span>◐ Learning</span>
            <span>◷ Due</span>
            <span>● Strong</span>
            <span className="flex items-center gap-1.5">
              <Mark /> Needs attention
            </span>
          </p>
        </>
      )}
    </div>
  );
}

function ConceptRow({
  concept,
  state,
  selected,
  relationships,
  href,
}: {
  concept: Concept;
  state: PracticeConcept | undefined;
  selected: boolean;
  relationships?: number;
  href?: string;
}) {
  return (
    <article
      aria-current={selected || undefined}
      className={`flex min-h-11 items-center gap-2.5 tab:min-h-7 ${selected ? "-mx-2 bg-ink px-2 text-paper" : ""}`}
    >
      <ConceptMark concept={state} />
      <h3 className="min-w-0 flex-1 text-[15px] break-words tab:truncate">
        {href ? (
          <Link href={href} className="hover:underline hover:decoration-accent hover:underline-offset-4">
            {concept.name}
          </Link>
        ) : (
          concept.name
        )}
      </h3>
      {relationships !== undefined && (
        <span className={`label ${selected ? "text-paper" : "text-ink-3"}`}>
          {relationships}
          <span className="sr-only"> {relationships === 1 ? "relationship" : "relationships"}</span>
        </span>
      )}
    </article>
  );
}

function stateLabel(d: ExtractionState) {
  if (d.document_status === "uploaded" || d.document_status === "processing") {
    return "Being read";
  }
  if (d.document_status === "failed") return "Could not be read";
  return STATE_LABEL[d.status];
}

const STATE_LABEL: Record<ExtractionState["status"], string> = {
  none: "Not extracted yet",
  pending: "Waiting to be extracted",
  generating: "Extracting concepts…",
  ready: "Ready",
  failed: "Extraction failed",
};

function ExtractionStates({
  environmentId,
  documents,
}: {
  environmentId: string;
  documents: ExtractionState[];
}) {
  const retry = useRequestConcepts(environmentId);
  const failing = documents.some((d) => d.status === "failed" || d.document_status === "failed");
  const [open, setOpen] = useState(failing);
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="label flex w-fit items-center gap-2 text-left"
      >
        <Mark />
        {documents.length} {documents.length === 1 ? "document" : "documents"} still to extract{" "}
        <OpenSign open={open} />
      </button>
      {open && (
        <ul className="flex flex-col" aria-label="Documents still to extract">
          {documents.map((d) => (
            <li key={d.document_id} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-rule py-2">
              <span className="min-w-0 flex-1 truncate text-[15px]">{d.filename}</span>
              <span className="label text-ink-2">{stateLabel(d)}</span>
              {d.document_status === "ready" &&
                (d.status === "failed" || d.status === "none") && (
                  <button
                    type="button"
                    onClick={() => retry.mutate(d.document_id)}
                    disabled={retry.isPending}
                    className={button.link}
                  >
                    {d.status === "failed" ? "Try again" : "Extract"}
                  </button>
                )}
              {d.error && (
                <span className="basis-full text-[13px] leading-[1.4] text-ink-2">{d.error}</span>
              )}
            </li>
          ))}
          {retry.error && (
            <li role="alert" className="flex items-center gap-2.5 pt-2 text-[13px] leading-[1.4]">
              <Mark />
              {retry.error.message}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

"use client";

// The Knowledge map tab (decision record 25): at the top, where the graph
// stands. Below, the concepts as the index of a book, beside the entry for
// the concept picked from it: its definition and the passages explaining
// it, what it builds on and what builds on it, what it is part of, its parts
// and what it is related to, each a link to explore further and each direct
// relationship with references that open the passages showing it. The
// picked concept is in the address (?concept=), so the browser's back button
// retraces the way. On a phone the index and the entry are two views.

import Link from "next/link";
import { useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { ConceptInventory } from "@/components/concept-inventory";
import { ConceptProgress } from "@/components/concept-progress";
import { STATE_BADGE } from "@/components/environment-summary";
import { MathsText } from "@/components/maths-text";
import { Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign } from "@/components/ui";
import { useConcepts } from "@/hooks/use-concepts";
import {
  graphVersion,
  useGraph,
  useNeighbourhood,
  useRequestGraph,
} from "@/hooks/use-graph";
import type { GraphState, Neighbour } from "@/lib/types";
import { InWords, inWords } from "@/lib/words";

export function KnowledgeMap({
  environmentId,
  conceptId,
}: {
  environmentId: string;
  conceptId: string | null;
}) {
  const graph = useGraph(environmentId);
  const exploreHref = (id: string | null) =>
    `/environments/${encodeURIComponent(environmentId)}/knowledge-map${
      id ? `?concept=${encodeURIComponent(id)}` : ""
    }`;
  const relationships: Record<string, number> = {};
  for (const edge of graph.data?.edges ?? []) {
    relationships[edge.source] = (relationships[edge.source] ?? 0) + 1;
    relationships[edge.target] = (relationships[edge.target] ?? 0) + 1;
  }

  return (
    <div className="flex flex-col gap-8">
      <GraphStatus environmentId={environmentId} graph={graph} />
      <div className="grid border-t border-ink tab:grid-cols-[240px_minmax(0,1fr)] desk:grid-cols-[280px_minmax(0,1fr)]">
        <div className={`pt-4 tab:border-r tab:border-rule tab:pr-7 ${conceptId ? "max-tab:hidden" : ""}`}>
          <ConceptInventory
            environmentId={environmentId}
            selectedId={conceptId}
            relationships={graph.data ? relationships : undefined}
            exploreHref={exploreHref}
          />
        </div>
        <div className={`min-w-0 pt-4 tab:pl-10 ${conceptId ? "" : "max-tab:hidden"}`}>
          {conceptId ? (
            <ConceptExplorer
              key={conceptId}
              environmentId={environmentId}
              conceptId={conceptId}
              version={graphVersion(graph.data)}
              exploreHref={exploreHref}
            />
          ) : (
            <p className="display max-w-md pt-2 text-[22px] leading-[1.2] text-ink-3 italic">
              Pick a concept from the index to see what it builds on and what builds on it.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

const KIND_LABEL = {
  PREREQUISITE_OF: ["←", "builds on", "build on"],
  PART_OF: ["⊂", "part of", "part of"],
  RELATED_TO: ["~", "related", "related"],
} as const;

function GraphStatus({
  environmentId,
  graph,
}: {
  environmentId: string;
  graph: ReturnType<typeof useGraph>;
}) {
  const update = useRequestGraph(environmentId);
  const kicker = (
    <p className="label max-tab:sr-only">
      <span aria-hidden>04 / </span>Knowledge map
    </p>
  );

  if (graph.isPending) {
    return (
      <div className="flex flex-col gap-4">
        {kicker}
        <Loading what="the knowledge graph" lines={3} />
      </div>
    );
  }
  if (graph.isError) {
    return (
      <div className="flex flex-col gap-4">
        {kicker}
        <LoadError
          what="the knowledge graph"
          error={graph.error}
          onRetry={() => void graph.refetch()}
          retrying={graph.isFetching}
        />
      </div>
    );
  }
  const { state, edges, nodes } = graph.data;
  const badge = STATE_BADGE[state];
  const kinds = (Object.keys(KIND_LABEL) as (keyof typeof KIND_LABEL)[])
    .map((kind) => ({ kind, count: edges.filter((e) => e.relationship_type === kind).length }))
    .filter(({ count }) => count > 0);
  const connected = new Set(edges.flatMap((e) => [e.source, e.target])).size;
  const headline =
    nodes.length === 0
      ? "No concepts yet."
      : `${InWords(nodes.length)} ${nodes.length === 1 ? "concept" : "concepts"}, ${
          edges.length ? `${inWords(edges.length)} ${edges.length === 1 ? "link" : "links"} between them.` : "no links yet."
        }`;

  return (
    <section aria-labelledby="graph-heading" className="flex flex-col gap-4 desk:flex-row desk:items-end desk:gap-10">
      <h2 id="graph-heading" className="sr-only">
        Knowledge graph
      </h2>
      <div className="flex min-w-0 flex-1 flex-col gap-3.5">
        {kicker}
        <p className="display text-[44px] leading-[0.92] tracking-[-0.03em] text-balance tab:text-[60px] desk:text-[64px]">
          {headline}
        </p>
      </div>
      <div className="flex flex-col gap-2 desk:w-60 desk:shrink-0 desk:pb-1.5">
        <p className={`label text-[10px] ${badge.style}`}>{badge.label}</p>
        {edges.length > 0 && (
          <p className="label text-[10px] text-ink-2">
            {edges.length} {edges.length === 1 ? "relationship" : "relationships"} between{" "}
            {connected} of {nodes.length} concepts
          </p>
        )}
        {kinds.length > 0 && (
          <ul className="flex flex-col gap-0.5" aria-label="Relationships by kind">
            {kinds.map(({ kind, count }) => (
              <li key={kind} className="label text-[10px]">
                <span aria-hidden>{KIND_LABEL[kind][0]} </span>
                {count} {KIND_LABEL[kind][count === 1 ? 1 : 2]}
              </li>
            ))}
          </ul>
        )}
        <GraphNote graph={graph.data} />
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
  );
}

// Where the graph stands, in a sentence. When it is up to date that is only
// how it was made, so it waits behind a toggle; anything else shows.
function GraphNote({ graph }: { graph: GraphState }) {
  const [open, setOpen] = useState(false);
  const { state, waiting_for, error, edges } = graph;
  const kept =
    edges.length > 0 ? " The relationships shown are from the last build." : "";
  const note = {
    up_to_date:
      edges.length > 0
        ? "Found by the local model in passages that connect two concepts; each relationship cites those passages. Pick a concept below to see what it builds on and what builds on it."
        : "The local model found no relationships in the passages that connect concepts.",
    updating:
      "Finding relationships between concepts… The local model is asked only about pairs of concepts it has not seen before." +
      kept,
    waiting: `${waiting_for} ${
      waiting_for === 1 ? "document is" : "documents are"
    } still being read or having their concepts extracted; the graph is updated once they are done.${kept}`,
    stale: `The concepts have changed since the graph was built.${kept}`,
    failed: `The graph could not be updated: ${error}${kept}`,
    none: "No relationships yet. Once materials have been read, relationships between their concepts appear here, found in the passages that connect them.",
  }[state];
  const quiet = state === "up_to_date" && edges.length > 0;
  return (
    <div className="flex flex-col gap-2">
      {quiet && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="label w-fit text-[10px] text-ink-3 hover:text-ink"
        >
          How relationships are found <OpenSign open={open} />
        </button>
      )}
      {(!quiet || open) && (
        <p
          role={state === "failed" ? "alert" : "status"}
          className={`flex gap-2 text-sm leading-snug ${state === "failed" ? "text-ink" : "text-ink-2"}`}
        >
          {state === "failed" && (
            <span className="pt-1.5">
              <Mark />
            </span>
          )}
          {note}
        </p>
      )}
    </div>
  );
}

const RELATION_ROWS = [
  { key: "prerequisites", sign: "←", title: "Builds on", hint: "Understand these first. Further steps back are listed after the direct ones." },
  { key: "dependents", sign: "→", title: "Leads to", hint: "These build on it." },
  { key: "part_of", sign: "⊂", title: "Part of", hint: "It is a part, step or kind of these." },
  { key: "parts", sign: "⊃", title: "Parts", hint: "Parts, steps or kinds of it." },
  { key: "related", sign: "~", title: "Related", hint: "Closely related to it." },
] as const;

function ConceptExplorer({
  environmentId,
  conceptId,
  version,
  exploreHref,
}: {
  environmentId: string;
  conceptId: string;
  version: string;
  exploreHref: (id: string | null) => string;
}) {
  const query = useNeighbourhood(conceptId, version);
  const concepts = useConcepts(environmentId);
  const close = (
    <Link href={exploreHref(null)} className="label text-[10px] text-ink-3 hover:text-ink">
      <span aria-hidden className="tab:hidden">← </span>
      <span className="tab:hidden">Index</span>
      <span className="hidden tab:inline">Close</span>
    </Link>
  );

  if (query.isPending) return <Loading what="the concept" lines={3} />;
  if (query.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        {query.error.message === "Concept not found" ? (
          <p role="alert" className="label flex items-center gap-2">
            <Mark />
            This concept is no longer in the material.
          </p>
        ) : (
          <LoadError
            what="the concept"
            error={query.error}
            onRetry={() => void query.refetch()}
            retrying={query.isFetching}
          />
        )}
        {close}
      </div>
    );
  }
  const near = query.data;
  const concept = concepts.data?.concepts.find((c) => c.id === near.concept.id);
  const nothing = RELATION_ROWS.every(({ key }) => near[key].length === 0);

  return (
    <section aria-labelledby="explorer-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <ConceptProgress environmentId={environmentId} conceptId={near.concept.id} />
          {close}
        </div>
        <h2
          id="explorer-heading"
          className="display text-5xl leading-[0.95] tracking-[-0.03em] tab:text-[56px] desk:text-[64px]"
        >
          {near.concept.name}
        </h2>
        {near.aliases.length > 0 && (
          <p className="label text-[10px] text-ink-3">Also: {near.aliases.join(", ")}</p>
        )}
        <p className="display max-w-3xl text-[22px] leading-[1.25] text-ink-2 tab:text-[26px]">
          <MathsText text={near.definition} />
        </p>
        {concept && concept.evidence.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="label text-[10px] text-ink-3">
              In {concept.documents.map((d) => d.filename).join(", ")}
            </p>
            <CitationChips environmentId={environmentId} citations={concept.evidence} showFilename />
          </div>
        )}
      </div>

      {nothing ? (
        <p className="display border-t border-ink pt-4 text-lg text-ink-3 italic">
          No relationships found for this concept yet.
        </p>
      ) : (
        <div className="flex flex-col border-t border-ink">
          {RELATION_ROWS.map(({ key, sign, title, hint }) => (
            <NeighbourGroup
              key={key}
              sign={sign}
              title={title}
              hint={hint}
              items={near[key]}
              environmentId={environmentId}
              exploreHref={exploreHref}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function NeighbourGroup({
  sign,
  title,
  hint,
  items,
  environmentId,
  exploreHref,
}: {
  sign: string;
  title: string;
  hint: string;
  items: Neighbour[];
  environmentId: string;
  exploreHref: (id: string | null) => string;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-rule py-3.5 tab:flex-row tab:gap-5">
      <div className="flex flex-col gap-1 tab:w-40 tab:shrink-0">
        <h3 className={`label text-[10px] ${items.length ? "" : "text-ink-3"}`}>
          <span aria-hidden>{sign} </span>
          {title}
        </h3>
        <p className="text-xs leading-snug text-ink-3">{hint}</p>
      </div>
      {items.length === 0 ? (
        <p className="display text-[17px] text-ink-3 italic">Nothing found in the passages.</p>
      ) : (
        <ul className="flex min-w-0 flex-col gap-3" aria-label={title}>
          {items.map((item) => (
            <li key={item.id} className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2.5">
                <Link
                  href={exploreHref(item.id)}
                  className="display text-[22px] leading-[1.15] hover:underline hover:decoration-accent hover:underline-offset-4"
                >
                  {item.name}
                </Link>
                {item.depth > 1 && (
                  <span className="label text-[10px] text-ink-3">{item.depth} steps away</span>
                )}
              </div>
              {item.evidence.length > 0 && (
                <CitationChips environmentId={environmentId} citations={item.evidence} showFilename />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

"use client";

// The Knowledge map tab (decision record 28): at the top, where the graph
// stands, and the first time it is opened, a note on where its concepts
// come from. Below, the concepts as the index of a book, beside the entry
// for the concept picked from it, one concept at a time: its definition,
// what it builds on and what builds on it, what it is part of, its parts
// and what it is related to, each a link to explore further. Small numbers
// after the definition and after each related concept point to the
// passages showing them, listed as footnotes under the entry; a footnote
// opens its passage in its page. The picked concept is in the address
// (?concept=), so the browser's back button retraces the way. On a phone
// the index and the entry are two views.

import Link from "next/link";
import { useState } from "react";

import { sourceLabel } from "@/components/cited-points";
import { ConceptInventory } from "@/components/concept-inventory";
import { ConceptProgress } from "@/components/concept-progress";
import { STATE_BADGE } from "@/components/environment-summary";
import { sectionNumber } from "@/components/environment-tabs";
import { MathsText } from "@/components/maths-text";
import { Note } from "@/components/note";
import { Empty, Loading, LoadError } from "@/components/query-states";
import { SourcePanel } from "@/components/source-panel";
import { button, Mark, OpenSign } from "@/components/ui";
import { useConcepts } from "@/hooks/use-concepts";
import {
  graphVersion,
  useGraph,
  useNeighbourhood,
  useRequestGraph,
} from "@/hooks/use-graph";
import type { Citation, GraphState, Neighbour } from "@/lib/types";
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
  const empty = graph.data?.nodes.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <GraphStatus environmentId={environmentId} graph={graph} />
      {empty ? (
        // Nothing to index yet; documents whose concepts could not be
        // extracted still show, with Extract or Try again.
        <div className="max-w-[640px]">
          <ConceptInventory environmentId={environmentId} statesOnly />
        </div>
      ) : (
        <>
          {graph.data && (
            <Note
              id="knowledge-map"
              title="The knowledge map — where it comes from"
              guideStep={3}
            >
              Every concept here was found in your passages, and every link was read in a
              passage that connects two concepts. The small numbers point to those pages.
            </Note>
          )}
          <div className="grid border-t border-ink tab:grid-cols-[240px_minmax(0,1fr)] desk:grid-cols-[260px_minmax(0,1fr)]">
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
                <p className="max-w-md pt-2 text-[15px] leading-[1.55] text-ink-2">
                  Pick a concept from the index to see what it builds on and what builds on it.
                </p>
              )}
            </div>
          </div>
        </>
      )}
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
      <span aria-hidden>{sectionNumber("Knowledge map")} / </span>Knowledge map
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

  if (nodes.length === 0) {
    return (
      <section aria-labelledby="graph-heading" className="flex flex-col gap-6">
        <h2 id="graph-heading" className="sr-only">
          Knowledge graph
        </h2>
        {kicker}
        <Empty
          title="No concepts yet."
          action={
            <div className="flex flex-col items-start gap-3">
              <Link
                href={`/environments/${encodeURIComponent(environmentId)}/materials`}
                className={button.outline}
              >
                Upload PDF or picture <span aria-hidden>→</span>
              </Link>
              <p className="text-[13px] leading-[1.4] text-ink-2">
                Already uploaded? The rail shows how far the reading has got.
              </p>
            </div>
          }
        >
          Concepts are found in the passages once a document has been read. How they build
          on one another makes this map.
        </Empty>
        {state !== "none" && state !== "up_to_date" && (
          <div className="flex max-w-[640px] flex-col gap-2">
            <GraphNote graph={graph.data} />
            {updateAction}
          </div>
        )}
      </section>
    );
  }

  const kinds = (Object.keys(KIND_LABEL) as (keyof typeof KIND_LABEL)[])
    .map((kind) => ({ kind, count: edges.filter((e) => e.relationship_type === kind).length }))
    .filter(({ count }) => count > 0);
  const connected = new Set(edges.flatMap((e) => [e.source, e.target])).size;
  const headline = (
    <>
      {InWords(nodes.length)} {nodes.length === 1 ? "concept" : "concepts"},
      <br />
      {edges.length
        ? `${inWords(edges.length)} ${edges.length === 1 ? "link" : "links"} between them.`
        : "no links yet."}
    </>
  );

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
      <div className="flex flex-col gap-2.5 desk:w-60 desk:shrink-0 desk:pb-1.5">
        {state !== "up_to_date" && <p className={`label ${badge.style}`}>{badge.label}</p>}
        {kinds.length > 0 && (
          <ul className="flex flex-col gap-1" aria-label="Relationships by kind">
            {kinds.map(({ kind, count }) => (
              <li key={kind} className="label">
                <span aria-hidden className="inline-block w-5">{KIND_LABEL[kind][0]}</span>
                {count} {KIND_LABEL[kind][count === 1 ? 1 : 2]}
              </li>
            ))}
          </ul>
        )}
        {edges.length > 0 && (
          <p className="text-[13px] leading-[1.4] text-ink-2">
            {edges.length} {edges.length === 1 ? "relationship" : "relationships"} between{" "}
            {connected} of {nodes.length} concepts
          </p>
        )}
        <GraphNote graph={graph.data} />
        {updateAction}
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
          className="label w-fit text-left text-ink-2 hover:text-ink"
        >
          How relationships are found <OpenSign open={open} />
        </button>
      )}
      {(!quiet || open) && (
        <p
          role={state === "failed" ? "alert" : "status"}
          className={`flex gap-2 text-[13px] leading-[1.5] ${state === "failed" ? "text-ink" : "text-ink-2"}`}
        >
          {state === "failed" && (
            <span className="pt-1.5">
              <Mark />
            </span>
          )}
          <span>{note}</span>
        </p>
      )}
    </div>
  );
}

const RELATION_ROWS = [
  { key: "prerequisites", sign: "←", title: "Builds on" },
  { key: "dependents", sign: "→", title: "Leads to" },
  { key: "part_of", sign: "⊂", title: "Part of" },
  { key: "parts", sign: "⊃", title: "Parts" },
  { key: "related", sign: "~", title: "Related" },
] as const;

// The entry's footnotes: every passage it cites, numbered in the order
// first cited, the definition's first.
type Footnotes = { list: { number: number; citation: Citation }[]; numbers: Map<string, number> };

function footnotes(groups: Citation[][]): Footnotes {
  const numbers = new Map<string, number>();
  const list: Footnotes["list"] = [];
  for (const citation of groups.flat()) {
    if (numbers.has(citation.chunk_id)) continue;
    numbers.set(citation.chunk_id, list.length + 1);
    list.push({ number: list.length + 1, citation });
  }
  return { list, numbers };
}

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
  // The footnote whose passage is open, by chunk id.
  const [open, setOpen] = useState<string | null>(null);
  const close = (
    <Link href={exploreHref(null)} className="label text-ink-2 hover:text-ink">
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
          <p role="alert" className="flex items-center gap-2.5 text-[15px]">
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
  const notes = footnotes([
    concept?.evidence ?? [],
    ...RELATION_ROWS.flatMap(({ key }) => near[key].map((item) => item.evidence)),
  ]);
  const toggle = (chunkId: string) => setOpen(open === chunkId ? null : chunkId);

  return (
    <section aria-labelledby="explorer-heading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="flex min-h-6 items-start justify-between gap-3">
          <ConceptProgress environmentId={environmentId} conceptId={near.concept.id} />
          {close}
        </div>
        <h2
          id="explorer-heading"
          className="display text-[44px] leading-[0.95] tracking-[-0.03em] tab:text-[56px]"
        >
          {near.concept.name}
        </h2>
        {near.aliases.length > 0 && (
          <p className="text-[13px] leading-[1.4] text-ink-2">Also called {near.aliases.join(", ")}</p>
        )}
        <p className="max-w-[640px] text-[19px] leading-[1.6]">
          <MathsText text={near.definition} />
          <NoteNumbers citations={concept?.evidence ?? []} notes={notes} open={open} onToggle={toggle} />
        </p>
      </div>

      {nothing ? (
        <p className="border-t border-ink pt-4 text-[15px] leading-[1.55] text-ink-2">
          No relationships found for this concept yet.
        </p>
      ) : (
        <div className="flex flex-col border-t border-ink">
          {RELATION_ROWS.map(({ key, sign, title }) => (
            <NeighbourGroup
              key={key}
              sign={sign}
              title={title}
              items={near[key]}
              notes={notes}
              open={open}
              onToggle={toggle}
              exploreHref={exploreHref}
            />
          ))}
        </div>
      )}

      {notes.list.length > 0 && (
        <div className="flex flex-col gap-3">
          <ol aria-label="Sources" className="flex flex-col gap-0.5">
            {notes.list.map(({ number, citation }) => {
              const isOpen = open === citation.chunk_id;
              return (
                <li key={citation.chunk_id} className="flex items-baseline gap-1 text-[13px] leading-[1.5]">
                  <sup aria-hidden className="w-3.5 shrink-0 text-[11px] text-ink-2">
                    {number}
                  </sup>
                  <button
                    type="button"
                    onClick={() => toggle(citation.chunk_id)}
                    aria-expanded={isOpen}
                    className={`text-left ${
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
          </ol>
          {open && <SourcePanel environmentId={environmentId} chunkId={open} />}
        </div>
      )}
    </section>
  );
}

// The small numbers after a definition or a related concept: each opens
// its footnote's passage under the entry.
function NoteNumbers({
  citations,
  notes,
  open,
  onToggle,
}: {
  citations: Citation[];
  notes: Footnotes;
  open: string | null;
  onToggle: (chunkId: string) => void;
}) {
  const shown = citations.filter(
    (c, index) => citations.findIndex((d) => d.chunk_id === c.chunk_id) === index,
  );
  if (shown.length === 0) return null;
  return (
    <sup className="ml-0.5 inline-flex gap-0.5 font-sans text-[11px] leading-none tracking-normal">
      {shown.map((citation) => {
        const number = notes.numbers.get(citation.chunk_id) ?? 0;
        const isOpen = open === citation.chunk_id;
        return (
          <button
            key={citation.chunk_id}
            type="button"
            onClick={() => onToggle(citation.chunk_id)}
            aria-expanded={isOpen}
            aria-label={`Note ${number}, ${sourceLabel(citation)}`}
            title={sourceLabel(citation)}
            className={`min-w-3 px-0.5 ${isOpen ? "bg-ink text-paper" : "text-ink-2 hover:text-ink hover:underline hover:decoration-accent"}`}
          >
            {number}
          </button>
        );
      })}
    </sup>
  );
}

function NeighbourGroup({
  sign,
  title,
  items,
  notes,
  open,
  onToggle,
  exploreHref,
}: {
  sign: string;
  title: string;
  items: Neighbour[];
  notes: Footnotes;
  open: string | null;
  onToggle: (chunkId: string) => void;
  exploreHref: (id: string | null) => string;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-rule py-3.5 tab:flex-row tab:items-baseline tab:gap-5">
      <h3 className={`label tab:w-36 tab:shrink-0 ${items.length ? "" : "text-ink-3"}`}>
        <span aria-hidden className="inline-block w-6">{sign}</span>
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="display text-[17px] text-ink-3 italic">Nothing found in the passages.</p>
      ) : (
        <ul className="flex min-w-0 flex-wrap gap-x-1 gap-y-1" aria-label={title}>
          {items.map((item, n) => (
            <li key={item.id} className="display text-[22px] leading-[1.2]">
              <Link
                href={exploreHref(item.id)}
                className="hover:underline hover:decoration-accent hover:underline-offset-4"
              >
                {item.name}
              </Link>
              <NoteNumbers citations={item.evidence} notes={notes} open={open} onToggle={onToggle} />
              {item.depth > 1 && (
                <span className="pl-1.5 font-sans text-[13px] tracking-normal text-ink-3">
                  {item.depth} steps away
                </span>
              )}
              {n < items.length - 1 && <span aria-hidden>,</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

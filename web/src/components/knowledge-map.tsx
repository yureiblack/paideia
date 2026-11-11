"use client";

// The Knowledge map tab: the knowledge graph and the concept inventory.
// At the top, where the graph stands. Then, for the concept picked from the
// list, an explorer: what it builds on and what builds on it, what it is part
// of, its parts and what it is related to, each a link to explore further and
// each direct relationship with chips that open the passages showing it. The
// picked concept is in the address (?concept=), so the browser's back button
// retraces the way. Plain lists, no drawing: it reads the same on a phone.

import Link from "next/link";

import { CitationChips } from "@/components/cited-points";
import { ConceptInventory } from "@/components/concept-inventory";
import { ConceptProgress } from "@/components/concept-progress";
import { STATE_BADGE } from "@/components/environment-summary";
import {
  graphVersion,
  useGraph,
  useNeighbourhood,
  useRequestGraph,
} from "@/hooks/use-graph";
import type { GraphState, Neighbour } from "@/lib/types";

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
      {conceptId && (
        <ConceptExplorer
          key={conceptId}
          environmentId={environmentId}
          conceptId={conceptId}
          version={graphVersion(graph.data)}
          exploreHref={exploreHref}
        />
      )}
      <ConceptInventory
        environmentId={environmentId}
        selectedId={conceptId}
        relationships={graph.data ? relationships : undefined}
        exploreHref={exploreHref}
      />
    </div>
  );
}

const KIND_LABEL = {
  PREREQUISITE_OF: ["prerequisite", "prerequisites"],
  PART_OF: ["part-of", "part-of"],
  RELATED_TO: ["related", "related"],
} as const;

function GraphStatus({
  environmentId,
  graph,
}: {
  environmentId: string;
  graph: ReturnType<typeof useGraph>;
}) {
  const update = useRequestGraph(environmentId);

  if (graph.isPending) {
    return <p className="text-zinc-500">Loading the knowledge graph…</p>;
  }
  if (graph.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not load the knowledge graph: {graph.error.message}
      </p>
    );
  }
  const { state, edges, nodes } = graph.data;
  const badge = STATE_BADGE[state];
  const kinds = (Object.keys(KIND_LABEL) as (keyof typeof KIND_LABEL)[])
    .map((kind) => {
      const count = edges.filter((e) => e.relationship_type === kind).length;
      return count ? `${count} ${KIND_LABEL[kind][count === 1 ? 0 : 1]}` : null;
    })
    .filter(Boolean);
  const connected = new Set(edges.flatMap((e) => [e.source, e.target])).size;

  return (
    <section aria-labelledby="graph-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <h2 id="graph-heading" className="font-medium">
          Knowledge graph
        </h2>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${badge.style}`}>
          {badge.label}
        </span>
        {edges.length > 0 && (
          <span className="text-zinc-600 dark:text-zinc-400">
            {edges.length} {edges.length === 1 ? "relationship" : "relationships"}{" "}
            between {connected} of {nodes.length} concepts
            {kinds.length > 0 && ` · ${kinds.join(" · ")}`}
          </span>
        )}
      </div>
      <GraphNote graph={graph.data} />
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
  );
}

function GraphNote({ graph }: { graph: GraphState }) {
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
  return (
    <p
      role={state === "failed" ? "alert" : "status"}
      className={`text-sm ${state === "failed" ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400"}`}
    >
      {note}
    </p>
  );
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
  const close = (
    <Link
      href={exploreHref(null)}
      className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium dark:border-zinc-700"
    >
      Close
    </Link>
  );

  if (query.isPending) {
    return <p className="text-zinc-500">Loading the concept…</p>;
  }
  if (query.isError) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {query.error.message === "Concept not found"
            ? "This concept is no longer in the material."
            : `Could not load the concept: ${query.error.message}`}
        </p>
        {close}
      </div>
    );
  }
  const near = query.data;
  const others = [
    { title: "Part of", hint: "It is a part, step or kind of these.", items: near.part_of },
    { title: "Parts", hint: "Parts, steps or kinds of it.", items: near.parts },
    { title: "Related", hint: "Closely related to it.", items: near.related },
  ].filter((group) => group.items.length > 0);
  const nothing =
    near.prerequisites.length + near.dependents.length + others.length === 0;

  return (
    <section
      aria-labelledby="explorer-heading"
      className="flex flex-col gap-5 rounded-xl border border-zinc-900 p-4 dark:border-zinc-100"
    >
      <div className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <h2 id="explorer-heading" className="min-w-0 text-lg font-semibold">
            {near.concept.name}
          </h2>
          {close}
        </div>
        {near.aliases.length > 0 && (
          <p className="text-xs text-zinc-500">Also: {near.aliases.join(", ")}</p>
        )}
        <p className="text-sm">{near.definition}</p>
        <ConceptProgress environmentId={environmentId} conceptId={near.concept.id} />
      </div>

      {nothing ? (
        <p className="text-sm text-zinc-500">
          No relationships found for this concept yet.
        </p>
      ) : (
        <>
          <div className="grid gap-5 md:grid-cols-2">
            <NeighbourGroup
              title="Builds on"
              hint="Understand these first. Further steps back are listed after the direct ones."
              items={near.prerequisites}
              environmentId={environmentId}
              exploreHref={exploreHref}
            />
            <NeighbourGroup
              title="Leads to"
              hint="These build on it."
              items={near.dependents}
              environmentId={environmentId}
              exploreHref={exploreHref}
            />
          </div>
          {others.length > 0 && (
            <div className="grid gap-5 md:grid-cols-3">
              {others.map((group) => (
                <NeighbourGroup
                  key={group.title}
                  {...group}
                  environmentId={environmentId}
                  exploreHref={exploreHref}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function NeighbourGroup({
  title,
  hint,
  items,
  environmentId,
  exploreHref,
}: {
  title: string;
  hint: string;
  items: Neighbour[];
  environmentId: string;
  exploreHref: (id: string | null) => string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div>
        <h3 className="text-sm font-medium">{title}</h3>
        <p className="text-xs text-zinc-500">{hint}</p>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-zinc-500">None found.</p>
      ) : (
        <ul className="flex flex-col gap-3" aria-label={title}>
          {items.map((item) => (
            <li key={item.id} className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <Link
                  href={exploreHref(item.id)}
                  className="font-medium underline decoration-zinc-400 underline-offset-4 hover:decoration-current dark:decoration-zinc-500"
                >
                  {item.name}
                </Link>
                {item.depth > 1 && (
                  <span className="text-xs text-zinc-500">
                    {item.depth} steps away
                  </span>
                )}
              </div>
              {item.evidence.length > 0 && (
                <CitationChips
                  environmentId={environmentId}
                  citations={item.evidence}
                  showFilename
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

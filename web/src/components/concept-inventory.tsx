"use client";

// The concept inventory, on the Knowledge map tab: every concept the
// environment's material teaches, as the language model proposed and the
// backend validated it. Each shows its definition, other names, the
// documents it appears in, and chips that open the passages explaining it;
// its name opens it in the explorer above, with how many relationships it
// has. Documents whose concepts are still coming, or could not be
// extracted, are listed above, with Try again for failures.

import Link from "next/link";
import { useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { useConcepts, useRequestConcepts } from "@/hooks/use-concepts";
import type { Concept, ExtractionState } from "@/lib/types";

export function ConceptInventory({
  environmentId,
  selectedId = null,
  relationships,
  exploreHref,
}: {
  environmentId: string;
  selectedId?: string | null;
  // Relationships per concept id, once the graph has loaded.
  relationships?: Record<string, number>;
  exploreHref?: (id: string) => string;
}) {
  const query = useConcepts(environmentId);
  const [filter, setFilter] = useState("");

  if (query.isPending) {
    return <p className="text-zinc-500">Loading concepts…</p>;
  }
  if (query.isError) {
    return (
      <p role="alert" className="text-red-600 dark:text-red-400">
        Could not load concepts: {query.error.message}
      </p>
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

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        {concepts.length} {concepts.length === 1 ? "concept" : "concepts"} from{" "}
        {readyCount} {readyCount === 1 ? "document" : "documents"}, proposed by
        the local model and checked before being kept.
      </p>

      {unsettled.length > 0 && (
        <ExtractionStates environmentId={environmentId} documents={unsettled} />
      )}

      {concepts.length === 0 ? (
        <p className="text-zinc-500">
          No concepts yet. They appear here once materials have been read.
        </p>
      ) : (
        <>
          <input
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter concepts"
            aria-label="Filter concepts by name"
            className="w-full max-w-sm rounded-lg border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
          />
          <ul className="flex flex-col gap-3" aria-label="Concepts">
            {shown.map((concept) => (
              <li key={concept.id}>
                <ConceptCard
                  environmentId={environmentId}
                  concept={concept}
                  selected={concept.id === selectedId}
                  relationships={relationships && (relationships[concept.id] ?? 0)}
                  href={exploreHref?.(concept.id)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ConceptCard({
  environmentId,
  concept,
  selected,
  relationships,
  href,
}: {
  environmentId: string;
  concept: Concept;
  selected: boolean;
  relationships?: number;
  href?: string;
}) {
  return (
    <article
      aria-current={selected || undefined}
      className={`flex flex-col gap-2 rounded-xl border p-4 ${
        selected
          ? "border-zinc-900 dark:border-zinc-100"
          : "border-zinc-200 dark:border-zinc-800"
      }`}
    >
      <div className="flex flex-col gap-0.5">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <h3 className="font-medium">
            {href ? (
              <Link
                href={href}
                className="underline decoration-zinc-400 underline-offset-4 hover:decoration-current dark:decoration-zinc-500"
              >
                {concept.name}
              </Link>
            ) : (
              concept.name
            )}
          </h3>
          {relationships !== undefined && (
            <span className="text-xs text-zinc-500">
              {relationships === 0
                ? "No relationships"
                : `${relationships} ${relationships === 1 ? "relationship" : "relationships"}`}
            </span>
          )}
        </div>
        {concept.aliases.length > 0 && (
          <p className="text-xs text-zinc-500">
            Also: {concept.aliases.join(", ")}
          </p>
        )}
      </div>
      <p className="text-sm">{concept.definition}</p>
      <p className="text-xs text-zinc-500">
        In {concept.documents.map((d) => d.filename).join(", ")}
      </p>
      <CitationChips
        environmentId={environmentId}
        citations={concept.evidence}
        showFilename
      />
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
  return (
    <ul className="flex flex-col gap-2 text-sm" aria-label="Documents still to extract">
      {documents.map((d) => (
        <li key={d.document_id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium">{d.filename}</span>
          <span className="text-zinc-500">
            · {stateLabel(d)}
            {d.error && `: ${d.error}`}
          </span>
          {d.document_status === "ready" &&
            (d.status === "failed" || d.status === "none") && (
            <button
              type="button"
              onClick={() => retry.mutate(d.document_id)}
              disabled={retry.isPending}
              className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium disabled:opacity-50 dark:border-zinc-700"
            >
              {d.status === "failed" ? "Try again" : "Extract"}
            </button>
          )}
        </li>
      ))}
      {retry.error && (
        <li role="alert" className="text-red-600 dark:text-red-400">
          {retry.error.message}
        </li>
      )}
    </ul>
  );
}

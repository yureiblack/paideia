"use client";

// The Knowledge map tab, for now the concept inventory: every concept the
// environment's material teaches, as the language model proposed and the
// backend validated it. Each shows its definition, other names, the
// documents it appears in, and chips that open the passages explaining it.
// Documents whose concepts are still coming, or could not be extracted, are
// listed above, with Try again for failures.

import { useState } from "react";

import { CitationChips } from "@/components/cited-points";
import { useConcepts, useRequestConcepts } from "@/hooks/use-concepts";
import type { Concept, ExtractionState } from "@/lib/types";

export function ConceptInventory({ environmentId }: { environmentId: string }) {
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
                <ConceptCard environmentId={environmentId} concept={concept} />
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
}: {
  environmentId: string;
  concept: Concept;
}) {
  return (
    <article className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-col gap-0.5">
        <h3 className="font-medium">{concept.name}</h3>
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

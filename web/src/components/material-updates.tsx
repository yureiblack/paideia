"use client";

// What each change to the material did, on the Materials tab. The latest
// update is one line; while it runs its steps show live (reading, its
// summary, the environment summary, concepts, the knowledge map, the
// roadmap), each saying what it did. Once done, "What changed" opens the
// steps and the report: new and removed concepts, new and removed
// relationships, what was updated and what was left as it was. Earlier
// updates open the same way.

import { useState, type ReactNode } from "react";

import { LoadError } from "@/components/query-states";
import { Mark, OpenSign } from "@/components/ui";
import { useUpdates } from "@/hooks/use-updates";
import { formatDateTime } from "@/lib/format";
import type { MaterialUpdate, RelationshipNote, UpdateStep } from "@/lib/types";

const KIND: Record<MaterialUpdate["kind"], string> = {
  added: "Added",
  new_version: "New version of",
  reprocessed: "Read again:",
  deleted: "Removed",
};

const MARK: Record<UpdateStep["state"], string> = {
  waiting: "○",
  running: "◐",
  done: "✓",
  failed: "✕",
  skipped: "–",
};

const RELATION: Record<RelationshipNote["type"], string> = {
  PREREQUISITE_OF: "comes before",
  PART_OF: "is part of",
  RELATED_TO: "relates to",
};

export function MaterialUpdates({ environmentId }: { environmentId: string }) {
  const query = useUpdates(environmentId);
  const [showEarlier, setShowEarlier] = useState(false);
  if (query.isError) {
    return (
      <LoadError
        what="the history of changes"
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  if (!query.data || query.data.length === 0) return null;
  const [latest, ...earlier] = query.data;

  return (
    <section aria-labelledby="updates-heading" className="flex flex-col border-y border-ink">
      <h2 id="updates-heading" className="sr-only">
        Updates
      </h2>
      <UpdateCard update={latest} latest />
      {earlier.length > 0 && (
        <div className="border-t border-rule py-2.5">
          <button
            type="button"
            onClick={() => setShowEarlier(!showEarlier)}
            aria-expanded={showEarlier}
            className="label text-ink-2 hover:text-ink"
          >
            {earlier.length} earlier {earlier.length === 1 ? "update" : "updates"} <OpenSign open={showEarlier} />
          </button>
          {showEarlier && (
            <ul className="mt-2 flex flex-col">
              {earlier.map((update) => (
                <li key={update.id} className="border-t border-rule">
                  <UpdateCard update={update} latest={false} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

const STATUS: Record<MaterialUpdate["status"], string> = {
  failed: "Finished with a problem",
  cancelled: "Cancelled",
  done: "Done",
  running: "Updating",
};

function UpdateCard({ update, latest }: { update: MaterialUpdate; latest: boolean }) {
  const running = update.status === "running";
  const [open, setOpen] = useState(false);
  const title = `${KIND[update.kind]} ${update.filename}`;
  // Work in progress is always shown; a finished update opens on request.
  const showing = running || open;

  return (
    <article className="flex flex-col gap-3 py-3">
      <div className="flex flex-col gap-1.5 tab:flex-row tab:items-baseline tab:gap-5">
        {latest && <span className="label text-[10px] text-ink-3">Latest</span>}
        <h3 className="min-w-0 flex-1 text-sm">{title}</h3>
        <div className="label flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px]">
          <span className="flex items-center gap-1.5 text-ink-2">
            {update.status === "failed" && <Mark />}
            {running ? "Updating…" : `${STATUS[update.status]} · ${formatDateTime(update.finished_at ?? update.started_at)}`}
          </span>
          {!running && (
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="hover:underline">
              What changed <OpenSign open={open} />
            </button>
          )}
        </div>
      </div>
      {showing && (
        <div className="flex flex-col gap-4 tab:pl-0">
          <ol className="flex flex-col gap-1.5" aria-label={`Steps: ${title}`}>
            {update.steps.map((step) => (
              <li key={step.name} className="flex gap-3">
                <span aria-hidden className="label flex w-4 shrink-0 justify-center pt-0.5">
                  {step.state === "failed" ? <Mark /> : MARK[step.state]}
                </span>
                <span className="text-sm">
                  <span className="label text-[10px]">{step.label}</span>
                  <span className="sr-only"> ({step.state})</span>
                  {step.detail && <span className="text-ink-2"> · {step.detail}</span>}
                  {step.state === "running" && <span className="text-ink-3"> · working…</span>}
                </span>
              </li>
            ))}
          </ol>
          {update.report && <Report update={update} />}
        </div>
      )}
    </article>
  );
}

function Report({ update }: { update: MaterialUpdate }) {
  const report = update.report!;
  const relations = [
    ...report.new_relationships.map((r) => ({ ...r, sign: "+" })),
    ...report.removed_relationships.map((r) => ({ ...r, sign: "−" })),
  ];
  return (
    <div className="flex flex-col gap-4 border-t border-rule pt-3">
      <h4 className="label">What changed</h4>
      {report.new_concepts.length + report.removed_concepts.length > 0 && (
        <Group title="Concepts">
          {report.new_concepts.map((name) => (
            <li key={`+${name}`}>+ {name}</li>
          ))}
          {report.removed_concepts.map((name) => (
            <li key={`-${name}`} className="text-ink-3">
              − {name}
            </li>
          ))}
        </Group>
      )}
      {relations.length > 0 && (
        <Group title="Relationships">
          {relations.map((r) => (
            <li
              key={`${r.sign}${r.source}${r.type}${r.target}`}
              className={r.sign === "−" ? "text-ink-3" : undefined}
            >
              {r.sign} {r.source} {RELATION[r.type]} {r.target}
            </li>
          ))}
        </Group>
      )}
      {report.updated.length > 0 && (
        <Group title="Updated">
          {report.updated.map((n) => (
            <li key={n.name + (n.detail ?? "")}>
              ✓ {n.name}
              {n.detail && <span className="text-ink-2"> · {n.detail}</span>}
            </li>
          ))}
        </Group>
      )}
      {report.unchanged.length > 0 && (
        <Group title="Unchanged">
          {report.unchanged.map((n) => (
            <li key={n.name + (n.detail ?? "")} className="text-ink-2">
              ✓ {n.name}
              {n.detail && <> · {n.detail}</>}
            </li>
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 tab:flex-row tab:gap-5">
      <h5 className="label w-40 shrink-0 text-[10px] text-ink-3">{title}</h5>
      <ul className="flex flex-col gap-0.5 text-sm" aria-label={title}>
        {children}
      </ul>
    </div>
  );
}

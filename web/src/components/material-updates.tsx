"use client";

// What each change to the material did, on the Materials tab. The latest
// update shows its steps as they run (reading, its summary, the environment
// summary, concepts, the knowledge map, the roadmap), each saying what it
// did; once done, "What changed": new and removed concepts, new and removed
// relationships, what was updated and what was left as it was. Earlier
// updates are listed below, each opening to its own report.

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
  if (!query.data || query.data.length === 0) return null;
  const [latest, ...earlier] = query.data;

  return (
    <section aria-labelledby="updates-heading" className="flex flex-col gap-3">
      <h2 id="updates-heading" className="sr-only">
        Updates
      </h2>
      <UpdateCard update={latest} open />
      {earlier.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-zinc-600 dark:text-zinc-400">
            Earlier updates ({earlier.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {earlier.map((update) => (
              <li key={update.id}>
                <UpdateCard update={update} open={false} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function UpdateCard({ update, open }: { update: MaterialUpdate; open: boolean }) {
  const running = update.status === "running";
  const title = `${KIND[update.kind]} ${update.filename}`;
  const body = (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-1 text-sm" aria-label={`Steps: ${title}`}>
        {update.steps.map((step) => (
          <li key={step.name} className="flex gap-2">
            <span
              aria-hidden
              className={`w-4 shrink-0 text-center ${step.state === "failed" ? "text-red-600 dark:text-red-400" : step.state === "done" ? "text-emerald-700 dark:text-emerald-400" : "text-zinc-400"}`}
            >
              {MARK[step.state]}
            </span>
            <span>
              <span className="font-medium">{step.label}</span>
              <span className="sr-only"> ({step.state})</span>
              {step.detail && (
                <span className="text-zinc-600 dark:text-zinc-400"> · {step.detail}</span>
              )}
              {step.state === "running" && (
                <span className="text-zinc-500"> · working…</span>
              )}
            </span>
          </li>
        ))}
      </ol>
      {update.report && <Report update={update} />}
    </div>
  );

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium">{title}</h3>
        <span className="text-xs text-zinc-500">
          {running
            ? "Updating…"
            : `${update.status === "failed" ? "Finished with a problem" : "Done"} · ${formatDateTime(update.finished_at ?? update.started_at)}`}
        </span>
      </div>
      {open ? (
        body
      ) : (
        <details>
          <summary className="cursor-pointer text-sm text-zinc-600 dark:text-zinc-400">
            Steps and what changed
          </summary>
          <div className="mt-2">{body}</div>
        </details>
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
    <div className="flex flex-col gap-3 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
      <h4 className="font-medium">What changed</h4>
      {report.new_concepts.length + report.removed_concepts.length > 0 && (
        <Group title="Concepts">
          {report.new_concepts.map((name) => (
            <li key={`+${name}`}>+ {name}</li>
          ))}
          {report.removed_concepts.map((name) => (
            <li key={`-${name}`} className="text-zinc-500">
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
              className={r.sign === "−" ? "text-zinc-500" : undefined}
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
              {n.detail && <span className="text-zinc-600 dark:text-zinc-400"> · {n.detail}</span>}
            </li>
          ))}
        </Group>
      )}
      {report.unchanged.length > 0 && (
        <Group title="Unchanged">
          {report.unchanged.map((n) => (
            <li key={n.name + (n.detail ?? "")} className="text-zinc-600 dark:text-zinc-400">
              ✓ {n.name}
              {n.detail && <> · {n.detail}</>}
            </li>
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <h5 className="text-xs font-medium uppercase tracking-wide text-zinc-500">{title}</h5>
      <ul className="flex flex-col gap-0.5" aria-label={title}>
        {children}
      </ul>
    </div>
  );
}

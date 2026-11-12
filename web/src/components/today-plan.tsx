"use client";

// Today's recommended study plan, on the Overview tab. Worked out by fixed
// rules from where the learner stands (decision record 16): concepts missed
// lately first, then those due for review, then the next roadmap stage, then
// recently added material. Each session says why, how long it should take
// and which concepts it covers, and opens what it needs. An optional time
// budget, remembered in this browser, moves what does not fit to "With more
// time".

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";

import { useBudget, usePlan } from "@/hooks/use-plan";
import { usePractice, usePreparePractice } from "@/hooks/use-practice";
import type { PlanSession } from "@/lib/types";

const BUDGETS = [15, 30, 45, 60, 90];

export function TodayPlan({ environmentId }: { environmentId: string }) {
  const [budget, setBudget] = useBudget();
  const query = usePlan(environmentId, budget);
  // Practice being prepared changes the plan once it is ready: the practice
  // overview follows the preparation, and each change asks for the plan
  // again.
  const queryClient = useQueryClient();
  const practice = usePractice(environmentId);
  const preparing =
    practice.data?.concepts.filter((c) => c.state === "pending" || c.state === "generating")
      .length ?? 0;
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["environments", environmentId, "plan"] });
  }, [preparing, environmentId, queryClient]);
  const base = `/environments/${encodeURIComponent(environmentId)}`;

  return (
    <section aria-labelledby="plan-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="plan-heading" className="font-medium">
          Today&apos;s plan
        </h2>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          Time today
          <select
            value={budget ?? ""}
            onChange={(event) => setBudget(Number(event.target.value) || null)}
            className="rounded-lg border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
          >
            <option value="">No limit</option>
            {BUDGETS.map((m) => (
              <option key={m} value={m}>
                {m} min
              </option>
            ))}
          </select>
        </label>
      </div>
      {query.isPending ? (
        <p className="text-sm text-zinc-500">Working out today&apos;s plan…</p>
      ) : query.isError ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          Could not work out today&apos;s plan: {query.error.message}
        </p>
      ) : query.data.sessions.length === 0 && query.data.later.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Nothing planned today. Once materials are read and practice is prepared,
          today&apos;s reviews and next steps appear here.
        </p>
      ) : (
        <>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {query.data.sessions.length}{" "}
            {query.data.sessions.length === 1 ? "session" : "sessions"}, about{" "}
            {query.data.minutes} minutes. Worked out from what is due, what was
            missed and where you are on the roadmap; times are estimates.
          </p>
          {query.data.sessions.length === 0 && (
            <p className="text-sm">Nothing fits in {budget} minutes today.</p>
          )}
          <ol className="flex flex-col gap-3" aria-label="Today's sessions">
            {query.data.sessions.map((session, n) => (
              <li key={session.title}>
                <SessionCard
                  environmentId={environmentId}
                  base={base}
                  number={n + 1}
                  session={session}
                />
              </li>
            ))}
          </ol>
          {query.data.later.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">With more time</h3>
              <ul className="flex flex-col gap-1 text-sm" aria-label="With more time">
                {query.data.later.map((session) => (
                  <li key={session.title} className="text-zinc-600 dark:text-zinc-400">
                    {session.minutes} min · {session.title}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function SessionCard({
  environmentId,
  base,
  number,
  session,
}: {
  environmentId: string;
  base: string;
  number: number;
  session: PlanSession;
}) {
  const prepare = usePreparePractice(environmentId);
  const ids = session.concepts.map((c) => c.id);
  const button =
    "rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-900";
  const quiet =
    "rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium dark:border-zinc-700";
  const practise = `${base}/practice?concepts=${ids.map(encodeURIComponent).join(",")}&title=${encodeURIComponent(session.title)}`;

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-xs font-medium tabular-nums text-zinc-500">
          {number}. {session.minutes} min
        </span>
        <h3 className="font-semibold">{session.title}</h3>
      </div>
      <p className="text-sm">{session.rationale}</p>
      {session.kind !== "skim" && session.concepts.length > 0 && (
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          {session.concepts.map((c, n) => (
            <span key={c.id}>
              {n > 0 && ", "}
              <Link
                href={`${base}/knowledge-map?concept=${encodeURIComponent(c.id)}`}
                className="underline decoration-zinc-400 underline-offset-2 hover:decoration-current dark:decoration-zinc-500"
              >
                {c.name}
              </Link>
            </span>
          ))}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {(session.kind === "strengthen" || session.kind === "review") && (
          <Link href={practise} className={button}>
            Start
          </Link>
        )}
        {session.kind === "learn" && (
          <>
            <Link href={`${base}/roadmap#stage-${session.stage}`} className={quiet}>
              Read on the roadmap
            </Link>
            {session.needs_preparing ? (
              <button
                type="button"
                onClick={() => prepare.mutate(ids)}
                disabled={prepare.isPending || prepare.isSuccess}
                className={`${button} disabled:opacity-50`}
              >
                {prepare.isSuccess ? "Preparing in the background…" : "Prepare practice"}
              </button>
            ) : (
              <Link href={practise} className={button}>
                Practise
              </Link>
            )}
          </>
        )}
        {session.kind === "skim" && (
          <Link href={`${base}/materials`} className={quiet}>
            Read the summary of {session.document?.filename}
          </Link>
        )}
      </div>
      {prepare.error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {prepare.error.message}
        </p>
      )}
    </article>
  );
}

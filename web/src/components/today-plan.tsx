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
import { useEffect, useState } from "react";

import { Empty, Loading, LoadError } from "@/components/query-states";
import { button, Mark, OpenSign, SectionHead } from "@/components/ui";
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

  const sessions = query.data?.sessions ?? [];
  return (
    <section aria-labelledby="plan-heading" className="flex flex-col">
      <SectionHead
        id="plan-heading"
        right={
          <label className="flex items-center gap-2">
            Time today
            <select
              value={budget ?? ""}
              onChange={(event) => setBudget(Number(event.target.value) || null)}
              className="label border-b border-ink bg-transparent pb-0.5 text-ink"
            >
              <option value="">No limit</option>
              {BUDGETS.map((m) => (
                <option key={m} value={m}>
                  {m} min
                </option>
              ))}
            </select>
          </label>
        }
      >
        <span aria-hidden>02 / </span>Today&apos;s plan
      </SectionHead>
      {query.isPending ? (
        <Loading what="today's plan" lines={3} />
      ) : query.isError ? (
        <LoadError
          what="today's plan"
          error={query.error}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
        />
      ) : sessions.length === 0 && query.data.later.length === 0 ? (
        <Empty>
          Nothing planned today. Once materials are read and practice is prepared,
          today&apos;s reviews and next steps appear here.
        </Empty>
      ) : (
        <>
          <PlanNote count={sessions.length} minutes={query.data.minutes} />
          {sessions.length === 0 && (
            <p className="display py-3 text-[19px] text-ink-2 italic">
              Nothing fits in {budget} minutes today.
            </p>
          )}
          <ol aria-label="Today's sessions">
            {sessions.map((session, n) => (
              <li key={session.title} className={n > 0 ? "border-t border-rule" : ""}>
                <SessionCard
                  environmentId={environmentId}
                  base={base}
                  number={n + 1}
                  session={session}
                  first={n === 0}
                />
              </li>
            ))}
          </ol>
          {query.data.later.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-rule pt-3">
              <h3 className="label text-ink-3">With more time</h3>
              <ul className="flex flex-col gap-1" aria-label="With more time">
                {query.data.later.map((session) => (
                  <li key={session.title} className="flex gap-3 text-sm text-ink-2">
                    <span className="label w-14 shrink-0 text-ink-3">{session.minutes} min</span>
                    {session.title}
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

// How many sessions and how long, with how the plan is made one click away.
function PlanNote({ count, minutes }: { count: number; minutes: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2 pb-2">
      <div className="label flex flex-wrap items-center gap-x-4 gap-y-1 text-ink-2">
        <span>
          {count} {count === 1 ? "session" : "sessions"}, about {minutes} minutes
        </span>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-ink-3 hover:text-ink"
        >
          How the plan is made <OpenSign open={open} />
        </button>
      </div>
      {open && (
        <p className="display border-l border-ink pl-3.5 text-[17px] leading-[1.25] text-ink-2 italic">
          Worked out from what is due, what was missed and where you are on the roadmap; times
          are estimates.
        </p>
      )}
    </div>
  );
}

const KIND_LABEL: Record<PlanSession["kind"], string> = {
  strengthen: "Strengthen",
  review: "Review",
  learn: "Learn",
  skim: "Skim",
};

function SessionCard({
  environmentId,
  base,
  number,
  session,
  first,
}: {
  environmentId: string;
  base: string;
  number: number;
  session: PlanSession;
  first: boolean;
}) {
  const prepare = usePreparePractice(environmentId);
  const ids = session.concepts.map((c) => c.id);
  const main = first ? button.primary : button.outline;
  const practise = `${base}/practice?concepts=${ids.map(encodeURIComponent).join(",")}&title=${encodeURIComponent(session.title)}`;
  // "Strengthen: Round Robin…" reads as a kind and a title; the kind is
  // shown on its own.
  const colon = session.title.indexOf(": ");
  const rest = colon > 0 ? session.title.slice(colon + 2) : session.title;
  const title = rest.charAt(0).toUpperCase() + rest.slice(1);

  return (
    <article className="flex flex-col gap-3 py-[18px] tab:flex-row tab:gap-6">
      <div className="flex items-center gap-3 tab:w-36 tab:shrink-0 tab:items-start tab:pt-1.5">
        <span className="label text-ink-3">{String(number).padStart(2, "0")}</span>
        <span className="label flex items-center gap-1.5">
          {session.kind === "strengthen" && <Mark />}
          {KIND_LABEL[session.kind]}
        </span>
        <span className="label ml-auto text-ink-3 tab:hidden">{session.minutes} min</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <h3 className="display text-2xl leading-[1.05] tracking-[-0.015em] tab:text-[28px]">{title}</h3>
        <p className="text-sm leading-normal text-ink-2">{session.rationale}</p>
        {session.kind !== "skim" && session.concepts.length > 0 && (
          <ul className="flex flex-wrap gap-x-3.5 gap-y-1" aria-label="Concepts in this session">
            {session.concepts.map((c) => (
              <li key={c.id}>
                <Link
                  href={`${base}/knowledge-map?concept=${encodeURIComponent(c.id)}`}
                  className="label border-b border-rule text-[10px] text-ink-2 hover:border-accent hover:text-ink"
                >
                  {c.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {session.kind === "learn" && (
          <Link href={`${base}/roadmap#stage-${session.stage}`} className={`${button.link} mt-1 w-fit text-[10px]`}>
            Read on the roadmap <span aria-hidden>→</span>
          </Link>
        )}
        {prepare.error && (
          <p role="alert" className="label flex items-center gap-2">
            <Mark />
            {prepare.error.message}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2 tab:w-32 tab:shrink-0 tab:items-end tab:pt-1">
        <span className="label hidden text-ink-3 tab:block">{session.minutes} min</span>
        {(session.kind === "strengthen" || session.kind === "review") && (
          <Link href={practise} className={main}>
            Start{first && <span aria-hidden> →</span>}
          </Link>
        )}
        {session.kind === "learn" &&
          (session.needs_preparing ? (
            <button
              type="button"
              onClick={() => prepare.mutate(ids)}
              disabled={prepare.isPending || prepare.isSuccess}
              className={main}
            >
              {prepare.isSuccess ? "Preparing in the background…" : "Prepare practice"}
            </button>
          ) : (
            <Link href={practise} className={main}>
              Practise
            </Link>
          ))}
        {session.kind === "skim" && (
          <Link href={`${base}/materials`} className={main}>
            Read the summary of {session.document?.filename}
          </Link>
        )}
      </div>
    </article>
  );
}

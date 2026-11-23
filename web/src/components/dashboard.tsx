"use client";

// The home screen, a starting point rather than a control panel (decision
// record 28). It answers one question first: where did I leave off, and
// what next? The environment opened last leads, with the first session of
// its plan and the document read last beside it; the index of environments
// follows, one line of status each. With no environment yet, it welcomes
// instead: what Paideia does, its five steps, and one action. The create
// flow opens in place.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EnvironmentCard } from "@/components/environment-card";
import { EnvironmentForm } from "@/components/environment-form";
import { Loading, LoadError } from "@/components/query-states";
import { KIND_LABEL, practiseHref, sessionTitle } from "@/components/today-plan";
import { button, Mark } from "@/components/ui";
import { useCreateEnvironment, useEnvironments } from "@/hooks/use-environments";
import { useBudget, usePlan } from "@/hooks/use-plan";
import { useLastEnvironment, useLastReading } from "@/lib/local";
import type { Environment, PlanSession } from "@/lib/types";

export function Dashboard() {
  const router = useRouter();
  const environments = useEnvironments();
  const create = useCreateEnvironment();
  const [isCreating, setIsCreating] = useState(false);
  const lastId = useLastEnvironment();

  function closeForm() {
    setIsCreating(false);
    create.reset();
  }

  const form = isCreating && (
    <section aria-labelledby="new-environment" className="flex max-w-2xl flex-col gap-5 border-t border-ink pt-3">
      <h2 id="new-environment" className="label">
        New environment
      </h2>
      <EnvironmentForm
        submitLabel="Create environment"
        isPending={create.isPending}
        error={create.error}
        onCancel={closeForm}
        onSubmit={(input) =>
          create.mutate(input, {
            // Go straight into the new environment.
            onSuccess: (environment) => router.push(`/environments/${environment.id}`),
          })
        }
      />
    </section>
  );

  const page = "flex flex-col gap-14 px-5 pt-7 pb-16 tab:px-8 tab:pt-9 desk:gap-16 desk:px-24 desk:pt-11";

  if (environments.isPending) {
    return (
      <div className={page}>
        <Loading what="environments" lines={3} />
      </div>
    );
  }
  if (environments.isError) {
    return (
      <div className={page}>
        <LoadError
          what="environments"
          error={environments.error}
          onRetry={() => void environments.refetch()}
          retrying={environments.isFetching}
        />
      </div>
    );
  }

  const list = environments.data;
  if (list.length === 0) {
    return (
      <div className={page}>
        <Welcome creating={isCreating} onCreate={() => setIsCreating(true)} />
        {form}
        <HowItWorks />
        <p className="flex flex-col gap-1 border-t border-rule pt-3.5 tab:flex-row tab:items-baseline tab:gap-4">
          <span className="label text-ink-3">On this computer</span>
          <span className="text-[14px] leading-[1.45] text-ink-2">
            Your material and your answers never leave this machine; the language model runs here
            too.
          </span>
        </p>
      </div>
    );
  }

  // The environment opened last in this browser, else the one changed last.
  const latest = [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
  const current = list.find((e) => e.id === lastId) ?? latest;

  return (
    <div className={page}>
      <Continue environment={current} environments={list} />
      <section aria-labelledby="environments-heading" className="flex flex-col">
        <div className="flex items-center gap-4 border-t border-ink py-3">
          <h2 id="environments-heading" className="label flex-1">
            Your environments — {list.length}
          </h2>
          {!isCreating && (
            <button type="button" onClick={() => setIsCreating(true)} className={button.outline}>
              New environment <span aria-hidden>[+]</span>
            </button>
          )}
        </div>
        {form && <div className="pb-8">{form}</div>}
        <ol aria-label="Environments" className="border-t border-rule">
          {list.map((environment) => (
            <li key={environment.id} className="border-b border-rule">
              <EnvironmentCard environment={environment} />
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

// Where you left off: the environment, the first session of today's plan
// with its Start, and the document read last.
function Continue({
  environment,
  environments,
}: {
  environment: Environment;
  environments: Environment[];
}) {
  const [budget] = useBudget();
  const plan = usePlan(environment.id, budget);
  const reading = useLastReading();
  const readingIn = reading && environments.find((e) => e.id === reading.environmentId);
  const base = `/environments/${encodeURIComponent(environment.id)}`;
  const next = plan.data?.sessions[0];

  return (
    <section aria-labelledby="continue-heading" className="flex flex-col gap-10 desk:flex-row desk:gap-16">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <p className="label">Continue</p>
        <h1 id="continue-heading" className="display text-[46px] leading-[0.95] tracking-[-0.03em] text-balance tab:text-[60px] desk:text-[72px]">
          <Link href={base} className="hover:underline hover:decoration-accent hover:decoration-2 hover:underline-offset-8">
            {environment.name}
          </Link>
        </h1>
        <div className="flex flex-col gap-2.5 border-t border-ink pt-4">
          {plan.isPending ? (
            <Loading what="today's plan" lines={2} />
          ) : plan.isError || !next ? (
            <>
              <p className="label">Today&apos;s plan</p>
              <p className="max-w-[600px] text-[16px] leading-[1.55] text-ink-2">
                {plan.isError
                  ? `Today's plan could not load: ${plan.error.message}`
                  : "Nothing planned today. The environment shows what is ready to read and practise."}
              </p>
              <div className="pt-2">
                <Link href={base} className={button.primary}>
                  Open the environment <span aria-hidden>→</span>
                </Link>
              </div>
            </>
          ) : (
            <>
              <p className="label flex items-center gap-2">
                {next.kind === "strengthen" && <Mark />}
                {KIND_LABEL[next.kind]} — first in today&apos;s plan
              </p>
              <h2 className="display text-[28px] leading-[1.05] tracking-[-0.015em] tab:text-[34px]">
                {sessionTitle(next)}
              </h2>
              <p className="max-w-[600px] text-[16px] leading-[1.55] text-ink-2">{next.rationale}</p>
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-2">
                <NextAction base={base} session={next} />
                <span className="text-[13px] leading-[1.4] text-ink-2">
                  About {next.minutes} {next.minutes === 1 ? "minute" : "minutes"}
                </span>
                {(plan.data?.sessions.length ?? 0) > 1 && (
                  <Link href={base} className={button.link}>
                    All of today&apos;s plan — {plan.data?.sessions.length} sessions <span aria-hidden>→</span>
                  </Link>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      {readingIn && reading && (
        <div className="flex flex-col gap-3 desk:w-[300px] desk:shrink-0 desk:pt-0.5">
          <p className="label text-ink-2">Or keep reading</p>
          <div className="flex flex-col gap-1.5 border-y border-rule py-3.5">
            <p className="display text-[28px] leading-[1.05] tracking-[-0.015em] break-words">{reading.filename}</p>
            <p className="text-[13px] leading-[1.4] text-ink-2">
              {readingIn.name} · page {reading.page} of {reading.pages}
            </p>
          </div>
          <Link
            href={`/environments/${encodeURIComponent(reading.environmentId)}/materials/${encodeURIComponent(reading.documentId)}#page-${reading.page}`}
            className={`${button.link} w-fit`}
          >
            Resume reading <span aria-hidden>→</span>
          </Link>
        </div>
      )}
    </section>
  );
}

// The first session's action, as on the Overview: practice for a review or
// a missed concept, the plan itself when a stage needs preparing first.
function NextAction({ base, session }: { base: string; session: PlanSession }) {
  if (session.kind === "skim") {
    return (
      <Link href={`${base}/materials`} className={button.primary}>
        Read the summary of {session.document?.filename} <span aria-hidden>→</span>
      </Link>
    );
  }
  if (session.kind === "learn" && session.needs_preparing) {
    return (
      <Link href={base} className={button.primary}>
        Prepare it on the overview <span aria-hidden>→</span>
      </Link>
    );
  }
  return (
    <Link href={practiseHref(base, session)} className={button.primary}>
      Start <span aria-hidden>→</span>
    </Link>
  );
}

// A first visit: what Paideia is, in one sentence, and the one thing to do.
function Welcome({ creating, onCreate }: { creating: boolean; onCreate: () => void }) {
  return (
    <section aria-labelledby="welcome-heading" className="flex flex-col gap-8 desk:flex-row desk:items-end desk:gap-16">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <p className="label">Welcome to Paideia</p>
        <h1 id="welcome-heading" className="display text-[54px] leading-[0.92] tracking-[-0.03em] text-balance tab:text-[72px] desk:text-[88px]">
          A library that reads with you.
        </h1>
      </div>
      <div className="flex flex-col gap-5 desk:w-[400px] desk:shrink-0 desk:pb-2">
        <p className="text-[18px] leading-[1.5] text-ink-2 tab:text-[20px]">
          Put a subject&apos;s PDFs in one place. Paideia reads them on this computer, writes
          summaries that cite their pages, maps the concepts and plans what to practise each day.
        </p>
        {!creating && (
          <div>
            <button type="button" onClick={onCreate} className={`${button.primary} w-full tab:w-fit`}>
              Create your first environment <span aria-hidden>[+]</span>
            </button>
          </div>
        )}
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Link href="/guide" className={button.link}>
            Read the guide <span aria-hidden>→</span>
          </Link>
          <span className="text-[13px] leading-[1.4] text-ink-2">Five steps, two minutes</span>
        </p>
      </div>
    </section>
  );
}

const STEPS = [
  ["Organise", "One environment per subject: a course, a module, a reading list. Each keeps its own material."],
  ["Add", "Upload the PDFs: lecture notes, chapters, problem sheets, up to 50 MB each. Scans and photographs work too, as pictures."],
  ["Build", "Each page is read and split into passages you can search by words or meaning. Concepts and their links are found."],
  ["Learn", "Summaries that cite the page, a knowledge map, a roadmap in stages, and practice written from your own material."],
  ["Return", "Today's plan says what is due. A concept you recall comes back further apart; one you miss comes back sooner."],
] as const;

function HowItWorks() {
  return (
    <section aria-labelledby="how-heading" className="flex flex-col">
      <h2 id="how-heading" className="label border-t border-ink pt-3">
        How it works — organise, add, build, learn, return
      </h2>
      <ol className="grid gap-x-0 pt-5 tab:grid-cols-2 desk:grid-cols-5">
        {STEPS.map(([title, text], i) => (
          <li
            key={title}
            className="flex flex-col gap-2 border-b border-rule py-4 tab:border-b-0 desk:border-l desk:px-6 desk:py-0 desk:first:border-l-0 desk:first:pl-0"
          >
            <span className="label text-ink-3">{String(i + 1).padStart(2, "0")}</span>
            <h3 className="display text-[28px] leading-none tracking-[-0.015em] tab:text-[32px]">{title}</h3>
            <p className="text-[15px] leading-[1.55] text-ink-2">{text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

"use client";

// The home screen: every environment as a row of an index, plus the create
// flow, which opens in place above the list.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { EnvironmentCard } from "@/components/environment-card";
import { EnvironmentForm } from "@/components/environment-form";
import { Loading, LoadError } from "@/components/query-states";
import { button, Standfirst } from "@/components/ui";
import {
  useCreateEnvironment,
  useEnvironments,
} from "@/hooks/use-environments";

export function Dashboard() {
  const router = useRouter();
  const environments = useEnvironments();
  const create = useCreateEnvironment();
  const [isCreating, setIsCreating] = useState(false);

  function closeForm() {
    setIsCreating(false);
    create.reset();
  }

  const count = environments.data?.length;

  return (
    <div className="flex flex-col gap-8 px-5 pt-7 pb-14 tab:px-8 tab:pt-9 desk:px-24 desk:pt-10">
      <div className="flex flex-col gap-4 desk:flex-row desk:items-end desk:gap-10">
        <div className="flex flex-1 flex-col gap-3.5">
          <h1 className="label">
            Your environments{count ? ` — ${count}` : ""}
          </h1>
          <p className="display text-[46px] leading-[0.92] tracking-[-0.03em] tab:text-[60px] desk:text-[76px]">
            One environment
            <br />
            per subject.
          </p>
        </div>
        <div className="flex flex-col gap-3.5 desk:w-60 desk:shrink-0 desk:pb-1.5">
          <Standfirst>Each keeps its own material, summaries and roadmap.</Standfirst>
          {!isCreating && (
            <button type="button" onClick={() => setIsCreating(true)} className={`${button.primary} w-full tab:w-fit`}>
              New environment <span aria-hidden>[+]</span>
            </button>
          )}
        </div>
      </div>

      {isCreating && (
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
                onSuccess: (environment) =>
                  router.push(`/environments/${environment.id}`),
              })
            }
          />
        </section>
      )}

      {environments.isPending ? (
        <Loading what="environments" lines={3} />
      ) : environments.isError ? (
        <LoadError
          what="environments"
          error={environments.error}
          onRetry={() => void environments.refetch()}
          retrying={environments.isFetching}
        />
      ) : environments.data.length === 0 ? (
        !isCreating && (
          <p className="display max-w-xl border-t border-ink pt-5 text-[30px] leading-[1.05] tracking-[-0.02em]">
            No environments yet. <span className="text-ink-2 italic">Create one to get started.</span>
          </p>
        )
      ) : (
        <ol aria-label="Environments" className="border-t border-ink">
          {environments.data.map((environment) => (
            <li key={environment.id} className="border-b border-rule">
              <EnvironmentCard environment={environment} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

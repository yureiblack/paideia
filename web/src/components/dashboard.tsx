"use client";

// The home screen: every environment as a card, plus the create flow.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { EnvironmentCard } from "@/components/environment-card";
import { EnvironmentForm } from "@/components/environment-form";
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

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Your environments
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            One per subject. Each keeps its own material, summaries and
            roadmap.
          </p>
        </div>
        {!isCreating && (
          <button
            type="button"
            onClick={() => setIsCreating(true)}
            className="shrink-0 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            New environment
          </button>
        )}
      </div>

      {isCreating && (
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
      )}

      {environments.isPending ? (
        <p className="text-zinc-500">Loading environments…</p>
      ) : environments.isError ? (
        <div role="alert" className="flex flex-col items-start gap-2">
          <p className="text-red-600 dark:text-red-400">
            Could not load environments: {environments.error.message}
          </p>
          <button
            type="button"
            onClick={() => environments.refetch()}
            className="text-sm font-medium underline"
          >
            Try again
          </button>
        </div>
      ) : environments.data.length === 0 ? (
        <p className="text-zinc-500">
          No environments yet. Create one to get started.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {environments.data.map((environment) => (
            <EnvironmentCard key={environment.id} environment={environment} />
          ))}
        </div>
      )}
    </div>
  );
}

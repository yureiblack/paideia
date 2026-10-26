"use client";

// The frame around every tab of an environment: its name, the edit and delete
// actions, and the tabs. It loads the environment once; the tabs below share
// that cached copy instead of fetching it again.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { EnvironmentForm } from "@/components/environment-form";
import { EnvironmentTabs } from "@/components/environment-tabs";
import {
  useDeleteEnvironment,
  useEnvironment,
  useUpdateEnvironment,
} from "@/hooks/use-environments";
import { ApiError } from "@/lib/api";
import type { Environment } from "@/lib/types";

export function EnvironmentShell({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const environment = useEnvironment(id);

  if (environment.isPending) {
    return <p className="text-zinc-500">Loading environment…</p>;
  }

  if (environment.isError) {
    const error = environment.error;
    // 404: no such environment. 422: the id in the URL is not even a UUID.
    const isMissing =
      error instanceof ApiError && (error.status === 404 || error.status === 422);
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <h1 className="text-xl font-semibold">
          {isMissing ? "Environment not found" : "Could not load environment"}
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          {isMissing
            ? "It may have been deleted, or the link is wrong."
            : error.message}
        </p>
        <Link href="/" className="text-sm font-medium underline">
          Back to all environments
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <EnvironmentHeader environment={environment.data} />
      <EnvironmentTabs id={id} />
      <div>{children}</div>
    </div>
  );
}

function EnvironmentHeader({ environment }: { environment: Environment }) {
  const router = useRouter();
  const update = useUpdateEnvironment(environment.id);
  const remove = useDeleteEnvironment();
  const [isEditing, setIsEditing] = useState(false);

  function closeForm() {
    setIsEditing(false);
    update.reset();
  }

  function handleDelete() {
    const confirmed = window.confirm(
      `Delete "${environment.name}"? This cannot be undone.`,
    );
    if (!confirmed) return;
    remove.mutate(environment.id, { onSuccess: () => router.push("/") });
  }

  if (isEditing) {
    return (
      <EnvironmentForm
        initial={{
          name: environment.name,
          description: environment.description,
        }}
        submitLabel="Save changes"
        isPending={update.isPending}
        error={update.error}
        onCancel={closeForm}
        onSubmit={(input) => update.mutate(input, { onSuccess: closeForm })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Link href="/" className="text-sm text-zinc-500 hover:underline">
        ← All environments
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            {environment.name}
          </h1>
          {environment.description && (
            <p className="max-w-2xl text-zinc-600 dark:text-zinc-400">
              {environment.description}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium dark:border-zinc-700"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={remove.isPending}
            className="rounded-lg border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 disabled:opacity-50 dark:border-red-900 dark:text-red-400"
          >
            {remove.isPending ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
      {remove.isError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          Could not delete: {remove.error.message}
        </p>
      )}
    </div>
  );
}

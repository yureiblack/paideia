"use client";

// The states every section that loads data can be in besides showing it,
// the same on every page (decision record 19): loading, a failure with Try
// again, and nothing yet with what to do next. QueryState picks between
// loading, failure and the section itself for one query.

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

// Placeholder lines while a section loads. Screen readers hear what is
// loading; the lines pulse only for those who have not asked for less motion.
export function Loading({ what, lines = 2 }: { what: string; lines?: number }) {
  return (
    <div role="status" className="flex flex-col gap-2 py-1">
      <span className="sr-only">Loading {what}…</span>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          aria-hidden="true"
          className={`h-3 rounded bg-zinc-200 motion-safe:animate-pulse dark:bg-zinc-800 ${
            i % 2 ? "w-1/2" : "w-2/3"
          }`}
        />
      ))}
    </div>
  );
}

// A section that could not load: why, and Try again. retrying shows while
// the request is being made again. When the API answered, its reference for
// the request is shown too, to find it in the server's logs.
export function LoadError({
  what,
  error,
  onRetry,
  retrying = false,
}: {
  what: string;
  error: Error;
  onRetry: () => void;
  retrying?: boolean;
}) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
      <p className="text-red-600 dark:text-red-400">
        Could not load {what}: {error.message}
      </p>
      <Reference error={error} />
      <button
        type="button"
        onClick={onRetry}
        disabled={retrying}
        className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium disabled:opacity-50 dark:border-zinc-700"
      >
        {retrying ? "Trying again…" : "Try again"}
      </button>
    </div>
  );
}

// The API's id for a failed request, shortened; hovering shows all of it.
export function Reference({ error }: { error: Error | null }) {
  if (!(error instanceof ApiError) || !error.requestId) return null;
  return (
    <span className="text-xs text-zinc-500" title={error.requestId}>
      Reference {error.requestId.slice(0, 8)}
    </span>
  );
}

// Nothing to show yet: what that means, and what to do next.
export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-zinc-300 p-4 text-sm text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
      <div>{children}</div>
      {action}
    </div>
  );
}

// One query's section: placeholder lines while it loads, the failure with
// Try again, otherwise children with its data.
export function QueryState<T>({
  query,
  what,
  lines,
  children,
}: {
  query: UseQueryResult<T, Error>;
  what: string;
  lines?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Loading what={what} lines={lines} />;
  if (query.isError) {
    return (
      <LoadError
        what={what}
        error={query.error}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  return <>{children(query.data)}</>;
}

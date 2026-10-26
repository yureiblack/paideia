// One environment on the dashboard. The whole card is a link to it.

import Link from "next/link";

import { formatDate } from "@/lib/format";
import type { Environment } from "@/lib/types";

export function EnvironmentCard({ environment }: { environment: Environment }) {
  return (
    <Link
      href={`/environments/${environment.id}`}
      className="flex flex-col gap-2 rounded-xl border border-zinc-200 p-5 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
    >
      <h2 className="font-semibold">{environment.name}</h2>
      {environment.description && (
        <p className="line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
          {environment.description}
        </p>
      )}
      <p className="mt-auto text-xs text-zinc-500">
        Created {formatDate(environment.created_at)}
      </p>
    </Link>
  );
}

// One environment on the home screen, a row of the index with today's plan
// beside it. The whole row is a link to it.

import Link from "next/link";

import { PlanLine } from "@/components/plan-line";
import { formatDate } from "@/lib/format";
import type { Environment } from "@/lib/types";

export function EnvironmentCard({ environment }: { environment: Environment }) {
  return (
    <Link
      href={`/environments/${environment.id}`}
      className="group flex flex-col gap-3 py-5 hover:bg-paper-2 tab:flex-row tab:items-start tab:gap-8 tab:px-4 tab:-mx-4"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <h2 className="display text-[28px] leading-none tracking-[-0.02em] tab:text-[40px]">
          {environment.name}
        </h2>
        {environment.description && (
          <p className="display line-clamp-2 text-base text-ink-2 italic tab:text-lg">
            {environment.description}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-1.5 tab:w-60 tab:shrink-0 tab:pt-1.5">
        <PlanLine environmentId={environment.id} />
        <p className="label text-ink-3">Created {formatDate(environment.created_at)}</p>
      </div>
      <span aria-hidden className="label hidden pt-1.5 group-hover:underline tab:block">
        Open →
      </span>
    </Link>
  );
}

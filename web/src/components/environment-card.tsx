// One environment on the home screen, a row of the index: its name and
// description, and beside them one line of status from today's plan and
// one about its documents (decision record 28). The whole row is a link.

import Link from "next/link";

import { PlanLine } from "@/components/plan-line";
import type { Environment } from "@/lib/types";

export function EnvironmentCard({ environment }: { environment: Environment }) {
  return (
    <Link
      href={`/environments/${environment.id}`}
      className="group flex flex-col gap-3 py-5 hover:bg-paper-2 tab:-mx-4 tab:flex-row tab:items-start tab:gap-10 tab:px-4"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <h3 className="display text-[30px] leading-none tracking-[-0.02em] tab:text-[38px]">
          {environment.name}
        </h3>
        {environment.description && (
          <p className="line-clamp-2 text-[15px] leading-[1.5] text-ink-2">{environment.description}</p>
        )}
      </div>
      <div className="flex flex-col gap-1 tab:w-72 tab:shrink-0 tab:pt-1.5">
        <PlanLine environmentId={environment.id} />
      </div>
      <span aria-hidden className="label hidden pt-2 group-hover:underline group-hover:decoration-accent tab:block">
        Open →
      </span>
    </Link>
  );
}

"use client";

// The row of tabs on an environment. Each tab is its own URL, so a later phase
// fills a tab by replacing one page file, and the back button just works.

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { label: "Overview", segment: "" },
  { label: "Materials", segment: "materials" },
  { label: "Knowledge map", segment: "knowledge-map" },
  { label: "Roadmap", segment: "roadmap" },
  { label: "Summary", segment: "summary" },
  { label: "Practice", segment: "practice" },
];

export function EnvironmentTabs({ id }: { id: string }) {
  const pathname = usePathname();
  const base = `/environments/${id}`;

  return (
    <nav
      aria-label="Environment sections"
      className="flex gap-1 overflow-x-auto border-b border-zinc-200 dark:border-zinc-800"
    >
      {TABS.map(({ label, segment }) => {
        const href = segment ? `${base}/${segment}` : base;
        const isActive = pathname === href;
        return (
          <Link
            key={label}
            href={href}
            aria-current={isActive ? "page" : undefined}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
              isActive
                ? "border-zinc-900 dark:border-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

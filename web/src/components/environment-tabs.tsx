"use client";

// The row of tabs on an environment. Each tab is its own URL, so a later phase
// fills a tab by replacing one page file, and the back button just works.

import Link from "next/link";
import { usePathname } from "next/navigation";

export const TABS = [
  { label: "Overview", segment: "" },
  { label: "Materials", segment: "materials" },
  { label: "Search", segment: "search" },
  { label: "Knowledge map", segment: "knowledge-map" },
  { label: "Roadmap", segment: "roadmap" },
  { label: "Summary", segment: "summary" },
  { label: "Practice", segment: "practice" },
];

// The name of the tab a path is on, for the page's title.
export function tabLabel(id: string, pathname: string): string {
  const base = `/environments/${id}`;
  const tab = TABS.find(({ segment }) => (segment ? `${base}/${segment}` : base) === pathname);
  return tab?.label ?? "Overview";
}

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
            // The row scrolls sideways on a phone, which clips anything drawn
            // outside it, so the focus ring is drawn just inside the tab.
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium focus-visible:-outline-offset-2 ${
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

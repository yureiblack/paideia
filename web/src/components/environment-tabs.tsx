"use client";

// An environment's sections, numbered like a table of contents. Each section
// is its own URL, so the back button just works. One list, three shapes: a
// column beside the page on a desktop, a row under the masthead on a tablet,
// and a full-screen sheet behind the Contents button on a phone.

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

// "01", "02": a section's number in the contents.
export function tabNumber(id: string, pathname: string): string {
  const index = TABS.findIndex(({ label }) => label === tabLabel(id, pathname));
  return String(index + 1).padStart(2, "0");
}

export function EnvironmentTabs({ id, onNavigate }: { id: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const base = `/environments/${id}`;

  return (
    <nav aria-label="Environment sections" className="min-w-0 flex-1">
      <ol className="flex flex-col border-t border-ink tab:flex-row tab:gap-6 tab:overflow-x-auto tab:border-0 desk:flex-col desk:gap-0">
        {TABS.map(({ label, segment }, index) => {
          const href = segment ? `${base}/${segment}` : base;
          const isActive = pathname === href;
          return (
            <li key={label} className="border-b border-rule tab:border-0 desk:border-b">
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={isActive ? "page" : undefined}
                // The row scrolls sideways on a tablet, which clips anything
                // drawn outside it, so the focus ring is drawn inside.
                className="group flex h-13 items-center gap-3.5 whitespace-nowrap focus-visible:-outline-offset-2 tab:h-11 tab:gap-2 desk:h-[38px] desk:gap-3"
              >
                <span
                  aria-hidden
                  className={`label flex h-[18px] w-[26px] shrink-0 items-center justify-center text-[10px] ${
                    isActive ? "bg-accent text-on-accent" : "text-ink-3 group-hover:text-ink"
                  }`}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span
                  className={`display text-[28px] tab:font-sans tab:text-sm tab:tracking-normal desk:text-[15px] ${
                    isActive ? "tab:font-semibold" : "group-hover:underline group-hover:decoration-accent group-hover:underline-offset-4"
                  }`}
                >
                  {label}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

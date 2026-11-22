"use client";

// An environment's sections, numbered like a table of contents and grouped
// by what they are for (decision record 28): the Overview, where a visit
// starts; the Library, what the material says; and Learn, what to do with
// it. Each section is its own URL, so the back button just works. One list,
// three shapes: a column beside the page on a desktop, a row under the
// masthead on a tablet, and a full-screen sheet behind the Contents button
// on a phone.

import Link from "next/link";
import { usePathname } from "next/navigation";

type Tab = { label: string; segment: string; group: "start" | "Library" | "Learn" };

export const TABS: Tab[] = [
  { label: "Overview", segment: "", group: "start" },
  { label: "Materials", segment: "materials", group: "Library" },
  { label: "Summary", segment: "summary", group: "Library" },
  { label: "Knowledge map", segment: "knowledge-map", group: "Library" },
  { label: "Search", segment: "search", group: "Library" },
  { label: "Roadmap", segment: "roadmap", group: "Learn" },
  { label: "Practice", segment: "practice", group: "Learn" },
];

// The tab a path is on; a document's own page is part of Materials.
function tabOf(id: string, pathname: string): Tab {
  const base = `/environments/${id}`;
  return (
    TABS.find(({ segment }) => {
      if (!segment) return pathname === base;
      const href = `${base}/${segment}`;
      return pathname === href || pathname.startsWith(`${href}/`);
    }) ?? TABS[0]
  );
}

// The name of the tab a path is on, for the page's title.
export function tabLabel(id: string, pathname: string): string {
  return tabOf(id, pathname).label;
}

// "01", "02": a section's number in the contents.
export function tabNumber(id: string, pathname: string): string {
  return number(TABS.indexOf(tabOf(id, pathname)));
}

// A section's number by its name, for kickers like "03 / Summary".
export function sectionNumber(label: string): string {
  return number(TABS.findIndex((t) => t.label === label));
}

function number(index: number): string {
  return String(index + 1).padStart(2, "0");
}

export function EnvironmentTabs({ id, onNavigate }: { id: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const base = `/environments/${id}`;
  const current = tabOf(id, pathname);
  const groups = [
    { name: null, tabs: TABS.filter((t) => t.group === "start") },
    { name: "Library", tabs: TABS.filter((t) => t.group === "Library") },
    { name: "Learn", tabs: TABS.filter((t) => t.group === "Learn") },
  ];

  return (
    <nav
      aria-label="Environment sections"
      className="flex min-w-0 flex-1 flex-col tab:flex-row tab:items-center tab:gap-6 tab:overflow-x-auto desk:flex-col desk:items-stretch desk:gap-0"
    >
      {groups.map(({ name, tabs }) => (
        <div
          key={name ?? "start"}
          role={name ? "group" : undefined}
          aria-label={name ?? undefined}
          className="flex flex-col tab:flex-row tab:items-center tab:gap-6 tab:border-l tab:border-rule tab:pl-6 tab:first:border-0 tab:first:pl-0 desk:flex-col desk:items-stretch desk:gap-0 desk:border-0 desk:pl-0"
        >
          {name && (
            <p aria-hidden className="label pt-5 pb-1.5 text-ink-3 tab:hidden desk:block">
              {name}
            </p>
          )}
          <ol
            className={`flex flex-col tab:flex-row tab:gap-6 tab:border-0 desk:flex-col desk:gap-0 ${
              name ? "" : "border-t border-ink desk:border-t-0"
            }`}
          >
            {tabs.map((t) => {
              const href = t.segment ? `${base}/${t.segment}` : base;
              const isActive = t === current;
              return (
                <li key={t.label} className="border-b border-rule tab:border-0 desk:border-b">
                  <Link
                    href={href}
                    onClick={onNavigate}
                    aria-current={pathname === href ? "page" : isActive ? "location" : undefined}
                    // The row scrolls sideways on a tablet, which clips
                    // anything drawn outside it, so the focus ring is drawn
                    // inside.
                    className="group flex h-13 items-center gap-3.5 whitespace-nowrap focus-visible:-outline-offset-2 tab:h-11 tab:gap-2 desk:h-10 desk:gap-3"
                  >
                    <span
                      aria-hidden
                      className={`label flex h-[18px] w-[26px] shrink-0 items-center justify-center tab:hidden desk:flex ${
                        isActive ? "bg-accent text-on-accent" : "text-ink-3 group-hover:text-ink"
                      }`}
                    >
                      {number(TABS.indexOf(t))}
                    </span>
                    <span
                      className={`display text-[28px] tab:font-sans tab:text-sm tab:tracking-normal desk:text-[15px] ${
                        isActive
                          ? "tab:font-semibold tab:underline tab:decoration-accent tab:decoration-2 tab:underline-offset-[14px] desk:no-underline"
                          : "group-hover:underline group-hover:decoration-accent group-hover:underline-offset-4"
                      }`}
                    >
                      {t.label}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </div>
      ))}
    </nav>
  );
}

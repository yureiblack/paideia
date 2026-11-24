"use client";

// A link back to the page you came from, going where the browser's back
// button would: the nearest earlier page of this app in the tab's history,
// passing over moves within the current page (the guide's #step-2 and the
// like). It goes back rather than opening that page again, so the page is
// as it was left and the history does not grow. When there is no earlier
// page, because the tab was opened here, or the browser cannot say (it has
// no Navigation API), it is a plain link to `fallback`.

import Link from "next/link";
import { useSyncExternalStore, type MouseEvent } from "react";

// The part of the Navigation API used here. TypeScript's DOM types do not
// declare window.navigation yet.
type Entry = { key: string; index: number; url: string | null };
type Navigation = EventTarget & {
  currentEntry: Entry | null;
  entries(): Entry[];
  traverseTo(key: string): unknown;
};

function navigation(): Navigation | undefined {
  return (window as Window & { navigation?: Navigation }).navigation;
}

// A page is its address without the fragment.
function page(url: string | null): string | null {
  return url && url.split("#")[0];
}

// The nearest earlier entry on another page, by its key, or null.
function previousKey(): string | null {
  const nav = navigation();
  const current = nav?.currentEntry;
  if (!nav || !current) return null;
  const entries = nav.entries();
  for (let i = current.index - 1; i >= 0; i--) {
    if (entries[i].url && page(entries[i].url) !== page(current.url)) return entries[i].key;
  }
  return null;
}

// The current entry changes after a page has rendered, so the answer is
// asked again then.
function subscribe(onChange: () => void): () => void {
  const nav = navigation();
  nav?.addEventListener("currententrychange", onChange);
  return () => nav?.removeEventListener("currententrychange", onChange);
}

export function BackLink({
  fallback,
  fallbackLabel,
  className,
}: {
  fallback: string;
  fallbackLabel: string;
  className?: string;
}) {
  // The server cannot know the tab's history, so it renders the fallback.
  const key = useSyncExternalStore(subscribe, previousKey, () => null);
  const entry = key ? navigation()?.entries().find((e) => e.key === key) : undefined;

  if (!entry?.url) {
    return (
      <Link href={fallback} className={className}>
        <span aria-hidden>← </span>
        {fallbackLabel}
      </Link>
    );
  }

  const url = new URL(entry.url);
  const goBack = (event: MouseEvent<HTMLAnchorElement>) => {
    // A click meant for a new tab or window opens the page there instead.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigation()?.traverseTo(entry.key);
  };
  return (
    <Link href={`${url.pathname}${url.search}${url.hash}`} onClick={goBack} className={className}>
      <span aria-hidden>← </span>Back
    </Link>
  );
}

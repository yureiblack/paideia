"use client";

// The masthead across the top of every page: the wordmark, today's date,
// the guide, the health of the system and the theme.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { ApiStatus } from "@/components/api-status";
import { ThemeToggle } from "@/components/theme-toggle";

// Today's date in the reader's own time zone, so it is written in the
// browser; the server renders nothing there.
function Dateline() {
  const today = useSyncExternalStore(
    () => () => {},
    () =>
      new Date().toLocaleDateString("en-GB", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }),
    () => "",
  );
  return <p className="label hidden flex-1 text-center text-ink-3 tab:block">{today}</p>;
}

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="border-b border-ink bg-paper">
      <div className="mx-auto flex h-13 w-full max-w-[1440px] items-center gap-5 px-5 tab:h-16 tab:gap-6 tab:px-8">
        <Link href="/" className="display text-[26px] italic tracking-[-0.01em] tab:text-[30px]">
          Paideia
        </Link>
        <Dateline />
        <div className="ml-auto flex items-center gap-5 tab:ml-0 tab:gap-6">
          <Link
            href="/guide"
            aria-current={pathname === "/guide" ? "page" : undefined}
            className={`label flex min-h-11 items-center border-b-0 text-ink ${
              pathname === "/guide" ? "underline decoration-accent decoration-2 underline-offset-[5px]" : "underline decoration-ink decoration-1 underline-offset-[5px] hover:decoration-accent hover:decoration-2"
            }`}
          >
            Guide
          </Link>
          <ApiStatus />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

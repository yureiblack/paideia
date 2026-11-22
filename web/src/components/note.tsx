"use client";

// A note in the margin (decision record 28): what a place is for, shown the
// first time it is opened in this browser. It sits beside what it explains
// and nothing waits for it; Got it puts it away for good, and the guide
// keeps the same words and can show the notes again. An orange rule marks
// it, like a note in a printed book.

import Link from "next/link";
import type { ReactNode } from "react";

import { button } from "@/components/ui";
import { putNoteAway, useNoteShown, type NoteId } from "@/lib/local";

export function Note({
  id,
  title,
  guideStep,
  children,
  className = "",
}: {
  id: NoteId;
  title: string;
  // The guide's step that says more, as in /guide#step-3.
  guideStep?: number;
  children: ReactNode;
  className?: string;
}) {
  const shown = useNoteShown(id);
  if (!shown) return null;
  const headingId = `note-${id}`;
  return (
    <aside
      aria-labelledby={headingId}
      className={`flex max-w-[440px] flex-col gap-2.5 border-l-2 border-accent pl-4 ${className}`}
    >
      <h2 id={headingId} className="label">
        {title}
      </h2>
      <div className="text-[15px] leading-[1.55] text-ink-2">{children}</div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1">
        <button type="button" onClick={() => putNoteAway(id)} className={`${button.link} min-h-6`}>
          Got it
        </button>
        <Link
          href={guideStep ? `/guide#step-${guideStep}` : "/guide"}
          className="label text-ink-2 hover:text-ink hover:underline hover:decoration-accent"
        >
          More in the guide <span aria-hidden>→</span>
        </Link>
      </div>
    </aside>
  );
}

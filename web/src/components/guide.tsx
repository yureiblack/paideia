"use client";

// The guide (decision record 28): how Paideia works, in five steps, one
// click away in the masthead. Each step says what to do and where, beside
// an excerpt of the interface drawn with the same type and rules. The
// excerpts are pictures, not controls: they are hidden from assistive
// technology, which hears the step's words instead, and nothing in them
// can be pressed. The notes that explain each place the first time it is
// opened say the same things; the guide can show them again.

import Link from "next/link";
import type { ReactNode } from "react";

import { button, Mark } from "@/components/ui";
import { NOTES, showNotesAgain, useNotesPutAway } from "@/lib/local";

type Step = { id: number; title: string; text: string; where: string; excerpt: ReactNode };

const STEPS: Step[] = [
  {
    id: 1,
    title: "Organise your learning",
    text: "An environment holds one subject: its PDFs, the summaries written from them, the concepts found in them, its roadmap and your practice. Nothing is shared between environments, so search and practice stay on the subject.",
    where: "Home → New environment",
    excerpt: (
      <div className="flex items-start gap-6">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="display text-[30px] leading-none tracking-[-0.02em]">Linear Algebra</p>
          <p className="text-[14px] leading-[1.45] text-ink-2">Lecture notes and problem sheets for MATH 201.</p>
        </div>
        <p className="text-[14px] leading-[1.4]">Nothing planned today</p>
        <span className="label border-b border-ink pb-0.5">Open →</span>
      </div>
    ),
  },
  {
    id: 2,
    title: "Add your study materials",
    text: "Upload PDFs of up to 50 MB: lecture notes, chapters, problem sheets. Each is read page by page as soon as it arrives, and you can keep working meanwhile. When a file changes, upload it as a new version and Paideia says what changed.",
    where: "Materials → Upload PDF",
    excerpt: (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-rule pb-3.5">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="display text-[26px] leading-none tracking-[-0.015em]">Synchronization.pdf</p>
            <p className="text-[13px] leading-[1.4] text-ink-2">478 KB · added 10 Nov</p>
          </div>
          <p className="label">Reading · page 2 of 4</p>
        </div>
        <span className={`${button.primary} w-fit`}>Upload PDF [+]</span>
      </div>
    ),
  },
  {
    id: 3,
    title: "Build your knowledge base",
    text: "Each page is split into passages. Search finds them by your words and by their meaning, and shows each one inside its page. The concepts in the passages are found too, with how they build on one another: that is the knowledge map.",
    where: "Search · Knowledge map",
    excerpt: (
      <div className="flex flex-col gap-2.5">
        <p className="label text-ink-2">Scheduling.pdf · p. 2 · Round robin</p>
        <p className="text-[15px] leading-[1.6]">
          Round robin scheduling assigns each ready task a fixed time quantum. When the quantum
          expires, the running task is preempted and moved to the back of the ready queue.
        </p>
        <p className="flex items-baseline gap-6 pt-2">
          <span className="label w-28 shrink-0 text-ink-2">← Builds on</span>
          <span className="display text-[22px] leading-none">Exponential Average</span>
        </p>
      </div>
    ),
  },
  {
    id: 4,
    title: "Learn from your materials",
    text: "Summaries say what a document, or the whole environment, covers; each point cites its page. The roadmap puts the concepts in stages, what a concept builds on first. Practice is written from your passages, and every answer shows the page it comes from. Linear algebra also gets exercises with worked solutions.",
    where: "Summary · Roadmap · Practice",
    excerpt: (
      <div className="flex flex-col gap-4">
        <p className="flex items-start gap-4 border-b border-rule pb-3.5">
          <span className="label text-ink-3">05</span>
          <span className="flex-1 text-[15px] leading-[1.6]">
            Deadlock needs four conditions at once: mutual exclusion, hold and wait, no preemption,
            circular wait.
          </span>
          <span className="label text-ink-2">6</span>
        </p>
        <p className="flex items-center gap-4 bg-ink px-3.5 py-3 text-paper">
          <span className="label flex size-[26px] shrink-0 items-center justify-center border border-paper">B</span>
          <span className="flex-1 text-[15px] leading-[1.4]">It is preempted and moved to the back of the ready queue.</span>
          <span className="label">✓ Answer</span>
        </p>
      </div>
    ),
  },
  {
    id: 5,
    title: "Return and continue",
    text: "Home opens on where you left off: the next thing to practise, and the document you were reading. Each environment's overview has today's plan: what is due for review, what you missed, and the next stage. A concept you recall comes back further apart.",
    where: "Home · Overview",
    excerpt: (
      <div className="flex items-start gap-4">
        <p className="label flex w-28 shrink-0 items-center gap-1.5 pt-1.5">
          <Mark />
          Strengthen
        </p>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="display text-[22px] leading-[1.05]">Round Robin Scheduling, Dispatcher and Time Quantum</p>
          <p className="text-[14px] leading-[1.4] text-ink-2">Missed on the last answer.</p>
        </div>
        <span className={button.primary}>Start →</span>
      </div>
    ),
  },
];

export function Guide() {
  return (
    <div className="flex flex-1 flex-col desk:flex-row">
      <aside className="flex flex-col gap-7 border-b border-ink px-5 pt-5 pb-6 tab:px-8 desk:sticky desk:top-0 desk:h-dvh desk:w-66 desk:shrink-0 desk:border-r desk:border-b-0 desk:border-r-rule desk:px-6 desk:py-7">
        <Link href="/" className="label w-fit text-ink-2 hover:text-ink">
          <span aria-hidden>← </span>Your environments
        </Link>
        <div className="flex flex-col gap-2">
          <p className="label text-ink-3">Guide</p>
          <p className="display text-[30px] leading-none tracking-[-0.015em]">How Paideia works</p>
          <p className="text-[13px] leading-[1.4] text-ink-2">Five steps · about two minutes</p>
        </div>
        <nav aria-label="Steps" className="hidden desk:block">
          <ol>
            {STEPS.map((s) => (
              <li key={s.id} className="border-b border-rule">
                <a href={`#step-${s.id}`} className="group flex min-h-10 items-center gap-3 py-1.5">
                  <span aria-hidden className="label flex h-[18px] w-[26px] shrink-0 items-center justify-center text-ink-3 group-hover:text-ink">
                    {String(s.id).padStart(2, "0")}
                  </span>
                  <span className="text-[15px] leading-[1.3] group-hover:underline group-hover:decoration-accent">
                    {s.title}
                  </span>
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <NotesAgain />
      </aside>
      <article aria-labelledby="guide-heading" className="flex min-w-0 flex-1 flex-col px-5 pt-6 pb-16 tab:px-8 tab:pt-8 desk:px-12 desk:pt-9">
        <div className="flex flex-col gap-4 pb-10">
          <p className="label">Guide / How Paideia works</p>
          <h1 id="guide-heading" className="display text-[48px] leading-[0.92] tracking-[-0.03em] tab:text-[64px] desk:text-[76px]">
            Organise, explore, learn.
          </h1>
          <p className="max-w-[640px] text-[18px] leading-[1.5] text-ink-2 tab:text-[20px]">
            Paideia turns a subject&apos;s PDFs into something you can search, read in summary and
            practise. These five steps are the whole of it; every place in the app has a short note
            the first time you open it.
          </p>
        </div>
        {STEPS.map((s) => (
          <section
            key={s.id}
            id={`step-${s.id}`}
            aria-labelledby={`step-${s.id}-heading`}
            className="flex scroll-mt-6 flex-col gap-6 border-t border-ink pt-4 pb-11 desk:flex-row desk:gap-12"
          >
            <div className="flex flex-col gap-3.5 desk:w-[420px] desk:shrink-0">
              <p className="label">Step {String(s.id).padStart(2, "0")} / 05</p>
              <h2 id={`step-${s.id}-heading`} className="display text-[34px] leading-none tracking-[-0.02em] tab:text-[40px]">
                {s.title}
              </h2>
              <p className="max-w-[640px] text-[17px] leading-[1.65]">{s.text}</p>
              <p className="flex items-baseline gap-2.5 pt-1">
                <span className="label text-ink-3">Where</span>
                <span className="text-[14px] leading-[1.4] text-ink-2">{s.where}</span>
              </p>
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-2.5">
              <p aria-hidden className="label text-ink-3">
                In the app
              </p>
              <div aria-hidden inert className="pointer-events-none border border-rule px-5 py-4.5 select-none">
                {s.excerpt}
              </div>
            </div>
          </section>
        ))}
        <div className="flex flex-col gap-4 border-t border-ink pt-4 tab:flex-row tab:items-center tab:gap-8">
          <p className="max-w-[640px] flex-1 text-[16px] leading-[1.5] text-ink-2">
            That is all of it. Each place explains itself the first time you open it, and this guide
            stays one click away in the masthead.
          </p>
          <Link href="/" className={`${button.primary} w-fit`}>
            Go to your environments <span aria-hidden>→</span>
          </Link>
        </div>
      </article>
    </div>
  );
}

// How many of the notes are put away, and a way to show them again.
function NotesAgain() {
  const away = useNotesPutAway();
  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-3 desk:mt-auto">
      <p className="label">Notes in the app</p>
      <p className="text-[13px] leading-[1.45] text-ink-2">
        {away === 0
          ? "A short note explains each place the first time you open it."
          : `You have put away ${away} of the ${NOTES.length} notes that explain a place the first time you open it.`}
      </p>
      {away > 0 && (
        <button type="button" onClick={showNotesAgain} className={`${button.link} w-fit`}>
          Show them again
        </button>
      )}
    </div>
  );
}

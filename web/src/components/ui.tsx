"use client";

// The small pieces every page is built from, in the Broadsheet design
// (decision record 25): buttons, the orange mark, section heads, headlines.
// Structure comes from type and hairline rules, not boxes; hover is an
// instant swap with no easing.

import { useEffect, useLayoutEffect, type ReactNode, type RefObject } from "react";

// Button styles. Primary is an ink block that turns orange under the
// pointer; outline is the secondary action; link is an underlined label;
// danger is for the one action that deletes.
export const button = {
  primary:
    "label inline-flex items-center justify-center gap-2 bg-ink px-4 py-[11px] font-medium text-paper hover:bg-accent hover:text-on-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-ink disabled:hover:text-paper",
  outline:
    "label inline-flex items-center justify-center gap-2 border border-ink px-[15px] py-[10px] font-medium text-ink hover:border-accent hover:bg-accent hover:text-on-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-ink disabled:hover:bg-transparent disabled:hover:text-ink",
  link: "label inline-flex items-center gap-1.5 border-b border-ink pb-0.5 text-left text-ink hover:border-b-2 hover:border-accent hover:pb-px disabled:cursor-not-allowed disabled:opacity-40",
  danger:
    "label inline-flex items-center justify-center gap-2 bg-accent px-4 py-[11px] font-medium text-on-accent hover:bg-ink hover:text-paper disabled:cursor-not-allowed disabled:opacity-40",
} as const;

// A text link in running copy: ink, a hairline underneath, orange on hover.
export const textLink =
  "underline decoration-rule decoration-1 underline-offset-[3px] hover:decoration-accent hover:decoration-2";

// The orange square: something needs attention (a missed answer, a failed
// job, a problem). Always beside words that say what it means.
export function Mark() {
  return <span aria-hidden className="inline-block size-[7px] shrink-0 bg-accent" />;
}

// A section's head: an ink rule, a numbered uppercase label, and an
// optional note or link on the right.
export function SectionHead({
  id,
  children,
  right,
  as: Heading = "h2",
}: {
  id?: string;
  children: ReactNode;
  right?: ReactNode;
  as?: "h2" | "h3";
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-ink pt-2.5 pb-3.5">
      <Heading id={id} className="label">
        {children}
      </Heading>
      {right && <div className="label text-ink-3">{right}</div>}
    </div>
  );
}

// A page's opening: a small kicker, the headline sentence, and a short
// standfirst beside it on wide screens and under it on narrow ones.
export function Opening({
  kicker,
  headline,
  headlineId,
  aside,
  below,
}: {
  kicker: ReactNode;
  headline: ReactNode;
  headlineId?: string;
  aside?: ReactNode;
  // A line under the headline, such as the figures at a glance.
  below?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 desk:flex-row desk:items-end desk:gap-10">
      <div className="flex min-w-0 flex-1 flex-col gap-3.5">
        <p className="label max-tab:sr-only">{kicker}</p>
        <p
          id={headlineId}
          className="display text-[44px] leading-[0.92] tracking-[-0.03em] text-balance tab:text-[60px] desk:text-[76px]"
        >
          {headline}
        </p>
        {below}
      </div>
      {aside && <div className="flex flex-col gap-3 desk:w-60 desk:shrink-0 desk:pb-1.5">{aside}</div>}
    </div>
  );
}

// A standfirst: one italic sentence under or beside a headline.
export function Standfirst({ children }: { children: ReactNode }) {
  return <p className="display text-lg leading-[1.2] text-ink-2 italic">{children}</p>;
}

// Closes a popover on Escape or a click outside it. Escape returns focus to
// whatever opened it.
export function useDismiss(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  close: () => void,
  trigger?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
        trigger?.current?.focus();
      }
    }
    function onPointer(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [ref, open, close, trigger]);
}

// A popover is aligned to its button, so on a narrow screen one whose
// button sits near the left edge would open off it. Once open it is moved
// sideways just enough to stay inside the page's 20px gutters; its class
// keeps it no wider than the window allows (POPOVER_WIDTH).
const GUTTER = 20;
export const POPOVER_WIDTH = "max-w-[calc(100vw-2.5rem)]";

export function useInsideWindow(ref: RefObject<HTMLElement | null>, open: boolean) {
  useLayoutEffect(() => {
    const element = ref.current;
    if (!open || !element) return;
    function place() {
      if (!element) return;
      element.style.translate = "";
      const box = element.getBoundingClientRect();
      // Not laid out (as in tests): nothing to measure.
      if (box.width === 0) return;
      const width = document.documentElement.clientWidth;
      const shift =
        box.left < GUTTER ? GUTTER - box.left : box.right > width - GUTTER ? width - GUTTER - box.right : 0;
      if (shift) element.style.translate = `${Math.round(shift)}px 0`;
    }
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [ref, open]);
}

// "[+]" and "[–]": the typographic sign that something opens in place.
export function OpenSign({ open }: { open: boolean }) {
  return <span aria-hidden>{open ? "[–]" : "[+]"}</span>;
}

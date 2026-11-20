// Text that may hold maths, shown with its formulas typeset (decision record
// 24). Used wherever passages or what the model wrote are shown.
//
// KaTeX renders each formula, with its trust option off, so no formula can
// add a link, an image or HTML of its own, and with limits on sizes and macro
// expansion. A formula KaTeX cannot render is shown as its LaTeX source,
// marked, instead of breaking the page. Rendered formulas are cached, since
// sections that poll render the same text again and again.

import katex from "katex";
import { Fragment } from "react";

import { split } from "@/lib/maths";

const OPTIONS = {
  throwOnError: true,
  trust: false,
  strict: "ignore",
  maxSize: 10, // ems, for commands that size things, such as \rule
  maxExpand: 500,
  output: "htmlAndMathml", // MathML is what screen readers read
} as const;

const CACHE_SIZE = 1000;
const cache = new Map<string, string | null>();

function typeset(latex: string, displayMode: boolean): string | null {
  const key = `${displayMode ? "d" : "i"}${latex}`;
  if (!cache.has(key)) {
    let html: string | null;
    try {
      html = katex.renderToString(latex, { ...OPTIONS, displayMode });
    } catch {
      html = null;
    }
    if (cache.size >= CACHE_SIZE) cache.clear();
    cache.set(key, html);
  }
  return cache.get(key) ?? null;
}

// Nothing, for no text, as React shows null.
export function MathsText({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <>
      {split(text).map((segment) => {
        if (segment.kind === "prose") {
          return <Fragment key={segment.start}>{segment.body}</Fragment>;
        }
        const html = typeset(segment.body, segment.kind === "display");
        if (html === null) {
          return (
            <code
              key={segment.start}
              title="This formula could not be shown, so its LaTeX source is shown instead."
              className="rounded bg-zinc-100 px-1 font-mono text-[0.9em] dark:bg-zinc-800"
            >
              {text.slice(segment.start, segment.end)}
            </code>
          );
        }
        return (
          <span
            key={segment.start}
            // KaTeX escapes everything it is given, and with trust off it
            // writes no links, images or HTML from the formula.
            dangerouslySetInnerHTML={{ __html: html }}
          />
        );
      })}
    </>
  );
}

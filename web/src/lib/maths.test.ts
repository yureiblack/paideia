// Splitting text into prose and formulas, as app/maths.py does on the
// backend (decision record 24), and keeping a highlight from cutting a
// formula in two.

import { describe, expect, it } from "vitest";

import { split, widen } from "./maths";

const kinds = (text: string) =>
  split(text).map((s) => [s.kind, text.slice(s.start, s.end)]);

describe("split", () => {
  it("finds inline and displayed formulas between their delimiters", () => {
    expect(kinds(String.raw`Let \(A\) be \[\det A = 1\] here.`)).toEqual([
      ["prose", "Let "],
      ["inline", String.raw`\(A\)`],
      ["prose", " be "],
      ["display", String.raw`\[\det A = 1\]`],
      ["prose", " here."],
    ]);
  });

  it("gives each formula its LaTeX without the delimiters", () => {
    expect(split(String.raw`\(\lambda^2\)`)[0].body).toBe(String.raw`\lambda^2`);
  });

  it("does not read a row break as a delimiter", () => {
    const text = String.raw`\(\begin{pmatrix} 1 \\ 2 \end{pmatrix}\)`;
    expect(kinds(text)).toEqual([["inline", text]]);
  });

  it("leaves dollar signs alone: a price is never maths", () => {
    expect(kinds("It costs $5, and $x$ is not maths here.")).toEqual([
      ["prose", "It costs $5, and $x$ is not maths here."],
    ]);
  });

  it("shows a formula that is never closed as prose", () => {
    expect(kinds(String.raw`Half \(x and more`)).toEqual([
      ["prose", String.raw`Half \(x and more`],
    ]);
  });

  it("reads an opening inside a formula as part of it, for KaTeX to refuse", () => {
    // The backend calls this a formula opening inside another.
    const text = String.raw`\(x and \(y\)`;
    expect(kinds(text)).toEqual([["inline", text]]);
  });

  it("does not close a formula with the other kind of delimiter", () => {
    expect(kinds(String.raw`\(a\] b\)`)).toEqual([["inline", String.raw`\(a\] b\)`]]);
  });
});

describe("widen", () => {
  const text = String.raw`Before \(x + y\) after`;
  // "Before " is 7 characters; the formula runs from 7 to 16.

  it("moves a highlight that starts or ends inside a formula to its edge", () => {
    expect(widen(text, 10, 20)).toEqual([7, 20]);
    expect(widen(text, 0, 12)).toEqual([0, 16]);
  });

  it("leaves a highlight that cuts no formula as it is", () => {
    expect(widen(text, 0, 7)).toEqual([0, 7]);
    expect(widen(text, 7, 16)).toEqual([7, 16]);
    expect(widen("No maths.", 3, 5)).toEqual([3, 5]);
  });
});

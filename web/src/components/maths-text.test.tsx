// Text with formulas, typeset by KaTeX (decision record 24): formulas render,
// one that cannot render shows its source instead of breaking the page, a
// price stays prose, and no formula can add a link or HTML of its own.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MathsText } from "./maths-text";

function shown(text: string | null) {
  return render(
    <p data-testid="text">
      <MathsText text={text} />
    </p>,
  ).getByTestId("text");
}

describe("MathsText", () => {
  it("typesets inline and displayed formulas, and keeps the prose", () => {
    const p = shown(String.raw`Solve \(\det(A - \lambda I) = 0\) for \[\lambda\].`);

    expect(p.querySelectorAll(".katex")).toHaveLength(2);
    expect(p.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(p.textContent).toMatch(/^Solve /);
    expect(p.textContent).toMatch(/ for .*\.$/);
    // The MathML KaTeX writes alongside keeps the LaTeX for screen readers.
    expect(p.querySelector("annotation")?.textContent).toBe(
      String.raw`\det(A - \lambda I) = 0`,
    );
  });

  it("typesets a matrix", () => {
    const p = shown(String.raw`\(\begin{pmatrix} 5 & 2 \\ 2 & 1 \end{pmatrix}\)`);
    expect(p.querySelector(".katex .mtable")).not.toBeNull();
  });

  it("shows a formula it cannot render as its source", () => {
    const p = shown(String.raw`A \(\frac{1}{2\) half.`);

    expect(p.querySelector(".katex")).toBeNull();
    const source = screen.getByTitle(/could not be shown/);
    expect(source.tagName).toBe("CODE");
    expect(source.textContent).toBe(String.raw`\(\frac{1}{2\)`);
    expect(p.textContent).toBe(String.raw`A \(\frac{1}{2\) half.`);
  });

  it("leaves prices and plain text exactly as they were", () => {
    const text = "It costs $5 and $10, and $x$ stays as written.";
    const p = shown(text);

    expect(p.innerHTML).toBe(text);
  });

  it("writes no link, image or HTML from a formula", () => {
    const p = shown(
      String.raw`\(\href{javascript:alert(1)}{x}\) \(\htmlClass{evil}{y}\) \(\includegraphics{a.png}\)`,
    );

    expect(p.querySelector("a, img, .evil, [href], [src]")).toBeNull();
    // The commands show as red text; their LaTeX is kept only as the
    // MathML annotation's escaped text.
    expect(p.querySelectorAll(".katex")).toHaveLength(3);
  });

  it("shows nothing for no text", () => {
    expect(shown(null).innerHTML).toBe("");
  });
});

// A citation opened in its page (decision record 07), with maths (decision
// record 24): the passage is marked, and a mark that would start or end inside
// a formula takes in the whole formula, which is typeset, never cut in two.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourcePanel } from "@/components/source-panel";
import type { SourcePreview } from "@/lib/types";
import { fakeApi } from "@/test/network";

function open(content: string, start: number, end: number) {
  const preview: SourcePreview = {
    citation: {
      environment_id: "e1",
      document_id: "d1",
      document_version: "v1",
      filename: "Lecture 5.pdf",
      chunk_id: "c1",
      page_start: 3,
      page_end: 3,
      heading: null,
      excerpt: content.slice(start, end),
      figure_id: null,
    },
    pages: [{ page_number: 3, content, highlight_start: start, highlight_end: end }],
  };
  fakeApi([{ method: "GET", path: "/api/chunks/c1/preview", answer: { body: preview } }]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SourcePanel environmentId="e1" chunkId="c1" />
    </QueryClientProvider>,
  );
}

describe("SourcePanel", () => {
  it("marks the passage, with a formula the mark would cut taken in whole", async () => {
    // The passage starts inside the formula, at "+ y".
    const content = String.raw`Before \(x + y\) after.`;
    open(content, content.indexOf("+"), content.length);

    const page = await screen.findByRole("region", { name: "Page 3" });
    const mark = page.querySelector("mark")!;
    expect(mark.querySelector(".katex annotation")?.textContent).toBe("x + y");
    expect(mark.textContent).toMatch(/after\.$/);
    expect(page.textContent).toMatch(/^Page 3Before /);
    // No LaTeX is left showing as text.
    expect(page.querySelector("code")).toBeNull();
  });

  it("marks plain text exactly where the passage is", async () => {
    open("One. Two. Three.", 5, 9);

    const page = await screen.findByRole("region", { name: "Page 3" });
    expect(page.querySelector("mark")?.textContent).toBe("Two.");
  });
});

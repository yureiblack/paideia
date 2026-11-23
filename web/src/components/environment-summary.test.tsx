// The environment's summary as an article with notes (decision record 28):
// every passage the points cite is numbered once, in the order first cited;
// a number beside a point, or a note in the margin, opens the passage under
// its point. Before there is a summary, the page says what comes.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EnvironmentSummary } from "@/components/environment-summary";
import type { Citation, EnvironmentSummaryState, SourcePreview } from "@/lib/types";
import { fakeApi } from "@/test/network";

function cite(chunk: string, filename: string, page: number): Citation {
  return {
    environment_id: "e1",
    document_id: filename,
    document_version: `${filename}-version`,
    filename,
    chunk_id: chunk,
    page_start: page,
    page_end: page,
    heading: null,
    excerpt: `Passage ${chunk}.`,
    figure_id: null,
  };
}

const week1 = cite("k1", "Week 1.pdf", 2);
const week2 = cite("k2", "Week 2.pdf", 1);
const week2Later = cite("k3", "Week 2.pdf", 4);

const written: EnvironmentSummaryState = {
  state: "up_to_date",
  waiting_for: 0,
  error: null,
  not_included: [],
  earlier_versions: 0,
  summary: {
    id: "s1",
    environment_id: "e1",
    status: "ready",
    error: null,
    overview: "Threads and how they are scheduled.",
    key_points: [
      { text: "Threads share their process's memory.", citations: [week1, week2] },
      { text: "Round robin gives each a time quantum.", citations: [week2, week2Later] },
    ],
    model: "a local model",
    prompt_versions: ["p1"],
    source_version: "v1",
    based_on: [
      { document_id: "d1", filename: "Week 1.pdf", document_version: "aaaa1111bbbb", summary_id: "x" },
      { document_id: "d2", filename: "Week 2.pdf", document_version: "cccc2222dddd", summary_id: "y" },
    ],
    seconds: 4.2,
    current: true,
    created_at: "2026-11-14T15:57:00Z",
    updated_at: "2026-11-14T15:57:00Z",
  },
};

function preview(citation: Citation): SourcePreview {
  return {
    citation,
    pages: [
      {
        page_number: citation.page_start,
        content: citation.excerpt,
        highlight_start: 0,
        highlight_end: citation.excerpt.length,
      },
    ],
  };
}

function show(state: EnvironmentSummaryState, documents: { status: string }[] = []) {
  fakeApi([
    { method: "GET", path: "/api/environments/e1/summary", answer: { body: state } },
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: documents } },
    ...[week1, week2, week2Later].map((c) => ({
      method: "GET",
      path: `/api/chunks/${c.chunk_id}/preview`,
      answer: { body: preview(c) },
    })),
  ]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EnvironmentSummary environmentId="e1" />
    </QueryClientProvider>,
  );
}

describe("EnvironmentSummary", () => {
  it("numbers each cited passage once and lists the notes in the margin", async () => {
    show(written);

    expect(await screen.findByText(/^Based on 2 documents · updated /)).toBeInTheDocument();
    const summary = screen.getByRole("region", { name: "Environment summary" });
    expect(summary).toHaveTextContent("Threads and how they are scheduled.");

    // Week 2.pdf, p. 1 is cited by both points, and is note 2 in both.
    const numbered = within(summary).getAllByRole("button", { name: /^Note \d/ });
    expect(numbered.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Note 1, Week 1.pdf · p. 2",
      "Note 2, Week 2.pdf · p. 1",
      "Note 2, Week 2.pdf · p. 1",
      "Note 3, Week 2.pdf · p. 4",
    ]);
    const notes = within(summary).getByRole("region", { name: "Notes" });
    expect(within(notes).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Week 1.pdf, p. 2",
      "Week 2.pdf, p. 1",
      "Week 2.pdf, p. 4",
    ]);
  });

  it("opens a note's passage under its point, from the point or from the margin", async () => {
    show(written);

    const note = await screen.findByRole("button", { name: "Note 3, Week 2.pdf · p. 4" });
    await userEvent.click(note);
    const page = await screen.findByRole("region", { name: "Week 2.pdf, Page 4" });
    expect(page.querySelector("mark")).toHaveTextContent("Passage k3.");
    expect(note).toHaveAttribute("aria-expanded", "true");

    // From the margin: one passage open at a time.
    await userEvent.click(screen.getByRole("button", { name: "Week 1.pdf, p. 2" }));
    expect(await screen.findByRole("region", { name: "Week 1.pdf, Page 2" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Week 2.pdf, Page 4" })).toBeNull();
  });

  it("keeps how it was written and its sources folded until asked for", async () => {
    show(written);

    const how = await screen.findByRole("button", { name: "How this was written" });
    expect(screen.queryByText(/Written by a local model/)).toBeNull();
    await userEvent.click(how);
    expect(screen.getByText(/Written by a local model/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sources and versions" }));
    expect(screen.getByText("aaaa1111")).toBeInTheDocument();
  });

  it("says the summary comes after the reading while documents are read", async () => {
    show(
      { ...written, state: "waiting", waiting_for: 1, summary: null },
      [{ status: "ready" }, { status: "ready" }, { status: "processing" }],
    );

    expect(await screen.findByText("The summary comes after the reading.")).toBeInTheDocument();
    expect(await screen.findByText(/1 of 3 documents is still being read\./)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the materials" })).toHaveAttribute(
      "href",
      "/environments/e1/materials",
    );
  });
});

// Offering to read a document's figures (decision record 29), on the Figures
// tab of its page: never unasked, with how many figures were found and on how
// many pages, a range, and how long it should take; figures already read, or
// kept as the PDF had them, are not offered again, and say why they were kept.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FiguresPanel } from "@/components/figure-reading";
import type { Document, FiguresOverview } from "@/lib/types";
import { fakeApi } from "@/test/network";

const document: Document = {
  id: "d1",
  environment_id: "e1",
  filename: "Data.pdf",
  size_bytes: 4_500_000,
  sha256: "a".repeat(64),
  status: "ready",
  error: null,
  page_count: 10,
  pages_with_text: 10,
  pages_ocr: 0,
  repaired: false,
  created_at: "2026-11-21T09:00:00Z",
  updated_at: "2026-11-21T09:00:00Z",
};

const overview: FiguresOverview = {
  figures: [
    { key: "2:a", page: 2, caption: "Figure 2.1 The data pipeline" },
    { key: "2:b", page: 2, caption: "Figure 2.2 Stages of cleaning" },
    { key: "3:a", page: 3, caption: "Table 3.1 Sales by year" },
    { key: "5:a", page: 5, caption: "Figure 5.1 A scatter plot" },
    { key: "9:a", page: 9, caption: null },
  ],
  read: ["3:a"],
  waiting: [],
  kept: [
    {
      key: "5:a",
      page: 5,
      caption: "Figure 5.1 A scatter plot",
      reason: "It gives numbers the figure does not have: 42.",
    },
  ],
  seconds_per_figure: 60,
};

function open(figures: FiguresOverview, started: { status?: number; body?: unknown } = {}) {
  const sent = fakeApi([
    { method: "GET", path: "/api/documents/d1/figures", answer: { body: figures } },
    {
      method: "POST",
      path: "/api/documents/d1/figures",
      answer: { status: 202, body: { id: "j1" }, ...started },
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FiguresPanel document={document} environmentId="e1" />
    </QueryClientProvider>,
  );
  return { sent };
}

describe("FiguresPanel", () => {
  it("offers the figures not read yet, with how long they take", async () => {
    open(overview);
    await screen.findByRole("spinbutton", { name: "From page" });

    // Figures 2:a, 2:b and 9:a: 3:a was read, 5:a keeps the PDF's own text.
    expect(screen.getByRole("status")).toHaveTextContent("3 figures to read · about 3 minutes");
    expect(screen.getByText(/5 figures were found on 4 pages\./)).toBeInTheDocument();
    expect(screen.getByText(/the description cannot be, so it is marked as the model's/)).toBeInTheDocument();
    expect(screen.getByText(/^1 figure read/)).toBeInTheDocument();
  });

  it("counts no time for figures a cancelled reading already read", async () => {
    open({ ...overview, waiting: ["9:a"] });
    await screen.findByRole("spinbutton", { name: "From page" });

    expect(screen.getByRole("status")).toHaveTextContent("3 figures to read · about 2 minutes");
  });

  it("reads the range chosen, then says the reading has started", async () => {
    const { sent } = open(overview);
    const to = await screen.findByRole("spinbutton", { name: "To page" });

    await userEvent.clear(to);
    await userEvent.type(to, "2");
    expect(screen.getByRole("status")).toHaveTextContent("2 figures to read · about 2 minutes");
    await userEvent.click(screen.getByRole("button", { name: "Read the figures" }));

    expect(sent.find((request) => request.method === "POST")).toMatchObject({
      path: "/api/documents/d1/figures",
      body: { first_page: 1, last_page: 2 },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Reading 2 figures, about 2 minutes.",
    );
    expect(screen.queryByRole("button", { name: "Read the figures" })).toBeNull();
    expect(screen.getByRole("button", { name: "Choose other pages" })).toBeInTheDocument();
  });

  it("offers nothing to read where every figure has been read", async () => {
    open({ ...overview, figures: overview.figures.filter((f) => ["3:a", "5:a"].includes(f.key)) });
    await screen.findByRole("spinbutton", { name: "From page" });

    expect(screen.getByRole("status")).toHaveTextContent("Every figure here has been read.");
    expect(screen.getByRole("button", { name: "Read the figures" })).toBeDisabled();
  });

  it("says why a figure keeps the PDF's own text", async () => {
    open({
      ...overview,
      kept: [
        ...overview.kept,
        { key: "9:a", page: 9, caption: null, reason: "Its words are not in the figure." },
      ],
    });

    await userEvent.click(await screen.findByRole("button", { name: /2 keep the PDF's own text/ }));

    const kept = screen.getByRole("list", { name: "Figures that keep the PDF's own text" });
    expect(kept).toHaveTextContent(
      "Figure 5.1 A scatter plot · page 5It gives numbers the figure does not have: 42.",
    );
    expect(kept).toHaveTextContent("A figure on page 9Its words are not in the figure.");
  });

  it("shows why a reading could not start", async () => {
    open(overview, {
      status: 409,
      body: { detail: "The figures of these pages have been read already." },
    });

    await userEvent.click(await screen.findByRole("button", { name: "Read the figures" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The figures of these pages have been read already.",
    );
  });

  it("says so when the document has no figures", async () => {
    open({ figures: [], read: [], waiting: [], kept: [], seconds_per_figure: 20 });

    expect(
      await screen.findByText(/Paideia finds no figures in “Data.pdf”: no drawings or pictures/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Read the figures" })).toBeNull();
  });
});

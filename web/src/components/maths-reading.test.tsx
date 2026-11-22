// Offering to read a document's maths (decision record 26), on the Maths tab
// of its page: never unasked, with how many pages hold maths, a range, and how
// long it should take; pages already read, or kept as the PDF had them, are
// not offered again.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { duration, MathsPanel } from "@/components/maths-reading";
import type { Document, MathsOverview } from "@/lib/types";
import { fakeApi } from "@/test/network";

const document: Document = {
  id: "d1",
  environment_id: "e1",
  filename: "Linear algebra.pdf",
  size_bytes: 4_500_000,
  sha256: "a".repeat(64),
  status: "ready",
  error: null,
  page_count: 10,
  pages_with_text: 10,
  repaired: false,
  created_at: "2026-11-21T09:00:00Z",
  updated_at: "2026-11-21T09:00:00Z",
};

const overview: MathsOverview = {
  maths_pages: [2, 3, 5, 9],
  read: [3],
  waiting: [],
  kept_text: [{ page: 5, reason: "Its digits differ from the PDF's text: 1 missing (2)." }],
  seconds_per_page: 60,
};

function open(maths: MathsOverview, started: { status?: number; body?: unknown } = {}) {
  const sent = fakeApi([
    { method: "GET", path: "/api/documents/d1/maths", answer: { body: maths } },
    {
      method: "POST",
      path: "/api/documents/d1/maths",
      answer: { status: 202, body: { id: "j1" }, ...started },
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MathsPanel document={document} environmentId="e1" />
    </QueryClientProvider>,
  );
  return { sent };
}

describe("duration", () => {
  it("says how long in words a learner can plan with", () => {
    expect(duration(20)).toBe("under a minute");
    expect(duration(65)).toBe("about a minute");
    expect(duration(9 * 60)).toBe("about 9 minutes");
    expect(duration(2 * 3600 + 10 * 60)).toBe("about 2 hours 10 minutes");
    expect(duration(3600)).toBe("about 1 hour");
  });
});

describe("MathsPanel", () => {
  it("offers the pages with maths not read yet, with how long they take", async () => {
    open(overview);
    await screen.findByRole("spinbutton", { name: "From page" });

    // Pages 2 and 9: 3 was read, 5 keeps the PDF's own text.
    expect(screen.getByRole("status")).toHaveTextContent(
      "2 pages to read · about 2 minutes",
    );
    expect(screen.getByText(/4 of 10 pages set maths/)).toBeInTheDocument();
  });

  it("counts no time for pages a cancelled reading already read", async () => {
    open({ ...overview, waiting: [9] });
    await screen.findByRole("spinbutton", { name: "From page" });

    expect(screen.getByRole("status")).toHaveTextContent("2 pages to read · about a minute");
  });

  it("reads the range chosen, then says the reading has started", async () => {
    const { sent } = open(overview);
    const to = await screen.findByRole("spinbutton", { name: "To page" });

    await userEvent.clear(to);
    await userEvent.type(to, "4");
    expect(screen.getByRole("status")).toHaveTextContent("1 page to read · about a minute");
    await userEvent.click(screen.getByRole("button", { name: "Read the maths" }));

    expect(sent.find((request) => request.method === "POST")).toMatchObject({
      path: "/api/documents/d1/maths",
      body: { first_page: 1, last_page: 4 },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Reading the maths of 1 page, about a minute.",
    );
    expect(screen.queryByRole("button", { name: "Read the maths" })).toBeNull();
  });

  it("offers nothing to read where every page has been read", async () => {
    open({ ...overview, maths_pages: [3, 5] });
    await screen.findByRole("spinbutton", { name: "From page" });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Every page with maths here has been read.",
    );
    expect(screen.getByRole("button", { name: "Read the maths" })).toBeDisabled();
  });

  it("says why a page keeps the PDF's own text", async () => {
    open(overview);

    await userEvent.click(await screen.findByRole("button", { name: /1 keeps the PDF's own text/ }));

    expect(
      screen.getByRole("list", { name: "Pages that keep the PDF's own text" }),
    ).toHaveTextContent("Page 5Its digits differ from the PDF's text: 1 missing (2).");
  });

  it("shows why a reading could not start", async () => {
    open(overview, {
      status: 409,
      body: { detail: "This document is already queued to be read." },
    });

    await userEvent.click(await screen.findByRole("button", { name: "Read the maths" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This document is already queued to be read.",
    );
  });

  it("says so when the document sets no maths", async () => {
    open({ maths_pages: [], read: [], waiting: [], kept_text: [], seconds_per_page: 65 });

    expect(
      await screen.findByText(/sets maths in a maths font, so there is no maths to read/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Read the maths" })).toBeNull();
  });
});

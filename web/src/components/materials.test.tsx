// The Materials tab (decision record 28): each document opens on its own
// page, its menu leads to its summary and maths there, a document being read
// shows the step it is at, and PDFs are added from one button, or from the
// band an empty environment shows, several at a time.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { Materials } from "@/components/materials";
import type { Document, Job, MaterialUpdate } from "@/lib/types";
import { fakeApi } from "@/test/network";

const ready: Document = {
  id: "d1",
  environment_id: "e1",
  filename: "Memory.pdf",
  size_bytes: 489_472,
  sha256: "a".repeat(64),
  status: "ready",
  error: null,
  page_count: 4,
  pages_with_text: 4,
  repaired: false,
  created_at: "2026-11-10T09:00:00Z",
  updated_at: "2026-11-10T09:01:00Z",
};

const reading: Document = {
  ...ready,
  id: "d2",
  filename: "Synchronization.pdf",
  sha256: "b".repeat(64),
  status: "processing",
  page_count: null,
  pages_with_text: null,
};

const update: MaterialUpdate = {
  id: "u2",
  kind: "added",
  document_id: "d2",
  filename: "Synchronization.pdf",
  status: "running",
  steps: [],
  report: null,
  started_at: "2026-11-22T09:00:00Z",
  finished_at: null,
};

const job = (fields: Partial<Job>): Job => ({
  id: "j1",
  kind: "read",
  title: "Reading Synchronization.pdf",
  lane: "read",
  status: "running",
  progress: 0,
  step: "Reading the document",
  error: null,
  attempts: 0,
  max_attempts: 3,
  cancel_requested: false,
  update_id: "u2",
  created_at: "2026-11-22T09:00:00Z",
  started_at: "2026-11-22T09:00:01Z",
  finished_at: null,
  not_before: null,
  ...fields,
});

function open(documents: Document[], jobs: Job[] = [], updates: MaterialUpdate[] = []) {
  const sent = fakeApi([
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: documents } },
    { method: "POST", path: "/api/environments/e1/documents", answer: { status: 202, body: ready } },
    { method: "GET", path: "/api/environments/e1/jobs", answer: { body: jobs } },
    { method: "GET", path: "/api/environments/e1/updates", answer: { body: updates } },
    { method: "GET", path: "/api/documents/d1/summary", answer: { status: 404, body: {} } },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Materials environmentId="e1" />
    </QueryClientProvider>,
  );
  return sent;
}

afterEach(() => window.localStorage.clear());

describe("Materials", () => {
  it("opens a document on its own page, and its summary and maths there", async () => {
    open([ready]);

    const row = await screen.findByRole("listitem");
    expect(within(row).getByText(/^478 KB · added /)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Read Memory.pdf" })).toHaveAttribute(
      "href",
      "/environments/e1/materials/d1",
    );

    await userEvent.click(within(row).getByRole("button", { name: "More for Memory.pdf" }));

    expect(within(row).getByRole("link", { name: "Summarize" })).toHaveAttribute(
      "href",
      "/environments/e1/materials/d1?tab=summary",
    );
    expect(within(row).getByRole("link", { name: "Read the maths" })).toHaveAttribute(
      "href",
      "/environments/e1/materials/d1?tab=maths",
    );
    expect(within(row).getByRole("button", { name: "Upload a new version" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    // Nothing being read: no note on the first upload.
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("shows the step a document being read is at, and what happens now", async () => {
    open(
      [ready, reading],
      [job({ kind: "derive", title: "Updating from Synchronization.pdf", step: "Extracting concepts" })],
      [update],
    );

    expect(await screen.findByText(/^Two documents\.One is being read\.$/)).toBeInTheDocument();
    const steps = await screen.findByRole("list", { name: "Steps for Synchronization.pdf" });
    expect(steps.querySelector('[aria-current="step"]')).toHaveTextContent("Concepts");
    expect(
      screen.getByRole("progressbar", { name: "Updating from Synchronization.pdf" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "First upload — what happens now" }),
    ).toHaveTextContent("You can leave this page: the rail shows the progress.");
  });

  it("offers the band when there is nothing yet, and uploads each PDF dropped on it", async () => {
    const sent = open([]);

    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Choose a PDF to upload")).toHaveLength(1);

    const band = screen.getByText("Drop PDFs here").closest("div")!.parentElement!;
    const pdf = (name: string) => new File(["%PDF-1.7"], name, { type: "application/pdf" });
    fireEvent.drop(band, {
      dataTransfer: { files: [pdf("Week 1.pdf"), new File(["hi"], "notes.txt"), pdf("Week 2.pdf")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("“notes.txt” is not a PDF.");
    const uploads = () =>
      sent.filter((r) => r.method === "POST" && r.path === "/api/environments/e1/documents");
    await expect.poll(() => uploads().map((r) => r.search)).toEqual([
      "?filename=Week%201.pdf",
      "?filename=Week%202.pdf",
    ]);
  });

  it("uploads several PDFs chosen at once", async () => {
    const sent = open([ready]);
    await screen.findByRole("listitem");

    await userEvent.upload(screen.getByLabelText("Choose a PDF to upload"), [
      new File(["%PDF-1.7"], "Week 1.pdf", { type: "application/pdf" }),
      new File(["%PDF-1.7"], "Week 2.pdf", { type: "application/pdf" }),
    ]);

    await expect
      .poll(() => sent.filter((r) => r.method === "POST").length)
      .toBe(2);
  });
});

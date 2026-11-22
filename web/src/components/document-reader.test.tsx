// A document's own page (decision record 28): a breadcrumb back to the
// environment and Materials, the text page by page in regions with their
// maths typeset, and the summary and maths as tabs named in the address.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentReader, firstWords } from "@/components/document-reader";
import type { CurrentSummary, Document, DocumentPage, MathsOverview } from "@/lib/types";
import { fakeApi } from "@/test/network";

// The address as the page reads it: its search parameters, and where it
// is sent.
const address = vi.hoisted(() => ({ search: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/environments/e1/materials/d1",
  useRouter: () => ({ replace: address.replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(address.search),
}));

const document: Document = {
  id: "d1",
  environment_id: "e1",
  filename: "Week 3 eigenvalues.pdf",
  size_bytes: 489_472,
  sha256: "a".repeat(64),
  status: "ready",
  error: null,
  page_count: 3,
  pages_with_text: 2,
  repaired: false,
  created_at: "2026-11-10T09:00:00Z",
  updated_at: "2026-11-10T09:01:00Z",
};

const pages: DocumentPage[] = [
  {
    page_number: 1,
    content: "Eigenvalues\n\n" + String.raw`A matrix \(A\) has eigenvalue \(\lambda\) when \(Av = \lambda v\).`,
  },
  { page_number: 2, content: "Diagonalisation\n\nA matrix with n distinct eigenvalues can be diagonalised." },
  { page_number: 3, content: "" },
];

const summary: CurrentSummary = {
  id: "s1",
  document_id: "d1",
  status: "ready",
  error: null,
  overview: "How a matrix stretches its eigenvectors.",
  key_points: [],
  model: "qwen3:8b",
  prompt_versions: ["summary-v3"],
  source_version: "a".repeat(64),
  sections: 1,
  seconds: 12.5,
  current: true,
  created_at: "2026-11-10T09:02:00Z",
  updated_at: "2026-11-10T09:02:00Z",
  earlier_versions: 0,
};

const maths: MathsOverview = {
  maths_pages: [1],
  read: [],
  waiting: [],
  kept_text: [],
  seconds_per_page: 60,
};

function open({
  documents = [document],
  search = "",
  documentSummary = summary as CurrentSummary | null,
} = {}) {
  address.search = search;
  const sent = fakeApi([
    {
      method: "GET",
      path: "/api/environments/e1",
      answer: {
        body: {
          id: "e1",
          name: "Linear Algebra",
          description: null,
          created_at: "2026-11-01T09:00:00Z",
          updated_at: "2026-11-01T09:00:00Z",
        },
      },
    },
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: documents } },
    { method: "GET", path: "/api/environments/e1/jobs", answer: { body: [] } },
    { method: "GET", path: "/api/environments/e1/updates", answer: { body: [] } },
    { method: "GET", path: "/api/documents/d1/pages", answer: { body: pages } },
    {
      method: "GET",
      path: "/api/documents/d1/summary",
      answer: documentSummary
        ? { body: documentSummary }
        : { status: 404, body: { detail: "No summary yet." } },
    },
    {
      method: "POST",
      path: "/api/documents/d1/summary",
      answer: { status: 202, body: { ...summary, status: "pending", overview: null } },
    },
    { method: "GET", path: "/api/documents/d1/maths", answer: { body: maths } },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DocumentReader environmentId="e1" documentId="d1" />
    </QueryClientProvider>,
  );
  return sent;
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
});

describe("DocumentReader", () => {
  it("leads back to the environment and Materials", async () => {
    open();
    await screen.findByRole("heading", { level: 2, name: "Week 3 eigenvalues.pdf" });

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(breadcrumb).findByRole("link", { name: "Linear Algebra" })).toHaveAttribute(
      "href",
      "/environments/e1",
    );
    expect(within(breadcrumb).getByRole("link", { name: "Materials" })).toHaveAttribute(
      "href",
      "/environments/e1/materials",
    );
    expect(within(breadcrumb).getByText("Week 3 eigenvalues.pdf")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows the text page by page, with its maths typeset", async () => {
    open();

    expect(
      await screen.findByRole("heading", { level: 2, name: "Week 3 eigenvalues.pdf" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/^3 pages · .* · text on 2 of 3 pages$/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Text" })).toHaveAttribute("aria-selected", "true");

    const first = await screen.findByRole("region", { name: "Page 1" });
    expect(within(first).getByRole("heading", { name: "Page 1 of 3" })).toBeInTheDocument();
    expect(first.querySelector(".katex")).not.toBeNull();
    expect(first.querySelector("code")).toBeNull();
    expect(screen.getByRole("region", { name: "Page 2" })).toHaveTextContent("Diagonalisation");
    expect(screen.getByRole("region", { name: "Page 3" })).toHaveTextContent(
      "No text on this page.",
    );

    // The list of pages beside the text, the first marked as the one in view.
    const list = screen.getByRole("navigation", { name: "Pages" });
    expect(within(list).getByRole("link", { name: "Page 1 Eigenvalues" })).toHaveAttribute(
      "aria-current",
      "location",
    );
    expect(within(list).getByRole("link", { name: "Page 2 Diagonalisation" })).toHaveAttribute(
      "href",
      "#page-2",
    );

    // Remembered for Home's Keep reading.
    expect(JSON.parse(window.localStorage.getItem("paideia.last.reading") ?? "null")).toEqual({
      environmentId: "e1",
      documentId: "d1",
      filename: "Week 3 eigenvalues.pdf",
      page: 1,
      pages: 3,
    });
  });

  it("opens the tab the address names, and names the tab chosen", async () => {
    open({ search: "?tab=summary" });

    expect(await screen.findByRole("tab", { name: "Summary" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await screen.findByRole("region", { name: "Summary" })).toHaveTextContent(
      "How a matrix stretches its eigenvectors.",
    );

    await userEvent.click(screen.getByRole("tab", { name: "Maths" }));

    expect(window.location.search).toBe("?tab=maths");
    const offer = await screen.findByRole("region", { name: "Maths of Week 3 eigenvalues.pdf" });
    expect(await within(offer).findByRole("button", { name: "Read the maths" })).toBeEnabled();
  });

  it("asks for a summary where there is none", async () => {
    const sent = open({ search: "?tab=summary", documentSummary: null });

    expect(await screen.findByText(/Waiting to be summarized/)).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "POST" && r.path === "/api/documents/d1/summary")).toHaveLength(1);
  });

  it("offers no maths until the document has been read", async () => {
    open({ documents: [{ ...document, status: "processing", page_count: null }] });

    expect(await screen.findByText("The text shows here once the document has been read.")).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Text", "Summary"]);
    expect(screen.getByRole("list", { name: "Steps for Week 3 eigenvalues.pdf" })).toHaveTextContent(
      "Reading→Summary→Concepts→Knowledge map→Roadmap",
    );
  });

  it("says so when the document is not there", async () => {
    open({ documents: [] });

    expect(await screen.findByRole("heading", { name: "Document not found." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Materials" })).toHaveAttribute(
      "href",
      "/environments/e1/materials",
    );
  });
});

describe("firstWords", () => {
  it("takes the first paragraph, formulas as an ellipsis, cut at a word", () => {
    expect(firstWords(String.raw`Let \(x\) be real.` + "\n\nMore.")).toBe("Let … be real.");
    expect(firstWords("one two three four", 12)).toBe("one two…");
  });
});

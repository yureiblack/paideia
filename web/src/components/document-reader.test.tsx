// A document's own page (decision record 28): a breadcrumb back to the
// environment and Materials, the text page by page in regions with their
// maths typeset, and the summary as a tab named in the address. Each figure
// is drawn as its picture in place of its text (decision record 31).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DocumentReader, firstWords } from "@/components/document-reader";
import type {
  CurrentSummary,
  Document,
  DocumentPage,
  Job,
  MaterialUpdate,
} from "@/lib/types";
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
  pages_ocr: 0,
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

function open({
  documents = [document],
  search = "",
  documentSummary = summary as CurrentSummary | null,
  documentPages = pages,
  jobs = [] as Job[],
  updates = [] as MaterialUpdate[],
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
    { method: "GET", path: "/api/environments/e1/jobs", answer: { body: jobs } },
    { method: "GET", path: "/api/environments/e1/updates", answer: { body: updates } },
    { method: "GET", path: "/api/documents/d1/pages", answer: { body: documentPages } },
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

    await userEvent.click(screen.getByRole("tab", { name: "Text" }));

    expect(window.location.search).toBe("");
    expect(await screen.findByRole("region", { name: "Page 1" })).toBeInTheDocument();
  });

  it("opens the text at an address naming the maths or figures, which are tabs no more", async () => {
    open({ search: "?tab=figures" });

    expect(await screen.findByRole("tab", { name: "Text" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Text", "Summary"]);
  });

  it("draws a figure as its picture, in place of all its text", async () => {
    // A character beyond the first 65,536, as maths fonts give, counts once
    // in the API's places and twice in a JavaScript string.
    const before = "Data 𝑥 arrives.\n\n";
    const text =
      "Figure 1 Eigenvectors Diagram: v; Av. Sales: Year | Sales / 2020 | 5.\n\n0 1 2 3";
    const after = "\n\nThe arrows share a line.";
    const start = [...before].length;
    const end = start + [...text].length;
    open({
      documents: [{ ...document, pages_ocr: 1 }],
      documentPages: [
        {
          page_number: 1,
          content: before + text + after,
          figures: [{ key: "1:72,90,300,200", start, end, caption: "Figure 1 Eigenvectors" }],
        },
        { page_number: 2, content: "Diagonalisation\n\nMore text.", figures: [] },
      ],
    });

    const page = await screen.findByRole("region", { name: "Page 1" });
    expect(screen.getByText(/· text on 2 of 3 pages · 1 page read from pictures$/)).toBeInTheDocument();

    const figure = within(page).getByRole("figure", { name: "Figure 1 Eigenvectors" });
    const picture = within(figure).getByRole("img", { name: "Figure 1 Eigenvectors" });
    expect(picture.getAttribute("src")).toMatch(
      new RegExp(`/api/documents/d1/figures/1%3A72%2C90%2C300%2C200/image\\?version=${"a".repeat(64)}$`),
    );
    expect(picture).toHaveAttribute("loading", "lazy");
    // Only the picture: neither what the model read nor the PDF's labels.
    expect(figure.textContent).toBe("");
    expect(page).not.toHaveTextContent("Diagram: v; Av");
    expect(page).not.toHaveTextContent("0 1 2 3");
    expect(within(page).queryByRole("table")).toBeNull();

    // The text around it is as it was.
    expect(within(page).getByText("Data 𝑥 arrives.")).toBeInTheDocument();
    expect(within(page).getByText("The arrows share a line.")).toBeInTheDocument();

    // The list of pages sums the page up by its text and the figure's caption.
    const list = screen.getByRole("navigation", { name: "Pages" });
    expect(within(list).getByRole("link", { name: "Page 1 Data 𝑥 arrives." })).toBeInTheDocument();
  });

  it("draws a figure with no text of its own where it stands", async () => {
    open({
      documentPages: [
        {
          page_number: 1,
          content: "Above.\n\nBelow.",
          figures: [{ key: "1:72,90,300,200", start: 6, end: 6, caption: null }],
        },
      ],
    });

    const page = await screen.findByRole("region", { name: "Page 1" });
    const [above, figure, below] = Array.from(page.children).slice(1);
    expect(above).toHaveTextContent("Above.");
    expect(figure).toBe(within(page).getByRole("figure", { name: "A figure on page 1" }));
    expect(below).toHaveTextContent("Below.");
  });

  it("asks for a summary where there is none", async () => {
    const sent = open({ search: "?tab=summary", documentSummary: null });

    expect(await screen.findByText(/Waiting to be summarized/)).toBeInTheDocument();
    expect(sent.filter((r) => r.method === "POST" && r.path === "/api/documents/d1/summary")).toHaveLength(1);
  });

  it("shows its maths and figures being read with one bar, beside the page", async () => {
    // The background work beside the page shows the bar, with Cancel; the
    // header shows it only when the contents are hidden on a desktop.
    open({
      updates: [
        {
          id: "u1",
          kind: "added",
          document_id: "d1",
          filename: "Week 3 eigenvalues.pdf",
          status: "running",
          steps: [],
          report: null,
          started_at: "2026-11-21T10:00:00Z",
          finished_at: null,
        },
      ],
      jobs: [
        {
          id: "j1",
          kind: "vision",
          title: "Reading the maths and figures of Week 3 eigenvalues.pdf",
          lane: "model",
          status: "running",
          progress: 40,
          step: "Reading the maths of page 2",
          error: null,
          attempts: 0,
          max_attempts: 3,
          cancel_requested: false,
          update_id: "u1",
          created_at: "2026-11-21T10:00:00Z",
          started_at: "2026-11-21T10:00:01Z",
          finished_at: null,
          not_before: null,
        },
      ],
    });

    expect(await screen.findByRole("region", { name: "Page 1" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Steps for Week 3 eigenvalues.pdf" })).toBeNull();
    expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
  });

  it("shows the steps until the document has been read", async () => {
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

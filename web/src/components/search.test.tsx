// A search that finds nothing (decision record 28): the page says so
// plainly and suggests what to try, naming real concepts from the knowledge
// map, and later only while documents are still being read. Clear the
// search starts again. A passage that is a figure the model read (decision
// record 29) shows the figure's picture, and says it is the model's.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Search } from "@/components/search";
import type { Citation, GraphState, SearchResult } from "@/lib/types";
import { fakeApi } from "@/test/network";

const graph: GraphState = {
  state: "up_to_date",
  waiting_for: 0,
  error: null,
  nodes: [
    { id: "n1", name: "Deadlock" },
    { id: "n2", name: "Round Robin" },
    { id: "n3", name: "Aging" },
  ],
  edges: [],
  pairs: null,
  asked: null,
  updated_at: null,
};

const cite = (fields: Partial<Citation>): Citation => ({
  environment_id: "e1",
  document_id: "d1",
  document_version: "v1",
  filename: "Data.pdf",
  chunk_id: "c1",
  page_start: 2,
  page_end: 2,
  heading: null,
  excerpt: "A pipeline cleans the data before it is stored.",
  figure_id: null,
  ...fields,
});

function open(documents: { status: string }[], results: SearchResult[] = []) {
  const sent = fakeApi([
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: documents } },
    { method: "GET", path: "/api/environments/e1/graph", answer: { body: graph } },
    { method: "POST", path: "/api/search", answer: { body: { results, debug: null } } },
  ]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Search environmentId="e1" />
    </QueryClientProvider>,
  );
  return sent;
}

async function search(words: string) {
  await userEvent.type(
    screen.getByRole("searchbox", { name: "Search this environment's materials" }),
    words,
  );
  await userEvent.click(screen.getByRole("button", { name: "Search" }));
}

describe("Search", () => {
  it("says nothing answers the query, and what to try instead", async () => {
    const sent = open([{ status: "ready" }, { status: "processing" }]);
    expect(await screen.findByText("Searches 1 document that has finished reading")).toBeInTheDocument();

    await search("how does round robin pick");

    expect(await screen.findByRole("heading", { name: "Nothing in these documents answers that." })).toBeInTheDocument();
    expect(screen.getByText("0 passages from 1 document that has finished reading")).toBeInTheDocument();
    // A concept sharing a word with the query comes first.
    expect(
      screen.getByText(/A concept's name from the knowledge map, such as Round Robin or Aging\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/Again later: 1 document is still being read/)).toBeInTheDocument();
    expect(sent.find((s) => s.method === "POST")?.body).toEqual({
      environment_id: "e1",
      query: "how does round robin pick",
      debug: false,
    });

    await userEvent.click(screen.getByRole("button", { name: "Clear the search" }));
    expect(screen.getByRole("searchbox", { name: "Search this environment's materials" })).toHaveValue("");
    expect(screen.queryByText("Nothing in these documents answers that.")).toBeNull();
  });

  it("leaves out waiting for documents when every one has been read", async () => {
    open([{ status: "ready" }]);

    await search("buddy allocator");

    expect(await screen.findByText("Nothing in these documents answers that.")).toBeInTheDocument();
    expect(screen.queryByText(/Again later/)).toBeNull();
  });

  it("shows the picture of a figure it found, marked as the model's description", async () => {
    open(
      [{ status: "ready" }],
      [
        {
          citation: cite({
            chunk_id: "c2",
            heading: "Figure 2.1 The data pipeline",
            excerpt:
              "Figure 2.1 The data pipeline Diagram: raw; clean. Described by the model: Three boxes in a row.",
            figure_id: "f9",
          }),
          score: 0.8,
        },
        { citation: cite({}), score: 0.6 },
      ],
    );

    await search("data pipeline");

    const results = await screen.findByRole("list", { name: "Search results" });
    const [figure, passage] = within(results).getAllByRole("listitem");
    const picture = within(figure).getByRole("img", { name: "Figure 2.1 The data pipeline" });
    expect(picture.getAttribute("src")).toMatch(/\/api\/figures\/f9\/image$/);
    expect(picture).toHaveAttribute("loading", "lazy");
    expect(within(figure).getByText("Figure · described by the model")).toBeInTheDocument();
    // An ordinary passage has neither.
    expect(within(passage).queryByRole("img")).toBeNull();
    expect(within(passage).queryByText("Figure · described by the model")).toBeNull();
  });

  it("says there is nothing to search before any document has been read", async () => {
    open([{ status: "processing" }]);

    expect(await screen.findByText("Nothing to search yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Materials" })).toHaveAttribute(
      "href",
      "/environments/e1/materials",
    );
  });
});

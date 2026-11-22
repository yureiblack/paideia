// A search that finds nothing (decision record 28): the page says so
// plainly and suggests what to try, naming real concepts from the knowledge
// map, and later only while documents are still being read. Clear the
// search starts again.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Search } from "@/components/search";
import type { GraphState } from "@/lib/types";
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

function open(documents: { status: string }[]) {
  const sent = fakeApi([
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: documents } },
    { method: "GET", path: "/api/environments/e1/graph", answer: { body: graph } },
    { method: "POST", path: "/api/search", answer: { body: { results: [], debug: null } } },
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

  it("says there is nothing to search before any document has been read", async () => {
    open([{ status: "processing" }]);

    expect(await screen.findByText("Nothing to search yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Materials" })).toHaveAttribute(
      "href",
      "/environments/e1/materials",
    );
  });
});

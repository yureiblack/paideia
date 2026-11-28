// The Overview's index of the environment (decision record 28): its Summary
// line says what comes while there is no summary to show, as after a
// document it was built from is deleted.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnvironmentIndex } from "@/components/overview-sections";
import type {
  EnvironmentSummaryState,
  GraphState,
  PracticeOverview,
  RoadmapState,
} from "@/lib/types";
import { fakeApi } from "@/test/network";

const graph: GraphState = {
  state: "none",
  waiting_for: 0,
  error: null,
  nodes: [],
  edges: [],
  pairs: null,
  asked: null,
  updated_at: null,
};
const roadmap: RoadmapState = { state: "none", error: null, stages: [], cycles: [], updated_at: null };
const practice: PracticeOverview = {
  items: 0,
  due_concepts: 0,
  new_concepts: 0,
  next_review_at: null,
  concepts: [],
  needs_attention: [],
  recently_strong: [],
};

function show(summary: EnvironmentSummaryState) {
  fakeApi([
    { method: "GET", path: "/api/environments/e1/summary", answer: { body: summary } },
    { method: "GET", path: "/api/environments/e1/documents", answer: { body: [] } },
    { method: "GET", path: "/api/environments/e1/graph", answer: { body: graph } },
    { method: "GET", path: "/api/environments/e1/roadmap", answer: { body: roadmap } },
    { method: "GET", path: "/api/environments/e1/practice", answer: { body: practice } },
    { method: "GET", path: "/api/environments/e1/practice/history", answer: { body: [] } },
  ]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EnvironmentIndex environmentId="e1" />
    </QueryClientProvider>,
  );
}

const noSummary: Omit<EnvironmentSummaryState, "state" | "earlier_versions"> = {
  waiting_for: 0,
  error: null,
  summary: null,
  not_included: [],
};

describe("EnvironmentIndex", () => {
  it("says the summary is being written when the last one was built from a deleted document", async () => {
    // The API shows no summary with points from a document that is gone.
    show({ ...noSummary, state: "stale", earlier_versions: 1 });

    expect(await screen.findByText("Being written from the documents' summaries.")).toBeInTheDocument();
  });

  it("says the summary is written once documents are read when every document is deleted", async () => {
    show({ ...noSummary, state: "none", earlier_versions: 1 });

    expect(await screen.findByText("Written once the documents have been read.")).toBeInTheDocument();
  });
});

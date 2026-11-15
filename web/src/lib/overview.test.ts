// What the Overview tab works out by itself (decision record 19): each
// roadmap stage's progress, and the knowledge map's highlights.

import { describe, expect, it } from "vitest";

import { formatBytes } from "@/lib/format";
import { mapHighlights, stageProgress } from "@/lib/overview";
import type { GraphEdge, GraphState, PracticeConcept, RoadmapStage } from "@/lib/types";

function stage(number: number, conceptIds: string[]): RoadmapStage {
  return {
    number,
    title: `Stage ${number}`,
    description: null,
    written: true,
    documents: [],
    concepts: conceptIds.map((id) => ({
      id,
      name: id,
      definition: "",
      builds_on: [],
      in_cycle: false,
      documents: [],
      evidence: [],
    })),
  };
}

function practised(id: string, exposures: number, strong = false): PracticeConcept {
  return {
    concept_id: id,
    name: id,
    state: "ready",
    error: null,
    items: 4,
    review: exposures ? "scheduled" : "new",
    exposures,
    recalled: 0,
    failed: 0,
    last_attempted_at: null,
    last_recalled_at: null,
    gap_days: null,
    next_review_at: null,
    attention: null,
    strong,
  };
}

function graph(names: string[], edges: [string, string, GraphEdge["relationship_type"]][]): GraphState {
  return {
    state: "up_to_date",
    waiting_for: 0,
    error: null,
    nodes: names.map((name) => ({ id: name, name })),
    edges: edges.map(([source, target, relationship_type], i) => ({
      id: String(i),
      source,
      target,
      relationship_type,
      confidence: 0.9,
    })),
    pairs: null,
    asked: null,
    updated_at: null,
  };
}

describe("stageProgress", () => {
  it("counts each stage's concepts practised and strong", () => {
    const progress = stageProgress(
      [stage(1, ["a", "b", "c"]), stage(2, ["d"])],
      [practised("a", 3, true), practised("b", 1), practised("c", 0), practised("d", 0)],
    );

    expect(progress).toEqual([
      { number: 1, title: "Stage 1", total: 3, practised: 2, strong: 1 },
      { number: 2, title: "Stage 2", total: 1, practised: 0, strong: 0 },
    ]);
  });

  it("counts a concept with no practice yet as neither", () => {
    // A concept new to the roadmap may not have reached practice.
    const [progress] = stageProgress([stage(1, ["new"])], []);

    expect(progress).toMatchObject({ total: 1, practised: 0, strong: 0 });
  });
});

describe("mapHighlights", () => {
  it("ranks concepts by their relationships, ties by name", () => {
    const highlights = mapHighlights(
      graph(
        ["Paging", "Caches", "TLB", "Alone"],
        [
          ["Paging", "TLB", "PREREQUISITE_OF"],
          ["Caches", "TLB", "RELATED_TO"],
          ["Paging", "Caches", "RELATED_TO"],
        ],
      ),
    );

    expect(highlights.concepts).toBe(4);
    expect(highlights.relationships).toBe(3);
    expect(highlights.connected.map((c) => [c.name, c.links])).toEqual([
      ["Caches", 2],
      ["Paging", 2],
      ["TLB", 2],
    ]);
  });

  it("starts from concepts others build on that build on nothing", () => {
    const highlights = mapHighlights(
      graph(
        ["Processes", "Threads", "Scheduling", "Locks"],
        [
          ["Processes", "Threads", "PREREQUISITE_OF"],
          ["Processes", "Scheduling", "PREREQUISITE_OF"],
          ["Threads", "Locks", "PREREQUISITE_OF"],
        ],
      ),
    );

    // Threads leads somewhere but builds on Processes, so it is not a start.
    expect(highlights.foundations).toEqual([{ id: "Processes", name: "Processes", leadsTo: 2 }]);
  });

  it("keeps at most the limit of each", () => {
    const names = ["A", "B", "C", "D"];
    const highlights = mapHighlights(
      graph(names, [
        ["A", "B", "PREREQUISITE_OF"],
        ["C", "D", "PREREQUISITE_OF"],
      ]),
      1,
    );

    expect(highlights.connected).toHaveLength(1);
    expect(highlights.foundations.map((c) => c.name)).toEqual(["A"]);
  });
});

describe("formatBytes", () => {
  it("uses the unit that keeps the number short", () => {
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(300 * 1024)).toBe("300 KB");
    expect(formatBytes(5.2 * 1024 * 1024)).toBe("5.2 MB");
  });
});

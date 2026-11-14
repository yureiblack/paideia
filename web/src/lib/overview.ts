// What the Overview tab works out from data other tabs already fetch
// (decision record 19): each roadmap stage's progress, and the knowledge
// map's highlights. Nothing here asks the backend for anything new.

import type { ConceptRef, GraphState, PracticeConcept, RoadmapStage } from "@/lib/types";

// A stage's concepts: how many there are, how many were practised (answered
// at least once) and how many are strong (recalled on their last answer
// after a gap of four days or more, the backend's rule).
export type StageProgress = {
  number: number;
  title: string;
  total: number;
  practised: number;
  strong: number;
};

export function stageProgress(
  stages: RoadmapStage[],
  concepts: PracticeConcept[],
): StageProgress[] {
  const byId = new Map(concepts.map((c) => [c.concept_id, c]));
  return stages.map((stage) => {
    const states = stage.concepts.map((c) => byId.get(c.id));
    return {
      number: stage.number,
      title: stage.title,
      total: stage.concepts.length,
      practised: states.filter((c) => c && c.exposures > 0).length,
      strong: states.filter((c) => c?.strong).length,
    };
  });
}

// The map in a few lines: its size; the concepts with the most direct
// relationships; and where to start, the concepts others build on that build
// on nothing themselves, those most built on first. At most `limit` each,
// ties by name.
export type MapHighlights = {
  concepts: number;
  relationships: number;
  connected: (ConceptRef & { links: number })[];
  foundations: (ConceptRef & { leadsTo: number })[];
};

export function mapHighlights(graph: GraphState, limit = 5): MapHighlights {
  const links = new Map<string, number>();
  const leadsTo = new Map<string, number>();
  const buildsOn = new Set<string>();
  for (const edge of graph.edges) {
    links.set(edge.source, (links.get(edge.source) ?? 0) + 1);
    links.set(edge.target, (links.get(edge.target) ?? 0) + 1);
    if (edge.relationship_type === "PREREQUISITE_OF") {
      leadsTo.set(edge.source, (leadsTo.get(edge.source) ?? 0) + 1);
      buildsOn.add(edge.target);
    }
  }
  const byName = (a: ConceptRef, b: ConceptRef) => a.name.localeCompare(b.name);
  const connected = graph.nodes
    .map((n) => ({ id: n.id, name: n.name, links: links.get(n.id) ?? 0 }))
    .filter((n) => n.links > 0)
    .sort((a, b) => b.links - a.links || byName(a, b))
    .slice(0, limit);
  const foundations = graph.nodes
    .filter((n) => leadsTo.has(n.id) && !buildsOn.has(n.id))
    .map((n) => ({ id: n.id, name: n.name, leadsTo: leadsTo.get(n.id) ?? 0 }))
    .sort((a, b) => b.leadsTo - a.leadsTo || byName(a, b))
    .slice(0, limit);
  return {
    concepts: graph.nodes.length,
    relationships: graph.edges.length,
    connected,
    foundations,
  };
}

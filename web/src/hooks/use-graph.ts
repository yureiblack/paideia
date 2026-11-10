// The environment's knowledge graph, which rebuilds itself in the background
// once concepts change. Checked every two seconds while it is being built,
// waits for documents, or is out of date, so the page follows along: out of
// date is how it looks in the moment between its concepts changing and its
// rebuild starting. A concept's neighbourhood is fetched again whenever the
// graph changes.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { GraphState } from "@/lib/types";

const key = (environmentId: string) =>
  ["environments", environmentId, "graph"] as const;

export function useGraph(environmentId: string) {
  return useQuery({
    queryKey: key(environmentId),
    queryFn: () => api.getGraph(environmentId),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "updating" || state === "waiting" || state === "stale"
        ? 2000
        : false;
    },
  });
}

export function useRequestGraph(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.requestGraph(environmentId),
    onSuccess: (state) => queryClient.setQueryData(key(environmentId), state),
  });
}

// What changes when the graph does: its edges.
export function graphVersion(graph: GraphState | undefined): string {
  if (!graph) return "";
  return graph.edges
    .map((e) => `${e.id}:${e.confidence}`)
    .sort()
    .join(",");
}

export function useNeighbourhood(conceptId: string | null, version: string) {
  return useQuery({
    queryKey: ["concepts", conceptId, "neighbourhood", version],
    queryFn: () => api.getNeighbourhood(conceptId as string),
    enabled: conceptId !== null,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === conceptId ? previous : undefined,
  });
}

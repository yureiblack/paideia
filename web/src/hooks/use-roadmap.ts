// The environment's learning roadmap. Its stages always follow the current
// concepts and graph; their titles are written in the background after the
// graph. Checked every two seconds while the titles are being written, wait
// for the graph, or are out of date, so the page follows along.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const key = (environmentId: string) =>
  ["environments", environmentId, "roadmap"] as const;

export function useRoadmap(environmentId: string) {
  return useQuery({
    queryKey: key(environmentId),
    queryFn: () => api.getRoadmap(environmentId),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "updating" || state === "waiting" || state === "stale"
        ? 2000
        : false;
    },
  });
}

export function useRequestRoadmap(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.requestRoadmap(environmentId),
    onSuccess: (state) => queryClient.setQueryData(key(environmentId), state),
  });
}

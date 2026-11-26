// An environment's background work. Checked every second and a half while a
// job is queued or running, so progress fills in live; when work finishes,
// everything the environment and its documents show is asked for again, as
// it may have changed: a document's text, read again with its maths and
// figures, and its pages.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "@/lib/api";

const ACTIVE = new Set(["queued", "running"]);

export function useJobs(environmentId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["environments", environmentId, "jobs"],
    queryFn: () => api.listJobs(environmentId),
    refetchInterval: (q) =>
      q.state.data?.some((j) => ACTIVE.has(j.status)) ? 1500 : 10_000,
  });
  const active = query.data?.filter((j) => ACTIVE.has(j.status)).length ?? 0;
  const before = useRef(active);
  useEffect(() => {
    if (active < before.current) {
      queryClient.invalidateQueries({ queryKey: ["environments", environmentId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
    before.current = active;
  }, [active, environmentId, queryClient]);
  return query;
}

export function useCancelJob(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["environments", environmentId, "jobs"] }),
  });
}

// Whether a worker is running, checked every half minute while work waits.
export function useWorker(enabled: boolean) {
  return useQuery({
    queryKey: ["worker"],
    queryFn: () => api.workerHealth(),
    enabled,
    retry: false,
    refetchInterval: 30_000,
  });
}

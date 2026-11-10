// The environment's summary, which keeps itself up to date as documents are
// added and removed. Checked every two seconds while it is being rebuilt, is
// waiting for documents, or is out of date, so the page follows along: out
// of date is how it looks in the moment between a document's summary being
// written and the environment's rebuild starting.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const key = (environmentId: string) =>
  ["environments", environmentId, "summary"] as const;

export function useEnvironmentSummary(environmentId: string) {
  return useQuery({
    queryKey: key(environmentId),
    queryFn: () => api.getEnvironmentSummary(environmentId),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "updating" || state === "waiting" || state === "stale"
        ? 2000
        : false;
    },
  });
}

export function useRequestEnvironmentSummary(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.requestEnvironmentSummary(environmentId),
    onSuccess: (state) => queryClient.setQueryData(key(environmentId), state),
  });
}

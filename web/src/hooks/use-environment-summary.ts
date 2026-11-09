// The environment's summary, which keeps itself up to date as documents are
// added and removed. Checked every two seconds while it is being rebuilt or
// is waiting for documents, so the page follows along.

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
      return state === "updating" || state === "waiting" ? 2000 : false;
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

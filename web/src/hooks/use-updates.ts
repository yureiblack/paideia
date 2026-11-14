// Changes to an environment's material, each followed step by step. Checked
// every second and a half while one is running, so its steps fill in live.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useUpdates(environmentId: string) {
  return useQuery({
    queryKey: ["environments", environmentId, "updates"],
    queryFn: () => api.listUpdates(environmentId),
    refetchInterval: (query) =>
      query.state.data?.some((u) => u.status === "running") ? 1500 : false,
  });
}

// A new version of a document. Everything derived from the material is
// asked for afresh, as for an upload.
export function useNewVersion(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, file }: { documentId: string; file: File }) =>
      api.uploadNewVersion(documentId, file),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["environments", environmentId] }),
  });
}

// An environment's concepts, extracted from its documents in the background.
// Checked every two seconds while any document is being read, or its
// concepts are waiting or being extracted, so the page fills in as they arrive.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

const key = (environmentId: string) =>
  ["environments", environmentId, "concepts"] as const;

export function useConcepts(environmentId: string) {
  return useQuery({
    queryKey: key(environmentId),
    queryFn: () => api.getConcepts(environmentId),
    refetchInterval: (query) =>
      query.state.data?.documents.some(
        (d) =>
          d.status === "pending" ||
          d.status === "generating" ||
          d.document_status === "uploaded" ||
          d.document_status === "processing",
      )
        ? 2000
        : false,
  });
}

// Ask for a document's concepts again, after a failure for example.
export function useRequestConcepts(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.requestConcepts(documentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key(environmentId) }),
  });
}

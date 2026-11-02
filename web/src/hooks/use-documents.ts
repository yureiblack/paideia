// Reading and changing an environment's documents. The list polls every
// second while any document is still waiting or being read, and stops by
// itself once they have all settled.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Document } from "@/lib/types";

// Under the environment's own key, so deleting the environment clears these.
const listKey = (environmentId: string) =>
  ["environments", environmentId, "documents"] as const;
const pagesKey = (documentId: string) =>
  ["documents", documentId, "pages"] as const;

const isPending = (document: Document) =>
  document.status === "uploaded" || document.status === "processing";

export function useDocuments(environmentId: string) {
  return useQuery({
    queryKey: listKey(environmentId),
    queryFn: () => api.listDocuments(environmentId),
    refetchInterval: (query) =>
      query.state.data?.some(isPending) ? 1000 : false,
  });
}

export function usePages(documentId: string) {
  return useQuery({
    queryKey: pagesKey(documentId),
    queryFn: () => api.getPages(documentId),
  });
}

export function useUploadDocument(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadDocument(environmentId, file),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: listKey(environmentId) }),
  });
}

export function useReprocessDocument(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.reprocessDocument(documentId),
    onSuccess: (_, documentId) => {
      queryClient.removeQueries({ queryKey: pagesKey(documentId) });
      return queryClient.invalidateQueries({ queryKey: listKey(environmentId) });
    },
  });
}

export function useDeleteDocument(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.deleteDocument(documentId),
    onSuccess: (_, documentId) => {
      queryClient.removeQueries({ queryKey: pagesKey(documentId) });
      return queryClient.invalidateQueries({ queryKey: listKey(environmentId) });
    },
  });
}

// Reading and changing an environment's documents. The list polls every
// second while any document is still waiting or being read, and stops by
// itself once they have all settled.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { CurrentSummary, Document } from "@/lib/types";

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

// A document's summary, written in the background once the document is read.
// Polled every two seconds while it waits or is being written, and for a
// minute after the document became ready, while its summary is being asked
// for. Under the environment's key, so deleting the environment clears it.
const summaryKey = (environmentId: string, documentId: string) =>
  ["environments", environmentId, "documents", documentId, "summary"] as const;

const isWriting = (summary: CurrentSummary | null | undefined) =>
  summary?.status === "pending" || summary?.status === "generating";

export function useSummary(environmentId: string, document: Document) {
  const ready = document.status === "ready";
  return useQuery({
    queryKey: summaryKey(environmentId, document.id),
    queryFn: () => api.getSummary(document.id),
    enabled: ready,
    refetchInterval: (query) => {
      const summary = query.state.data;
      const justRead =
        summary === null &&
        Date.now() - new Date(document.updated_at).getTime() < 60_000;
      return isWriting(summary) || justRead ? 2000 : false;
    },
  });
}

export function useRequestSummary(environmentId: string, documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.requestSummary(documentId),
    onSuccess: (summary) =>
      queryClient.setQueryData(summaryKey(environmentId, documentId), summary),
  });
}

// Opening a citation: the pages a cited passage touches, with the passage
// marked. Cached under the environment's own key, so deleting the environment
// clears them. Fetched only once the reader asks to see it.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

const previewKey = (environmentId: string, chunkId: string) =>
  ["environments", environmentId, "chunks", chunkId, "preview"] as const;

export function usePreview(
  environmentId: string,
  chunkId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: previewKey(environmentId, chunkId),
    queryFn: () => api.getPreview(chunkId),
    enabled,
  });
}

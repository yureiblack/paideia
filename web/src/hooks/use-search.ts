// Searching an environment's materials. Each query's results are cached under
// the environment's own key, so going back to an earlier query is instant and
// deleting the environment clears them. An empty query sends no request.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

const searchKey = (environmentId: string, query: string) =>
  ["environments", environmentId, "search", query] as const;

export function useSearch(environmentId: string, query: string) {
  return useQuery({
    queryKey: searchKey(environmentId, query),
    queryFn: () => api.search(environmentId, query),
    enabled: query.length > 0,
  });
}

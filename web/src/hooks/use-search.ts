// Searching an environment's materials. Each query's results are cached under
// the environment's own key, so going back to an earlier query is instant and
// deleting the environment clears them. With and without the scoring details
// are cached separately. An empty query sends no request.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

const searchKey = (environmentId: string, query: string, debug: boolean) =>
  ["environments", environmentId, "search", query, debug] as const;

export function useSearch(environmentId: string, query: string, debug: boolean) {
  return useQuery({
    queryKey: searchKey(environmentId, query, debug),
    queryFn: () => api.search(environmentId, query, debug),
    enabled: query.length > 0,
  });
}

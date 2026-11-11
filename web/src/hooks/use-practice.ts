// Practice: what is due, preparing items, sessions and answers. The overview
// is checked every two seconds while any concept's items are being written,
// so the page follows along. A session is fetched once when it starts and
// kept as it was, so answering items does not reshuffle it.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { AttemptInput } from "@/lib/types";

const key = (environmentId: string) =>
  ["environments", environmentId, "practice"] as const;

// The end of the learner's own day, as an instant the API understands.
export function endOfToday(): string {
  const end = new Date();
  end.setHours(23, 59, 59, 999);
  return end.toISOString();
}

export function usePractice(environmentId: string) {
  return useQuery({
    queryKey: key(environmentId),
    queryFn: () => api.getPractice(environmentId, endOfToday()),
    refetchInterval: (query) =>
      query.state.data?.concepts.some(
        (c) => c.state === "pending" || c.state === "generating",
      )
        ? 2000
        : false,
  });
}

export function usePreparePractice(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conceptIds: string[]) =>
      api.preparePractice(environmentId, conceptIds),
    onSuccess: (overview) => queryClient.setQueryData(key(environmentId), overview),
  });
}

// started tells sessions apart, so starting again fetches a fresh one.
export function usePracticeSession(
  environmentId: string,
  conceptIds: string[] | null,
  started: number | null,
) {
  return useQuery({
    queryKey: [...key(environmentId), "session", conceptIds, started],
    queryFn: () =>
      api.getPracticeSession(environmentId, endOfToday(), conceptIds ?? undefined),
    enabled: started !== null,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useAnswer(environmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, input }: { itemId: string; input: AttemptInput }) =>
      api.answerItem(itemId, input),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: key(environmentId), exact: true }),
  });
}
